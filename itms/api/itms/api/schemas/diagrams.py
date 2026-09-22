from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from itms.api.schemas.common import ORMModel
from itms.models.enums import DiagramNodeKind, DiagramType


class DiagramCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    diagram_type: DiagramType = DiagramType.NETWORK
    location_id: uuid.UUID | None = None
    description: str | None = None
    autofill: bool = True


class DiagramUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class DiagramRead(ORMModel):
    id: uuid.UUID
    name: str
    diagram_type: DiagramType
    location_id: uuid.UUID | None
    description: str | None
    viewport: dict[str, Any]
    version: int


class LayoutNode(BaseModel):
    id: uuid.UUID
    x: float
    y: float


class LayoutWrite(BaseModel):
    version: int
    nodes: list[LayoutNode] = Field(default_factory=list)
    viewport: dict[str, Any] | None = None


class NodeCreate(BaseModel):
    ci_id: uuid.UUID


class DiagramNodeRead(BaseModel):
    id: uuid.UUID
    ci_id: uuid.UUID | None
    node_kind: DiagramNodeKind
    x: float
    y: float
    label: str
    code: str | None
    ci_type: str | None
    status: str | None
    criticality: str | None
    device_role: str | None
    hostname: str | None
    mgmt_ip: str | None


class DiagramEdgeRead(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    connection_id: uuid.UUID | None
    relation_id: uuid.UUID | None
    label: str | None
    medium: str | None
    status: str | None
    length_m: float | None
    is_redundant: bool
    redundancy_group: str | None
    rel_type: str | None


class DiagramFull(BaseModel):
    diagram: DiagramRead
    nodes: list[DiagramNodeRead]
    edges: list[DiagramEdgeRead]
