from datetime import timedelta

import pytest
from sqlalchemy import select

from inventory.db import transaction
from inventory.import_sales import import_sales
from inventory.models import Product, SaleDay


def test_sales_import_is_atomic_and_idempotent(engine, today, tmp_path):
    with transaction(engine, write=True) as session:
        session.add(
            Product(sku="MILK", name="Milk", category="Dairy", reorder_point=2, created_on=today)
        )
    csv = tmp_path / "sales.csv"
    past = today - timedelta(days=1)
    csv.write_text(f"sku,date,units,stockout\nMILK,{past},0,0\nUNKNOWN,{past},2,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 3"), transaction(engine, write=True) as session:
        import_sales(session, csv, today)
    with transaction(engine) as session:
        assert not session.scalars(select(SaleDay)).all()
    csv.write_text(
        f"sku,date,units,stockout\nMILK,{past},0,0\nMILK,{past - timedelta(days=1)},2,1\n",
        encoding="utf-8",
    )
    with transaction(engine, write=True) as session:
        assert import_sales(session, csv, today) == (2, 0)
    with transaction(engine, write=True) as session:
        assert import_sales(session, csv, today) == (0, 2)
    with transaction(engine) as session:
        actual = session.scalars(select(SaleDay).order_by(SaleDay.day)).all()
        assert [(row.units, row.stockout) for row in actual] == [(2, True), (0, False)]
