from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    template: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=500)


class RecurrenceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    cadence: str
    interval_count: int = Field(default=1, ge=1, le=366)
    weekday: int | None = Field(default=None, ge=0, le=6)
    month_day: int | None = Field(default=None, ge=1, le=31)
    priority: str = "MEDIUM"
    assignee_id: uuid.UUID | None = None
    estimate_min: int = Field(default=0, ge=0)


class RecurrenceRead(BaseModel):
    id: uuid.UUID
    title: str
    cadence: str
    interval_count: int
    weekday: int | None
    month_day: int | None
    next_on: date
    priority: str


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_id: uuid.UUID | None = None
    status: str | None = None
    priority: str | None = None
    bucket: str | None = None


class SavedViewRead(BaseModel):
    id: uuid.UUID
    name: str
    project_id: uuid.UUID | None
    status: str | None
    priority: str | None
    bucket: str | None


class WorkloadRow(BaseModel):
    name: str
    open: int
    estimate_min: int


class Analytics(BaseModel):
    by_status: dict[str, int]
    by_priority: dict[str, int]
    open: int
    completed: int
    overdue: int
    workload: list[WorkloadRow]
