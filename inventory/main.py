import base64
import binascii
import os
import secrets
from datetime import UTC
from pathlib import Path
from time import perf_counter
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .dashboard import dashboard_data, latest_movements, product_history
from .db import build_engine, store_now, transaction
from .models import ForecastRun, Product, StoreSetting
from .schemas import Discard, ProductCreate, ProductDetails, Receipt, StockMovement
from .stock import InventoryError, discard, get_product, product_data, receive, sell

STATIC = Path(__file__).parent / "static"
HEALTH_PATHS = {"/health/live", "/health/ready", "/metrics"}


def authorized(header: str, username: str, password: str) -> bool:
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        supplied = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return False
    return secrets.compare_digest(supplied, f"{username}:{password}".encode())


def create_app(engine: Engine | None = None) -> FastAPI:
    engine = engine if engine is not None else build_engine()
    username, password = os.getenv("APP_USERNAME", ""), os.getenv("APP_PASSWORD", "")
    if bool(username) != bool(password) or ":" in username:
        raise RuntimeError(
            "Set both APP_USERNAME and APP_PASSWORD. The username cannot contain a colon."
        )

    app = FastAPI(title="FreshLedger API", version="1.0.0")
    registry = CollectorRegistry()
    requests = Counter(
        "freshledger_http_requests_total",
        "HTTP requests",
        ("method", "route", "status"),
        registry=registry,
    )
    latency = Histogram(
        "freshledger_http_duration_seconds",
        "HTTP request duration",
        ("method", "route"),
        registry=registry,
    )
    database_up = Gauge("freshledger_database_up", "Whether the database responds", registry=registry)
    forecast_at = Gauge(
        "freshledger_forecast_last_success_timestamp_seconds",
        "Last successful forecast publication",
        registry=registry,
    )
    forecast_products = Gauge(
        "freshledger_forecast_products",
        "Products included in the latest run",
        registry=registry,
    )

    @app.middleware("http")
    async def protect_and_measure(request: Request, call_next):
        start = perf_counter()
        path = request.url.path
        if (
            password
            and path not in HEALTH_PATHS
            and not authorized(
                request.headers.get("authorization", ""),
                username,
                password,
            )
        ):
            return JSONResponse(
                {"detail": "Sign in to FreshLedger."},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="FreshLedger", charset="UTF-8"'},
            )
        if request.method in {"POST", "PUT", "PATCH"} and path.startswith("/api/"):
            content_type = request.headers.get("content-type", "").split(";", 1)[0].lower().strip()
            if content_type != "application/json":
                return JSONResponse({"detail": "Send an application/json request."}, status_code=415)
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            if path not in HEALTH_PATHS:
                route = getattr(request.scope.get("route"), "path", "unmatched")
                method = (
                    request.method if request.method in {"GET", "POST", "PATCH", "HEAD"} else "OTHER"
                )
                requests.labels(method, route, str(status)).inc()
                latency.labels(method, route).observe(perf_counter() - start)
        if path.startswith("/api/") or path == "/":
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if path == "/":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
        return response

    @app.exception_handler(InventoryError)
    async def inventory_error(_: Request, error: InventoryError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, __: IntegrityError):
        return JSONResponse(
            {"detail": "This record conflicts with an existing inventory update."}, status_code=409
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError):
        messages = [
            " · ".join(map(str, item["loc"][1:])) + ": " + item["msg"] for item in error.errors()
        ]
        return JSONResponse({"detail": messages}, status_code=422)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health/live")
    def liveness():
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness():
        try:
            with transaction(engine) as session:
                configured = session.get(StoreSetting, "data_mode")
        except SQLAlchemyError:
            configured = None
        if configured is None:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        try:
            with transaction(engine) as session:
                session.execute(text("SELECT 1"))
                latest = session.scalar(select(ForecastRun).order_by(ForecastRun.as_of.desc()).limit(1))
                if latest is not None:
                    forecast_at.set(latest.completed_at.replace(tzinfo=UTC).timestamp())
                    forecast_products.set(latest.products_forecast)
            database_up.set(1)
        except SQLAlchemyError:
            database_up.set(0)
        return Response(
            generate_latest(registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST, "Cache-Control": "no-store"},
        )

    @app.get("/api/dashboard")
    def dashboard():
        with transaction(engine) as session:
            return dashboard_data(session, store_now().date())

    @app.get("/api/products/{product_id}/forecast")
    def history(product_id: int):
        with transaction(engine) as session:
            return product_history(session, product_id, store_now().date())

    @app.post("/api/products", status_code=201)
    def create_product(data: ProductCreate):
        with transaction(engine, write=True) as session:
            if session.scalar(select(Product.id).where(Product.sku == data.sku)) is not None:
                raise InventoryError("A product with this SKU already exists.")
            product = Product(**data.model_dump(), created_on=store_now().date())
            session.add(product)
            session.flush()
            return product_data(product)

    @app.patch("/api/products/{product_id}")
    def update_product(product_id: int, data: ProductDetails):
        with transaction(engine, write=True) as session:
            product = get_product(session, product_id, lock=True)
            product.name, product.category, product.reorder_point = (
                data.name,
                data.category,
                data.reorder_point,
            )
            return product_data(product)

    @app.post("/api/products/{product_id}/receipts", status_code=201)
    def add_receipt(product_id: int, data: Receipt):
        with transaction(engine, write=True) as session:
            return receive(session, product_id, data, store_now().date())

    @app.post("/api/products/{product_id}/sales", status_code=201)
    def add_sale(product_id: int, data: StockMovement):
        with transaction(engine, write=True) as session:
            return sell(session, product_id, data, store_now().date())

    @app.post("/api/batches/{batch_id}/discards", status_code=201)
    def add_discard(batch_id: int, data: Discard):
        with transaction(engine, write=True) as session:
            return discard(session, batch_id, data, store_now().date())

    @app.get("/api/movements")
    def movements(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        before: Annotated[int | None, Query(ge=1)] = None,
    ):
        with transaction(engine) as session:
            return latest_movements(session, limit=limit, before=before)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
