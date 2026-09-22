from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from itms.api.schemas.common import ORMModel
from itms.models.enums import AuditAction, ImportStatus, ImportTarget


class AuditChangeRead(ORMModel):
    field: str
    old_value: Any | None
    new_value: Any | None


class AuditLogRead(ORMModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_kind: str
    actor_label: str | None
    entity_type: str
    entity_id: uuid.UUID | None
    entity_label: str | None
    action: AuditAction
    change_id: uuid.UUID | None
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    document_id: uuid.UUID | None
    reason: str | None
    comment: str | None
    source: str
    changes: list[AuditChangeRead] = Field(default_factory=list)


class SearchHitRead(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    title: str
    subtitle: str | None
    snippet: str | None
    rank: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitRead]
    counts: dict[str, int] = Field(default_factory=dict)


class ImportJobRead(ORMModel):
    id: uuid.UUID
    target: ImportTarget
    status: ImportStatus
    filename: str
    columns: list[str]
    mapping: dict[str, str]
    rows_total: int
    rows_valid: int
    rows_invalid: int
    rows_created: int
    rows_updated: int
    errors: list[dict[str, Any]]
    preview: list[dict[str, Any]]
    created_at: datetime
    applied_at: datetime | None


class ImportMappingUpdate(BaseModel):
    mapping: dict[str, str]


class DashboardCounters(BaseModel):
    ci_total: int
    ci_critical: int
    ci_attention: int
    locations: int
    employees_active: int
    documents: int
    documents_review_due: int


class KeyCount(BaseModel):
    key: str
    count: int


class ActivityItem(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_label: str | None
    entity_type: str
    entity_id: uuid.UUID | None
    entity_label: str | None
    action: AuditAction
    reason: str | None


class DashboardRead(BaseModel):
    counters: DashboardCounters
    ci_by_type: list[KeyCount]
    ci_by_status: list[KeyCount]
    ci_by_criticality: list[KeyCount]
    data_quality: dict[str, Any]
    recent_activity: list[ActivityItem]


class MetaResponse(BaseModel):
    """Справочники перечислений для интерфейса: значения и переводы берутся из словаря."""

    ci_types: list[str]
    ci_statuses: list[str]
    ci_status_transitions: dict[str, list[str]]
    criticalities: list[str]
    environments: list[str]
    location_types: list[str]
    location_parents: dict[str, list[str]]
    relation_types: list[str]
    document_kinds: list[str]
    document_statuses: list[str]
    employee_statuses: list[str]
    support_lines: list[str]
    user_roles: list[str]
    audit_actions: list[str]
    power_defaults: dict[str, float | int]
