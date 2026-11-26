from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import timestamp
from .models import Batch, Movement, Product, SaleDay
from .schemas import Discard, Receipt, StockMovement


class InventoryError(Exception):
    def __init__(self, message: str, status: int = 409) -> None:
        self.status = status
        super().__init__(message)


def get_product(session: Session, product_id: int, *, lock: bool = False) -> Product:
    query = select(Product).where(Product.id == product_id)
    product = session.scalar(query.with_for_update() if lock else query)
    if product is None:
        raise InventoryError("Product not found.", 404)
    return product


def product_data(product: Product) -> dict:
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "reorder_point": product.reorder_point,
    }


def movement_data(movement: Movement, product: Product) -> dict:
    return {
        "id": movement.id,
        "kind": movement.kind,
        "product_id": product.id,
        "product_name": product.name,
        "sku": product.sku,
        "units": movement.units,
        "details": movement.details,
        "created_at": timestamp(movement.created_at),
    }


def movement_request(session: Session, kind: str, product_id: int, data: StockMovement, **context):
    operation_id = str(data.operation_id or uuid4())
    request = data.model_dump(mode="json", exclude={"operation_id"}) | context
    previous = session.scalar(select(Movement).where(Movement.operation_id == operation_id))
    if previous is not None and (
        previous.kind != kind or previous.product_id != product_id or previous.request != request
    ):
        raise InventoryError("This operation ID already belongs to a different inventory update.")
    return operation_id, request, previous


def record_movement(
    session: Session,
    product: Product,
    kind: str,
    units: int,
    operation_id: str,
    request: dict,
    details: dict,
) -> dict:
    movement = Movement(
        product_id=product.id,
        kind=kind,
        units=units,
        operation_id=operation_id,
        request=request,
        details=details,
    )
    session.add(movement)
    session.flush()
    return movement_data(movement, product)


def receive(session: Session, product_id: int, data: Receipt, today: date) -> dict:
    product = get_product(session, product_id, lock=True)
    operation_id, request, previous = movement_request(session, "receipt", product_id, data)
    if previous is not None:
        return movement_data(previous, product)
    if data.expires_on < today:
        raise InventoryError("Expiry must be today or a later date.", 422)
    exists = session.scalar(
        select(Batch.id).where(Batch.product_id == product_id, Batch.code == data.batch_code)
    )
    if exists is not None:
        raise InventoryError("This product already has a batch with that code.")
    batch = Batch(
        product_id=product_id,
        code=data.batch_code,
        quantity=data.units,
        received_on=today,
        expires_on=data.expires_on,
    )
    session.add(batch)
    session.flush()
    return record_movement(
        session,
        product,
        "receipt",
        data.units,
        operation_id,
        request,
        {"batch_code": batch.code, "expires_on": batch.expires_on.isoformat()},
    )


def sell(session: Session, product_id: int, data: StockMovement, today: date) -> dict:
    product = get_product(session, product_id, lock=True)
    operation_id, request, previous = movement_request(session, "sale", product_id, data)
    if previous is not None:
        return movement_data(previous, product)
    batches = session.scalars(
        select(Batch)
        .where(Batch.product_id == product_id, Batch.expires_on >= today, Batch.quantity > 0)
        .order_by(Batch.expires_on, Batch.id)
        .with_for_update()
    ).all()
    available = sum(batch.quantity for batch in batches)
    if available < data.units:
        raise InventoryError(f"Only {available} sellable units are available.")
    remaining = data.units
    allocations = []
    for batch in batches:
        taken = min(remaining, batch.quantity)
        batch.quantity -= taken
        remaining -= taken
        allocations.append({"batch_code": batch.code, "units": taken})
        if remaining == 0:
            break
    daily = session.get(SaleDay, (product_id, today))
    if daily is None:
        daily = SaleDay(product_id=product_id, day=today, units=0, stockout=False)
        session.add(daily)
    daily.units += data.units
    daily.stockout = daily.stockout or available == data.units
    return record_movement(
        session,
        product,
        "sale",
        data.units,
        operation_id,
        request,
        {"allocations": allocations},
    )


def discard(session: Session, batch_id: int, data: Discard, today: date) -> dict:
    product_id = session.scalar(select(Batch.product_id).where(Batch.id == batch_id))
    if product_id is None:
        raise InventoryError("Batch not found.", 404)
    product = get_product(session, product_id, lock=True)
    operation_id, request, previous = movement_request(
        session,
        "discard",
        product_id,
        data,
        batch_id=batch_id,
    )
    if previous is not None:
        return movement_data(previous, product)
    batch = session.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
    if data.units > batch.quantity:
        raise InventoryError(f"Only {batch.quantity} units remain in this batch.")
    batch.quantity -= data.units
    if batch.expires_on >= today and batch.quantity == 0:
        sellable = session.scalar(
            select(Batch.id)
            .where(
                Batch.product_id == product_id,
                Batch.expires_on >= today,
                Batch.quantity > 0,
            )
            .limit(1)
        )
        if sellable is None:
            daily = session.get(SaleDay, (product_id, today))
            if daily is None:
                session.add(SaleDay(product_id=product_id, day=today, units=0, stockout=True))
            else:
                daily.stockout = True
    return record_movement(
        session,
        product,
        "discard",
        data.units,
        operation_id,
        request,
        {"batch_code": batch.code, "reason": data.reason},
    )
