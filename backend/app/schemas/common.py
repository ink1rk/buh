from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class MoneyAmount(BaseModel):
    amount: float
    currency: str = "RUB"


class DateRange(BaseModel):
    start: date
    end: date


class ErrorDetail(BaseModel):
    code: str
    detail: str
    meta: dict[str, Any] = {}
