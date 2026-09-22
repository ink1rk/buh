from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SnapshotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class GapRead(BaseModel):
    rule: str
    level: str
    message: str


class LivePowerRead(BaseModel):
    input_id: uuid.UUID | None
    input_name: str | None
    input_code: str | None
    estimated_w: int | None
    nameplate_w: int | None
    limit_w: int | None
    headroom_w: int | None
    target_w: int | None
    deficit_w: int | None
    required_w: int | None
    recommended_w: int | None
    added_w: int | None


class SnapshotRead(BaseModel):
    id: uuid.UUID
    name: str
    checksum: str
    taken_at: datetime
    estimated_w: int | None
    limit_w: int | None
    headroom_w: int | None
    target_w: int | None
    deficit_w: int | None


class ChangeItemRead(BaseModel):
    id: uuid.UUID
    operation: str
    entity_type: str
    entity_id: uuid.UUID | None
    payload: dict[str, Any]
    apply_status: str
    order_index: int


class PlanRead(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    applied_at: datetime | None
    base_snapshot_id: uuid.UUID | None
    result_snapshot_id: uuid.UUID | None
    gap: list[GapRead]
    items: list[ChangeItemRead]


class TransitionView(BaseModel):
    live: LivePowerRead
    snapshots: list[SnapshotRead]
    plans: list[PlanRead]
    gap: list[GapRead]
