from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine

from .db import transaction, utc_now
from .models import ForecastRun, Product, ProductForecast, SaleDay, StoreSetting

HORIZON = 7
HISTORY_WINDOW = 180
VALIDATION_DAYS = 21


@dataclass(frozen=True)
class Forecast:
    method: str
    daily_units: list[int]
    history_days: int
    evaluation_points: int = 0
    selected_mae: float | None = None
    baseline_mae: float | None = None
    forest_mae: float | None = None


def recent(history: dict[date, int], origin: date, window: int) -> list[int]:
    days = (origin - timedelta(days=offset) for offset in range(1, window + 1))
    return [history[day] for day in days if day in history]


def features(history: dict[date, int], origin: date, target: date) -> tuple[list[float], float] | None:
    previous_week = recent(history, origin, 7)
    if len(previous_week) < 3:
        return None
    average = mean(previous_week)
    monthly = mean(recent(history, origin, 28))
    weekday = [int(index == target.weekday()) for index in range(7)]
    lags = [history.get(origin - timedelta(days=offset), average) for offset in (1, 7, 14)]
    return [*weekday, *lags, average, monthly, (target - origin).days], average


def make_forest() -> RandomForestRegressor:
    return RandomForestRegressor(n_estimators=80, min_samples_leaf=4, random_state=42, n_jobs=1)


def predict_product(history: dict[date, int], as_of: date) -> Forecast | None:
    history = {
        day: units
        for day, units in history.items()
        if as_of - timedelta(days=HISTORY_WINDOW) <= day < as_of
    }
    if len(history) < 7:
        return None
    future = [features(history, as_of, as_of + timedelta(days=i)) for i in range(HORIZON)]
    if future[0] is None:
        return None
    forecast_inputs = [entry[0] for entry in future]
    baseline = [round(entry[1]) for entry in future]
    cutoff = as_of - timedelta(days=VALIDATION_DAYS)
    train_x, train_y, test_x, test_y, test_baseline = [], [], [], [], []
    for offset in range((as_of - min(history)).days):
        origin = min(history) + timedelta(days=offset)
        for step in range(HORIZON):
            target = origin + timedelta(days=step)
            if target not in history or origin < cutoff <= target:
                continue
            entry = features(history, origin, target)
            if entry is None:
                continue
            values, average = entry
            if target < cutoff:
                train_x.append(values)
                train_y.append(history[target])
            else:
                test_x.append(values)
                test_y.append(history[target])
                test_baseline.append(round(average))

    if len(history) < 56 or len(train_y) < 140 or len(test_y) < 35:
        return Forecast("moving_average", baseline, len(history))

    forest = make_forest().fit(train_x, train_y)
    forest_predictions = [round(value) for value in forest.predict(test_x)]
    forest_mae = mean(
        abs(actual - estimate) for actual, estimate in zip(test_y, forest_predictions, strict=True)
    )
    baseline_mae = mean(
        abs(actual - estimate) for actual, estimate in zip(test_y, test_baseline, strict=True)
    )
    if forest_mae < baseline_mae:
        # Entries that cross the holdout boundary were deliberately excluded from validation.
        # Refit on every available target before publishing the operational forecast.
        for origin_offset in range(1, HORIZON):
            origin = cutoff - timedelta(days=origin_offset)
            for step in range(origin_offset, HORIZON):
                target = origin + timedelta(days=step)
                entry = features(history, origin, target)
                if target in history and entry is not None:
                    train_x.append(entry[0])
                    train_y.append(history[target])
        forest.fit(train_x + test_x, train_y + test_y)
        predictions = [round(value) for value in forest.predict(forecast_inputs)]
        return Forecast(
            "random_forest",
            predictions,
            len(history),
            len(test_y),
            forest_mae,
            baseline_mae,
            forest_mae,
        )
    return Forecast(
        "moving_average",
        baseline,
        len(history),
        len(test_y),
        baseline_mae,
        baseline_mae,
        forest_mae,
    )


def run_forecast(engine: Engine, as_of: date, *, force: bool = False) -> int:
    started = utc_now()
    with transaction(engine) as session:
        existing = session.get(ForecastRun, as_of)
        if existing is not None and not force:
            return existing.products_forecast
        history = defaultdict(dict)
        for row in session.scalars(
            select(SaleDay).where(
                SaleDay.day >= as_of - timedelta(days=HISTORY_WINDOW),
                SaleDay.day < as_of,
                SaleDay.stockout.is_(False),
            )
        ):
            history[row.product_id][row.day] = row.units

    forecasts = {
        product_id: result
        for product_id, rows in history.items()
        if (result := predict_product(rows, as_of)) is not None
    }
    with transaction(engine, write=True) as session:
        # Store setup always creates this row. It serializes publication for concurrent workers.
        session.scalar(select(StoreSetting).where(StoreSetting.name == "data_mode").with_for_update())
        run = session.get(ForecastRun, as_of)
        if run is not None and (not force or run.completed_at >= started):
            return run.products_forecast
        if run is None:
            run = ForecastRun(as_of=as_of, completed_at=utc_now(), products_forecast=len(forecasts))
            session.add(run)
            session.flush()
        else:
            session.execute(delete(ProductForecast).where(ProductForecast.as_of == as_of))
            run.completed_at = utc_now()
            run.products_forecast = len(forecasts)
        session.add_all(
            ProductForecast(
                as_of=as_of,
                product_id=product.id,
                method=forecast.method,
                daily_units=forecast.daily_units,
                history_days=forecast.history_days,
                evaluation_points=forecast.evaluation_points,
                selected_mae=forecast.selected_mae,
                baseline_mae=forecast.baseline_mae,
                forest_mae=forecast.forest_mae,
            )
            for product in session.scalars(select(Product).where(Product.id.in_(forecasts)))
            if (forecast := forecasts.get(product.id)) is not None
        )
    return len(forecasts)
