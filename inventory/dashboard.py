from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import timestamp
from .forecast import HORIZON
from .models import Batch, ForecastRun, Movement, Product, ProductForecast, SaleDay, StoreSetting
from .stock import get_product, movement_data, product_data


def project_stock(
    batches: list[Batch],
    demand: list[int],
    as_of: date,
) -> tuple[dict[int, int], int, date | None]:
    """Simulate sales, followed by end-of-day expiry, without changing actual stock."""
    balance = {batch.id: batch.quantity for batch in batches if batch.expires_on >= as_of}
    ordered = sorted(batches, key=lambda batch: (batch.expires_on, batch.id))
    risk, shortfall, first_shortfall = {}, 0, None
    for offset, units in enumerate(demand):
        day = as_of + timedelta(days=offset)
        for batch in ordered:
            available = balance.get(batch.id, 0)
            sold = min(available, units)
            if sold:
                balance[batch.id] -= sold
                units -= sold
            if units == 0:
                break
        if units:
            shortfall += units
            first_shortfall = first_shortfall or day
        for batch in ordered:
            if batch.expires_on == day:
                risk[batch.id] = balance.pop(batch.id, 0)
    return risk, shortfall, first_shortfall


def forecast_data(record: ProductForecast) -> dict:
    return {
        "method": record.method,
        "units": sum(record.daily_units),
        "history_days": record.history_days,
        "evaluation_points": record.evaluation_points,
        "selected_mae": record.selected_mae,
        "baseline_mae": record.baseline_mae,
        "forest_mae": record.forest_mae,
    }


def dashboard_data(session: Session, as_of: date) -> dict:
    products = session.scalars(select(Product).order_by(Product.name, Product.id)).all()
    batches_by_product = defaultdict(list)
    for batch in session.scalars(
        select(Batch).where(Batch.quantity > 0).order_by(Batch.expires_on, Batch.id)
    ):
        batches_by_product[batch.product_id].append(batch)
    forecasts = {
        forecast.product_id: forecast
        for forecast in session.scalars(select(ProductForecast).where(ProductForecast.as_of == as_of))
    }
    today_sales = {
        row.product_id: row.units for row in session.scalars(select(SaleDay).where(SaleDay.day == as_of))
    }
    run = session.get(ForecastRun, as_of)
    setting = session.get(StoreSetting, "data_mode")
    rows = []
    for product in products:
        batches = batches_by_product[product.id]
        forecast = forecasts.get(product.id)
        risk, shortfall, first_shortfall = {}, None, None
        if forecast:
            remaining_demand = forecast.daily_units.copy()
            remaining_demand[0] = max(0, remaining_demand[0] - today_sales.get(product.id, 0))
            risk, shortfall, first_shortfall = project_stock(batches, remaining_demand, as_of)
        sellable = sum(batch.quantity for batch in batches if batch.expires_on >= as_of)
        rows.append(
            product_data(product)
            | {
                "sellable_units": sellable,
                "expired_units": sum(batch.quantity for batch in batches if batch.expires_on < as_of),
                "expiring_units": sum(
                    batch.quantity for batch in batches if 0 <= (batch.expires_on - as_of).days <= 3
                ),
                "estimated_waste_units": sum(risk.values()) if forecast else None,
                "shortfall_units": shortfall,
                "first_shortfall": first_shortfall,
                "low_stock": sellable <= product.reorder_point,
                "forecast": forecast_data(forecast) if forecast else None,
                "batches": [
                    {
                        "id": batch.id,
                        "code": batch.code,
                        "quantity": batch.quantity,
                        "expires_on": batch.expires_on,
                        "days_to_expiry": (batch.expires_on - as_of).days,
                        "estimated_waste_units": risk.get(batch.id),
                    }
                    for batch in batches
                ],
            }
        )
    return {
        "as_of": as_of,
        "data_mode": setting.value if setting else "live",
        "forecast_run": (
            {"completed_at": timestamp(run.completed_at), "products_forecast": run.products_forecast}
            if run
            else None
        ),
        "summary": {
            "products": len(rows),
            "sellable_units": sum(row["sellable_units"] for row in rows),
            "expired_units": sum(row["expired_units"] for row in rows),
            "expiring_units": sum(row["expiring_units"] for row in rows),
            "estimated_waste_units": sum(row["estimated_waste_units"] or 0 for row in rows)
            if forecasts
            else None,
            "low_stock_products": sum(row["low_stock"] for row in rows),
            "projected_stockout_products": sum(bool(row["shortfall_units"]) for row in rows)
            if forecasts
            else None,
        },
        "products": rows,
    }


def product_history(session: Session, product_id: int, as_of: date) -> dict:
    product = get_product(session, product_id)
    start = as_of - timedelta(days=14)
    actuals = {
        row.day: row
        for row in session.scalars(
            select(SaleDay).where(
                SaleDay.product_id == product.id,
                SaleDay.day >= start,
                SaleDay.day < as_of,
            )
        )
    }
    forecast = session.get(ProductForecast, (as_of, product_id))
    history = []
    for offset in range((as_of - start).days):
        day = start + timedelta(days=offset)
        row = actuals.get(day)
        history.append(
            {"day": day, "units": row.units if row else None, "stockout": bool(row and row.stockout)}
        )
    return {
        "product": product_data(product),
        "history": history,
        "forecast": forecast_data(forecast) if forecast else None,
        "prediction": [
            {"day": as_of + timedelta(days=offset), "units": forecast.daily_units[offset]}
            for offset in range(HORIZON)
        ]
        if forecast
        else [],
    }


def latest_movements(session: Session, *, limit: int, before: int | None = None) -> dict:
    query = select(Movement, Product).join(Product, Product.id == Movement.product_id)
    if before is not None:
        query = query.where(Movement.id < before)
    rows = session.execute(query.order_by(Movement.id.desc()).limit(limit + 1)).all()
    return {
        "items": [movement_data(movement, product) for movement, product in rows[:limit]],
        "next_before": rows[limit - 1][0].id if len(rows) > limit else None,
    }
