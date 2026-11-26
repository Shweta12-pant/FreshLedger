from csv import DictReader
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product, SaleDay, StoreSetting


def import_sales(session: Session, file: Path, today: date) -> tuple[int, int]:
    setting = session.get(StoreSetting, "data_mode")
    if setting is None or setting.value != "live":
        raise ValueError("Initialize a live workspace before importing historical sales.")
    products = dict(session.execute(select(Product.sku, Product.id)).tuples().all())
    inserted, unchanged = 0, 0
    with file.open(encoding="utf-8-sig", newline="") as stream:
        reader = DictReader(stream, strict=True)
        if reader.fieldnames != ["sku", "date", "units", "stockout"]:
            raise ValueError("The CSV header must be sku,date,units,stockout.")
        for row in reader:
            try:
                sku = row["sku"].strip().upper()
                if sku not in products:
                    raise ValueError(f"unknown SKU {sku!r}")
                day = date.fromisoformat(row["date"])
                if day >= today or day.isoformat() != row["date"]:
                    raise ValueError("date must be a completed store day in YYYY-MM-DD format")
                units = int(row["units"])
                if not 0 <= units <= 1_000_000:
                    raise ValueError("units must be between 0 and 1,000,000")
                if row["stockout"] not in {"0", "1"} or None in row:
                    raise ValueError("stockout must be 0 or 1 and each row must have four columns")
                stockout = row["stockout"] == "1"
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"CSV line {reader.line_num}: {exc}") from exc
            product_id = products[sku]
            existing = session.get(SaleDay, (product_id, day))
            if existing is not None:
                if (existing.units, existing.stockout) != (units, stockout):
                    raise ValueError(
                        f"CSV line {reader.line_num}: sales already exist with different values."
                    )
                unchanged += 1
                continue
            session.add(SaleDay(product_id=product_id, day=day, units=units, stockout=stockout))
            inserted += 1
    return inserted, unchanged
