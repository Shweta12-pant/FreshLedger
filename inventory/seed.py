from datetime import date, timedelta
from random import Random
from uuid import uuid4

from sqlalchemy.orm import Session

from .models import Batch, Movement, Product, SaleDay

# SKU, name, category, minimum stock, weekday sales range centre, quantities and expiry offsets.
CATALOG = [
    ("DAI-101", "Whole Milk", "Dairy", 24, 14, [(38, 1), (56, 7)]),
    ("BAK-201", "Sourdough Bread", "Bakery", 16, 10, [(36, 2), (31, 5)]),
    ("DAI-102", "Greek Yogurt", "Dairy", 18, 8, [(55, 3), (36, 13)]),
    ("PRO-301", "Baby Spinach", "Produce", 12, 7, [(11, 1), (6, 5)]),
    ("PRO-302", "Strawberries", "Produce", 12, 11, [(9, 0), (22, 4)]),
    ("CHI-401", "Fresh Orange Juice", "Chilled", 10, 6, [(24, 4), (43, 8)]),
    ("DAI-103", "Unsalted Butter", "Dairy", 10, 4, [(32, 18), (19, 24)]),
    ("CHI-402", "Classic Hummus", "Chilled", 12, 5, [(4, -1), (22, 6)]),
]


def seed_demo(session: Session, today: date) -> None:
    rng = Random(728)
    start = today - timedelta(days=120)
    for sku, name, category, threshold, average, batches in CATALOG:
        product = Product(
            sku=sku, name=name, category=category, reorder_point=threshold, created_on=start
        )
        session.add(product)
        session.flush()
        for offset in range((today - start).days):
            day = start + timedelta(days=offset)
            weekend = round(average * 0.65) if day.weekday() in (4, 5) else 0
            weekly_dip = -2 if day.weekday() == 1 else 0
            stockout = rng.random() < 0.025
            units = (
                rng.randint(0, 3)
                if stockout
                else max(0, average + weekend + weekly_dip + rng.randint(-2, 2))
            )
            session.add(SaleDay(product_id=product.id, day=day, units=units, stockout=stockout))
        for index, (quantity, days_to_expiry) in enumerate(batches, start=1):
            batch = Batch(
                product_id=product.id,
                code=f"{sku}-{index:02}",
                quantity=quantity,
                received_on=today - timedelta(days=2),
                expires_on=today + timedelta(days=days_to_expiry),
            )
            session.add(batch)
            session.add(
                Movement(
                    operation_id=str(uuid4()),
                    product_id=product.id,
                    kind="receipt",
                    units=quantity,
                    request={"source": "demo"},
                    details={"batch_code": batch.code, "expires_on": batch.expires_on.isoformat()},
                )
            )
