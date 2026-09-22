from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from itms.models.enums import (
    DependencyKind,
    MilestoneStatus,
    Priority,
    ProjectStatus,
    TaskStatus,
    TaskType,
)


class ProjectCreate(BaseModel):
    key: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNING
    priority: Priority = Priority.MEDIUM
    owner_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    budget_planned: float | None = Field(default=None, ge=0)
    budget_actual: float | None = Field(default=None, ge=0)


class ProjectUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: ProjectStatus | None = None
    priority: Priority | None = None
    owner_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    budget_planned: float | None = Field(default=None, ge=0)
    budget_actual: float | None = Field(default=None, ge=0)


class PhaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    order_index: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class PhaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    order_index: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = None


class MilestoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    due_date: date | None = None
    description: str = ""


class MilestoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    due_date: date | None = None
    description: str | None = None
    status: MilestoneStatus | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    task_type: TaskType = TaskType.TASK
    priority: Priority = Priority.MEDIUM
    phase_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimate_min: int = Field(default=0, ge=0)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    task_type: TaskType | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    phase_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimate_min: int | None = Field(default=None, ge=0)


class DependencyCreate(BaseModel):
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    dep_kind: DependencyKind = DependencyKind.FS
    lag_days: int = Field(default=0, ge=-365, le=365)


class CiLink(BaseModel):
    ci_id: uuid.UUID
    involvement: str = Field(default="затронут", max_length=64)


class TaskCiLink(BaseModel):
    ci_id: uuid.UUID
    role: str = Field(default="затронут", max_length=64)


class MemberWrite(BaseModel):
    employee_id: uuid.UUID
    role: str = Field(default="участник", max_length=64)


class TimeEntryCreate(BaseModel):
    employee_id: uuid.UUID
    work_date: date
    minutes: int = Field(ge=1, le=24 * 60)
    note: str = ""


class ProjectSummary(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    status: ProjectStatus
    priority: Priority
    owner_name: str | None
    start_date: date | None
    due_date: date | None
    progress_pct: float
    health: str
    task_count: int
    open_task_count: int


class ProjectRead(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str
    status: ProjectStatus
    priority: Priority
    owner_id: uuid.UUID | None
    owner_name: str | None
    start_date: date | None
    due_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    budget_planned: float | None
    budget_actual: float | None
    progress_pct: float
    task_count: int
    open_task_count: int


class PhaseRead(BaseModel):
    id: uuid.UUID
    name: str
    order_index: int
    start_date: date | None
    end_date: date | None
    status: str
    progress_pct: float


class MilestoneRead(BaseModel):
    id: uuid.UUID
    name: str
    due_date: date | None
    status: MilestoneStatus
    description: str
    completed_at: datetime | None


class TaskCiRead(BaseModel):
    ci_id: uuid.UUID
    code: str | None
    name: str
    role: str


class TimeEntryRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None
    work_date: date
    minutes: int
    note: str


class TaskRead(BaseModel):
    id: uuid.UUID
    number: int
    label: str
    title: str
    description: str
    task_type: TaskType
    status: TaskStatus
    priority: Priority
    phase_id: uuid.UUID | None
    milestone_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    assignee_name: str | None
    start_date: date | None
    due_date: date | None
    estimate_min: int
    spent_min: int
    progress_pct: float
    order_index: float
    cis: list[TaskCiRead]
    time_entries: list[TimeEntryRead]


class DependencyRead(BaseModel):
    id: uuid.UUID
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    dep_kind: DependencyKind
    lag_days: int


class ProjectCiRead(BaseModel):
    ci_id: uuid.UUID
    code: str | None
    name: str
    ci_type: str
    involvement: str


class MemberRead(BaseModel):
    employee_id: uuid.UUID
    full_name: str
    role: str


class ScheduleItem(BaseModel):
    task_id: uuid.UUID
    number: int
    label: str
    title: str
    phase_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    status: TaskStatus
    duration_days: int
    es: int
    ef: int
    ls: int
    lf: int
    float_days: int
    critical: bool
    start_date: date
    finish_date: date
    planned_start: date | None
    planned_finish: date | None


class ScheduleMilestone(BaseModel):
    id: uuid.UUID
    name: str
    due_date: date | None
    offset_days: int | None
    status: MilestoneStatus
    overdue: bool


class ScheduleView(BaseModel):
    anchor: date
    length_days: int
    items: list[ScheduleItem]
    milestones: list[ScheduleMilestone]


class FindingRead(BaseModel):
    rule: str
    level: str
    message: str
    entity_ids: list[str]


class HealthRead(BaseModel):
    status: str
    findings: list[FindingRead]


class ProjectView(BaseModel):
    project: ProjectRead
    phases: list[PhaseRead]
    milestones: list[MilestoneRead]
    tasks: list[TaskRead]
    dependencies: list[DependencyRead]
    cis: list[ProjectCiRead]
    members: list[MemberRead]
    schedule: ScheduleView
    health: HealthRead
