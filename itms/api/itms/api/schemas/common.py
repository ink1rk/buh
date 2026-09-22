from __future__ import annotations

import uuid
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Ok(BaseModel):
    ok: bool = True


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class Paging(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class Ref(ORMModel):
    id: uuid.UUID
    name: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
