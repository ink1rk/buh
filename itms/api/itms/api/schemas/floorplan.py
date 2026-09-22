from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class FloorplanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location_id: uuid.UUID
    width_mm: int = Field(ge=1000, le=200_000)
    height_mm: int = Field(ge=1000, le=200_000)


class FloorplanSummary(BaseModel):
    id: uuid.UUID
    name: str
    location_id: uuid.UUID
    location_name: str | None
    width_mm: int
    height_mm: int
    item_count: int


class FloorplanRead(BaseModel):
    id: uuid.UUID
    name: str
    location_id: uuid.UUID
    location_name: str | None
    width_mm: int
    height_mm: int


class FloorplanItemRead(BaseModel):
    id: uuid.UUID
    ci_id: uuid.UUID | None
    code: str | None
    name: str
    item_kind: str
    x: float
    y: float
    width: float
    height: float
    rotation: int


class FloorplanCandidate(BaseModel):
    ci_id: uuid.UUID
    code: str | None
    name: str
    item_kind: str
    width: float
    height: float


class FloorplanView(BaseModel):
    plan: FloorplanRead
    items: list[FloorplanItemRead]
    available: list[FloorplanCandidate]


class ItemPlace(BaseModel):
    ci_id: uuid.UUID
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    rotation: int = 0


class ItemMove(BaseModel):
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    rotation: int | None = None
