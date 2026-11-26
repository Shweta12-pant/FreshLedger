from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Code = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Units = Annotated[int, Field(strict=True, ge=1, le=100000)]
Threshold = Annotated[int, Field(strict=True, ge=0, le=100000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductDetails(Input):
    name: Name
    category: Category
    reorder_point: Threshold = 10


class ProductCreate(ProductDetails):
    sku: Code

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class StockMovement(Input):
    units: Units
    operation_id: UUID | None = None


class Receipt(StockMovement):
    batch_code: Code
    expires_on: date

    @field_validator("batch_code", mode="before")
    @classmethod
    def normalize_batch_code(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class Discard(StockMovement):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
