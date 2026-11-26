from datetime import date, timedelta

from inventory.dashboard import project_stock
from inventory.forecast import predict_product
from inventory.models import Batch

TODAY = date(2026, 8, 1)


def test_too_little_data_and_recent_average_fallback():
    assert predict_product({TODAY - timedelta(days=1): 5}, TODAY) is None
    history = {TODAY - timedelta(days=n): 4 for n in range(1, 14)}
    forecast = predict_product(history, TODAY)
    assert forecast.method == "moving_average"
    assert forecast.daily_units == [4] * 7
    assert forecast.forest_mae is None


def test_weekly_pattern_beats_baseline_and_ignores_future_sales():
    history = {
        TODAY - timedelta(days=n): 30 if (TODAY - timedelta(days=n)).weekday() >= 5 else 5
        for n in range(1, 101)
    }
    forecast = predict_product(history, TODAY)
    assert forecast.method == "random_forest"
    assert forecast.forest_mae < forecast.baseline_mae
    assert forecast.daily_units == [30, 30, 5, 5, 5, 5, 5]
    history[TODAY] = 4900
    history[TODAY + timedelta(days=1)] = 5000
    assert predict_product(history, TODAY) == forecast


def test_baseline_wins_a_tie_on_flat_history():
    history = {TODAY - timedelta(days=n): 6 for n in range(1, 101)}
    forecast = predict_product(history, TODAY)
    assert forecast.method == "moving_average"
    assert forecast.forest_mae == forecast.baseline_mae == 0


def test_projection_removes_batches_after_expiry_and_never_changes_stock():
    expired = Batch(id=1, quantity=100, expires_on=TODAY - timedelta(days=1))
    early = Batch(id=2, quantity=8, expires_on=TODAY)
    late = Batch(id=3, quantity=5, expires_on=TODAY + timedelta(days=7))
    risk, shortfall, first = project_stock([late, expired, early], [4, 6, 5], TODAY)
    assert risk == {2: 4}
    assert shortfall == 6
    assert first == TODAY + timedelta(days=1)
    assert (early.quantity, late.quantity, expired.quantity) == (8, 5, 100)
