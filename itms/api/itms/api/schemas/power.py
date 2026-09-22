from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from itms.models.enums import FeedSide, PhaseLabel, PowerNodeType


class PowerNodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = None
    node_type: PowerNodeType
    location_id: uuid.UUID | None = None
    description: str | None = None
    parent_device_id: uuid.UUID | None = None
    rack_id: uuid.UUID | None = None
    feed_side: FeedSide = FeedSide.SINGLE
    voltage_v: float | None = None
    phases: int = 1
    phase_label: PhaseLabel | None = None
    rated_current_a: float | None = None
    derating_factor: float = 0.8
    power_factor: float | None = None
    efficiency: float | None = None
    power_nameplate_w: int | None = Field(default=None, ge=0)
    power_max_w: int | None = Field(default=None, ge=0)
    max_load_w: int | None = Field(default=None, ge=0)
    ups_capacity_va: int | None = Field(default=None, ge=0)
    ups_capacity_w: int | None = Field(default=None, ge=0)
    utilization: float | None = Field(default=None, gt=0, le=1)
    notes: str | None = None


class PowerNodeCreated(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str


class PowerLinkCreate(BaseModel):
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID


class PowerLinkCreated(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID


class PowerFeedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    side: FeedSide
    root_node_id: uuid.UUID
    location_id: uuid.UUID | None = None
    is_protected: bool = False
    description: str | None = None


class PowerFeedCreated(BaseModel):
    id: uuid.UUID
    name: str
    side: FeedSide


class PowerMeasurementCreate(BaseModel):
    node_id: uuid.UUID
    power_w: int | None = Field(default=None, ge=0)
    measured_at: datetime | None = None
    source: str = "MANUAL"
    current_a: float | None = None
    voltage_v: float | None = None
    power_factor: float | None = None
    phase_label: PhaseLabel | None = None
    instrument: str | None = None
    note: str | None = None
    is_peak: bool = False


class PowerMeasurementCreated(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    power_w: int | None


class ScenarioItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    nameplate_w: int = Field(ge=0)
    quantity: int = Field(default=1, ge=1, le=1000)
    utilization: float = Field(gt=0, le=1)
    behind_new_ups: bool = True


class PowerScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    project_id: uuid.UUID | None = None
    charge_w: int = Field(default=0, ge=0)
    ups_efficiency: float | None = None
    reserve: float = Field(default=0.2, ge=0, lt=1)
    items: list[ScenarioItemCreate] = Field(default_factory=list)


class PowerScenarioCreated(BaseModel):
    id: uuid.UUID
    name: str


class PowerWarning(BaseModel):
    code: str
    message: str


class PowerNodeRow(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    node_type: str
    feed_id: uuid.UUID | None
    feed_name: str | None
    feed_side: str
    nameplate_w: int
    estimated_w: int
    inlet_w: int
    used_w: int
    limit_w: int | None
    headroom_w: int | None
    current_a: float | None
    disbalance_pct: float | None
    phases_w: dict[str, int]
    value_source: str
    measured_coverage_pct: float
    warnings: list[PowerWarning]
    trace: list[dict[str, Any]]
    failover: str | None
    failover_detail: str | None
    estimated_with_charge_w: int


class PowerFeedRow(BaseModel):
    id: uuid.UUID
    name: str
    side: str
    root_node_id: uuid.UUID
    root_name: str | None
    is_protected: bool
    description: str


class PowerLinkRow(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    source_name: str | None
    target_name: str | None


class ScenarioItemRow(BaseModel):
    id: uuid.UUID
    name: str
    nameplate_w: int
    quantity: int
    utilization: float
    behind_new_ups: bool


class PowerScenarioRow(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    project_id: uuid.UUID | None
    project_key: str | None
    charge_w: int
    ups_efficiency: float | None
    reserve: float
    items: list[ScenarioItemRow]
    forecast: dict[str, int | float] | None


class PowerOverview(BaseModel):
    nodes: list[PowerNodeRow]
    feeds: list[PowerFeedRow]
    links: list[PowerLinkRow]
    primary_input_id: uuid.UUID | None
    scenarios: list[PowerScenarioRow]
