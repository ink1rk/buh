from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from itms.api.schemas.common import ORMModel
from itms.models.enums import (
    CiStatus,
    CiType,
    Criticality,
    Environment,
    LocationType,
    RelationType,
)


class LocationBrief(ORMModel):
    id: uuid.UUID
    name: str
    path: str
    location_type: LocationType


class CiBase(BaseModel):
    code: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    criticality: Criticality = Criticality.MEDIUM
    environment: Environment = Environment.PROD
    location_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None
    vendor: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    inventory_number: str | None = Field(default=None, max_length=64)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    valid_from: date | None = None
    valid_to: date | None = None
    tags: list[str] = Field(default_factory=list)


class CiCreate(CiBase):
    ci_type: CiType
    status: CiStatus = CiStatus.ACTIVE


class CiUpdate(BaseModel):
    code: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: CiStatus | None = None
    criticality: Criticality | None = None
    environment: Environment | None = None
    location_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    inventory_number: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    tags: list[str] | None = None
    version: int | None = Field(default=None, description="Ожидаемая версия объекта")


class CiRead(ORMModel):
    id: uuid.UUID
    ci_type: CiType
    code: str | None
    name: str
    status: CiStatus
    criticality: Criticality
    environment: Environment
    location_id: uuid.UUID | None
    location: LocationBrief | None = None
    owner_employee_id: uuid.UUID | None
    vendor: str | None
    model: str | None
    serial_number: str | None
    inventory_number: str | None
    description: str | None
    attributes: dict[str, Any]
    valid_from: date | None
    valid_to: date | None
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)


class RelationCreate(BaseModel):
    source_ci_id: uuid.UUID
    target_ci_id: uuid.UUID
    rel_type: RelationType
    criticality: Criticality | None = None
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class RelatedCi(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    ci_type: CiType
    status: CiStatus


class RelatedItem(BaseModel):
    relation_id: uuid.UUID
    rel_type: RelationType
    direction: str
    criticality: Criticality
    description: str | None
    ci: RelatedCi


class ProvenanceEntry(BaseModel):
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_label: str | None
    actor_kind: str
    action: str
    field: str
    old_value: Any | None
    new_value: Any | None
    reason: str | None
    change_id: uuid.UUID | None
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    document_id: uuid.UUID | None
    source: str


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location_type: LocationType
    parent_id: uuid.UUID | None = None
    code: str | None = None
    address: str | None = None
    area_m2: float | None = None
    responsible_employee_id: uuid.UUID | None = None
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class LocationUpdate(BaseModel):
    name: str | None = None
    parent_id: uuid.UUID | None = None
    code: str | None = None
    address: str | None = None
    area_m2: float | None = None
    responsible_employee_id: uuid.UUID | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None


class LocationRead(ORMModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    location_type: LocationType
    name: str
    code: str | None
    path: str
    depth: int
    address: str | None
    area_m2: float | None
    responsible_employee_id: uuid.UUID | None
    description: str | None
    archived_at: datetime | None


class LocationNode(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    location_type: LocationType
    name: str
    code: str | None
    path: str
    depth: int
    ci_count: int
    children: list[LocationNode] = Field(default_factory=list)


LocationNode.model_rebuild()


class TagRead(ORMModel):
    id: uuid.UUID
    name: str
    color: str | None
    description: str | None
