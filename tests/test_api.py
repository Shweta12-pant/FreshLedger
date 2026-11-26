from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from inventory.commands import initialize
from inventory.db import transaction
from inventory.forecast import run_forecast
from inventory.main import create_app
from inventory.models import ForecastRun, Product, SaleDay


def add_product(client, sku="MILK-1", name="Whole Milk"):
    response = client.post(
        "/api/products", json={"sku": sku, "name": name, "category": "Dairy", "reorder_point": 6}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_batch(client, product_id, code, quantity, expires, **extra):
    return client.post(
        f"/api/products/{product_id}/receipts",
        json={
            "batch_code": code,
            "units": quantity,
            "expires_on": expires.isoformat(),
            **extra,
        },
    )


def sell(client, product_id, quantity, **extra):
    return client.post(f"/api/products/{product_id}/sales", json={"units": quantity, **extra})


def test_dashboard_and_ready(engine):
    with TestClient(create_app(engine)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ready"}
        assert client.get("/api/dashboard").json()["summary"]["products"] == 0
        assert "freshledger_database_up 1.0" in client.get("/metrics").text
        assert "freshledger_http_requests_total" in client.get("/metrics").text


def test_product_validation_update_and_uniqueness(engine):
    with TestClient(create_app(engine)) as client:
        product_id = add_product(client, " milk-1 ")
        duplicate = client.post(
            "/api/products", json={"sku": "MILK-1", "name": "Duplicate", "category": "Dairy"}
        )
        assert duplicate.status_code == 409
        invalid = client.post(
            "/api/products", json={"sku": "bad sku", "name": "Invalid", "category": "Dairy"}
        )
        assert invalid.status_code == 422
        wrong_content_type = client.post("/api/products", data={"sku": "ALT"})
        assert wrong_content_type.status_code == 415
        updated = client.patch(
            f"/api/products/{product_id}",
            json={"name": "Whole milk 1 L", "category": "Chilled", "reorder_point": 3},
        )
        assert updated.json()["name"] == "Whole milk 1 L"
        assert updated.json()["sku"] == "MILK-1"
        assert client.get("/api/products/123456/forecast").status_code == 404


def test_fefo_retry_rollback_and_activity(engine, today):
    with TestClient(create_app(engine)) as client:
        pid = add_product(client)
        assert add_batch(client, pid, "LATER", 6, today + timedelta(days=5)).status_code == 201
        assert add_batch(client, pid, "EARLIER", 4, today).status_code == 201
        assert add_batch(client, pid, "EARLIER", 4, today).status_code == 409
        assert add_batch(client, pid, "EXPIRED", 4, today - timedelta(days=1)).status_code == 422
        operation = str(uuid4())
        sale = sell(client, pid, 7, operation_id=operation)
        assert sale.status_code == 201, sale.text
        assert sale.json()["details"]["allocations"] == [
            {"batch_code": "EARLIER", "units": 4},
            {"batch_code": "LATER", "units": 3},
        ]
        repeat = sell(client, pid, 7, operation_id=operation)
        assert repeat.json()["id"] == sale.json()["id"]
        assert sell(client, pid, 1, operation_id=operation).status_code == 409
        assert sell(client, pid, 4).status_code == 409
        assert sell(client, pid, True).status_code == 422
        row = client.get("/api/dashboard").json()["products"][0]
        assert row["sellable_units"] == 3 and row["low_stock"]
        assert [b["code"] for b in row["batches"]] == ["LATER"]
        audit = client.get("/api/movements?limit=2").json()
        assert [entry["kind"] for entry in audit["items"]] == ["sale", "receipt"]
        page = client.get(f"/api/movements?limit=2&before={audit['next_before']}").json()
        assert len(page["items"]) == 1 and page["next_before"] is None
    with transaction(engine) as session:
        assert session.get(SaleDay, (pid, today)).units == 7


def test_expired_stock_disposal_and_no_sale(engine, today, monkeypatch):
    with TestClient(create_app(engine)) as client:
        pid = add_product(client)
        assert add_batch(client, pid, "LAST-DAY", 5, today).status_code == 201
        monkeypatch.setattr(
            "inventory.main.store_now",
            lambda: datetime.combine(today + timedelta(days=1), datetime.min.time()),
        )
        row = client.get("/api/dashboard").json()["products"][0]
        assert row["expired_units"] == 5 and row["sellable_units"] == 0
        assert sell(client, pid, 1).status_code == 409
        discard_url = f"/api/batches/{row['batches'][0]['id']}/discards"
        operation = str(uuid4())
        body = {"units": 5, "reason": "Expired", "operation_id": operation}
        discarded = client.post(discard_url, json=body)
        assert discarded.status_code == 201
        assert client.post(discard_url, json=body).json()["id"] == discarded.json()["id"]
        assert client.get("/api/dashboard").json()["products"][0]["expired_units"] == 0


def test_concurrent_sales_cannot_oversell(engine, today):
    with TestClient(create_app(engine)) as client:
        pid = add_product(client)
        assert add_batch(client, pid, "ONE", 10, today).status_code == 201
        barrier = Barrier(2)

        def attempt():
            barrier.wait(timeout=5)
            return sell(client, pid, 7).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt) for _ in range(2)]
            assert sorted(task.result(timeout=20) for task in futures) == [201, 409]


def test_basic_auth_and_liveness_without_credentials(engine, monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "manager")
    monkeypatch.setenv("APP_PASSWORD", "strong-demo-pass")
    with TestClient(create_app(engine)) as client:
        assert client.get("/").status_code == 401
        assert "Basic" in client.get("/api/dashboard").headers["WWW-Authenticate"]
        assert client.get("/api/dashboard", auth=("manager", "strong-demo-pass")).status_code == 200
        assert client.get("/health/live").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_forecasts_publish_and_expiry_risk_moves_with_stock(engine, today):
    with TestClient(create_app(engine)) as client:
        pid = add_product(client)
        with transaction(engine, write=True) as session:
            session.add_all(
                SaleDay(product_id=pid, day=today - timedelta(days=offset), units=5, stockout=False)
                for offset in range(1, 15)
            )
        assert add_batch(client, pid, "THIS-WEEK", 17, today + timedelta(days=1)).status_code == 201
        assert run_forecast(engine, today) == 1
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["forecast_run"]["products_forecast"] == 1
        row = dashboard["products"][0]
        assert row["estimated_waste_units"] == 7
        assert row["shortfall_units"] == 25
        assert row["batches"][0]["estimated_waste_units"] == 7
        detail = client.get(f"/api/products/{pid}/forecast").json()
        assert detail["forecast"]["method"] == "moving_average"
        assert sum(point["units"] for point in detail["prediction"]) == 35
        assert sell(client, pid, 3).status_code == 201
        assert client.get("/api/dashboard").json()["products"][0]["estimated_waste_units"] == 7
        assert run_forecast(engine, today, force=True) == 1
        with transaction(engine) as session:
            assert len(session.scalars(select(ForecastRun)).all()) == 1


def test_init_preserves_existing_workspace(engine, today):
    with TestClient(create_app(engine)) as client:
        pid = add_product(client)
        initialize(engine, demo=True, today=today)
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["data_mode"] == "live"
        assert [item["id"] for item in dashboard["products"]] == [pid]
    with transaction(engine) as session:
        assert session.get(Product, pid).name == "Whole Milk"
