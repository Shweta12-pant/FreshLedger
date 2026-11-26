from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .db import utc_now


class Base(DeclarativeBase):
    pass


class StoreSetting(Base):
    __tablename__ = "store_settings"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(40))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(40))
    reorder_point: Mapped[int] = mapped_column(Integer)
    created_on: Mapped[date] = mapped_column(Date)


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("product_id", "code"),
        CheckConstraint("quantity >= 0"),
        Index("ix_batches_product_expiry", "product_id", "expires_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    code: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(Integer)
    received_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)


class SaleDay(Base):
    __tablename__ = "daily_sales"
    __table_args__ = (CheckConstraint("units >= 0"),)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    units: Mapped[int] = mapped_column(Integer)
    stockout: Mapped[bool] = mapped_column(Boolean, default=False)


class Movement(Base):
    __tablename__ = "movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(36), unique=True)
    kind: Mapped[str] = mapped_column(String(12))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    units: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON)
    request: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(MySQLDateTime(fsp=6), "mysql")
    )
    products_forecast: Mapped[int] = mapped_column(Integer)


class ProductForecast(Base):
    __tablename__ = "product_forecasts"

    as_of: Mapped[date] = mapped_column(
        ForeignKey("forecast_runs.as_of", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    method: Mapped[str] = mapped_column(String(24))
    daily_units: Mapped[list] = mapped_column(JSON)
    selected_mae: Mapped[float | None] = mapped_column(Float)
    baseline_mae: Mapped[float | None] = mapped_column(Float)
    forest_mae: Mapped[float | None] = mapped_column(Float)
    history_days: Mapped[int] = mapped_column(Integer)
    evaluation_points: Mapped[int] = mapped_column(Integer)
