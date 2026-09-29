from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ClusterWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    endpoint: str | None = None
    version: str | None = None
    environment: str = "PROD"
    project_id: uuid.UUID | None = None
    host_id: uuid.UUID | None = None
    notes: str | None = None


class ClusterRead(BaseModel):
    id: uuid.UUID
    name: str
    endpoint: str | None
    version: str | None
    environment: str
    project_id: uuid.UUID | None
    project_name: str | None
    host_id: uuid.UUID | None
    notes: str | None


class McpWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    endpoint: str = Field(min_length=1, max_length=500)
    transport: str = "HTTP"
    cluster_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    description: str | None = None


class McpRead(BaseModel):
    id: uuid.UUID
    name: str
    endpoint: str
    transport: str
    cluster_id: uuid.UUID | None
    cluster_name: str | None
    project_id: uuid.UUID | None
    project_name: str | None
    description: str | None


class AgentWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = "OPENCODE"
    endpoint: str | None = None
    model: str | None = None
    project_id: uuid.UUID | None = None
    description: str | None = None
    mcp_ids: list[uuid.UUID] = Field(default_factory=list)


class AgentRead(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    endpoint: str | None
    model: str | None
    project_id: uuid.UUID | None
    project_name: str | None
    description: str | None
    mcp_ids: list[uuid.UUID]
    mcp_names: list[str]


class RouteWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    path: str = "/"
    target_kind: str
    target_id: uuid.UUID | None = None
    target_url: str | None = None
    vlan_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    notes: str | None = None


class RouteRead(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    path: str
    target_kind: str
    target_id: uuid.UUID | None
    target_url: str | None
    target_name: str | None
    vlan_id: uuid.UUID | None
    vlan_label: str | None
    project_id: uuid.UUID | None
    project_name: str | None
    notes: str | None


class PlatformCounts(BaseModel):
    clusters: int
    mcp: int
    agents: int
    routes: int
    vlans: int
    vms: int


class PlatformOverview(BaseModel):
    clusters: list[ClusterRead]
    mcp: list[McpRead]
    agents: list[AgentRead]
    routes: list[RouteRead]
    counts: PlatformCounts
