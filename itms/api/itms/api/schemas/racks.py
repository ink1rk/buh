from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from itms.models.enums import RackFace, RackFormFactor, ZeroUSide


class RackCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = None
    location_id: uuid.UUID | None = None
    description: str | None = None
    u_height: int = Field(default=42, ge=1, le=60)
    width_in: int = Field(default=19, ge=10, le=23)
    depth_mm: int = Field(default=1000, ge=1)
    max_weight_kg: float | None = Field(default=None, ge=0)
    max_power_w: int | None = Field(default=None, ge=0)
    form_factor: RackFormFactor = RackFormFactor.CABINET
    descending_units: bool = False


class RackUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    location_id: uuid.UUID | None = None
    description: str | None = None
    u_height: int | None = Field(default=None, ge=1, le=60)
    width_in: int | None = Field(default=None, ge=10, le=23)
    depth_mm: int | None = Field(default=None, ge=1)
    max_weight_kg: float | None = None
    max_power_w: int | None = None
    form_factor: RackFormFactor | None = None
    descending_units: bool | None = None


class RackSummary(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    location_id: uuid.UUID | None
    location_path: str | None
    u_height: int
    form_factor: RackFormFactor
    used_front: int
    used_rear: int
    largest_free_front: int
    weight_kg: float
    max_weight_kg: float | None
    power_w: int
    max_power_w: int | None


class RackDetail(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    location_id: uuid.UUID | None
    location_path: str | None
    description: str | None
    u_height: int
    width_in: int
    depth_mm: int
    max_weight_kg: float | None
    max_power_w: int | None
    form_factor: RackFormFactor
    descending_units: bool


class FreeBlock(BaseModel):
    start: int
    length: int


class MountRead(BaseModel):
    id: uuid.UUID
    ci_id: uuid.UUID
    name: str
    code: str | None
    status: str
    device_role: str | None
    position_u: int
    u_height: int
    face: RackFace
    zero_u_side: ZeroUSide | None
    depth_mm: int | None
    weight_kg: float | None
    power_w: int | None
    is_reservation: bool


class WarehouseItem(BaseModel):
    ci_id: uuid.UUID
    name: str
    code: str | None
    status: str
    device_role: str | None
    u_height: int
    power_w: int | None
    weight_kg: float | None


class Capacity(BaseModel):
    u_height: int
    used_front: int
    used_rear: int
    weight_kg: float
    max_weight_kg: float | None
    power_w: int
    max_power_w: int | None


class RackElevation(BaseModel):
    rack: RackDetail
    mounts: list[MountRead]
    free_front: list[FreeBlock]
    free_rear: list[FreeBlock]
    capacity: Capacity
    warehouse: list[WarehouseItem]


class MountWrite(BaseModel):
    ci_id: uuid.UUID
    position_u: int = Field(default=1, ge=1, le=60)
    u_height: int | None = Field(default=None, ge=0, le=60)
    face: RackFace = RackFace.FRONT
    zero_u_side: ZeroUSide | None = None
    depth_mm: int | None = None
    weight_kg: float | None = None
    is_reservation: bool = False
    confirm_warnings: bool = False
