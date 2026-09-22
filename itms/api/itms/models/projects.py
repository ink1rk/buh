"""Проекты и универсальные задачи.

Проект — переход инфраструктуры, поэтому он ссылается на объекты через project_ci.
Задача не является объектом CMDB: связь с оборудованием живёт в task_ci.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import Base, TimestampMixin, uuid_pk
from itms.models.enums import (
    DependencyKind,
    MilestoneStatus,
    Priority,
    ProjectStatus,
    TaskStatus,
    TaskType,
)


class Project(Base, TimestampMixin):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[ProjectStatus] = mapped_column(
        ENUM(ProjectStatus, name="project_status", create_type=False),
        nullable=False,
        default=ProjectStatus.PLANNING,
    )
    priority: Mapped[Priority] = mapped_column(
        ENUM(Priority, name="priority", create_type=False),
        nullable=False,
        default=Priority.MEDIUM,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    actual_start_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    budget_planned: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_actual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    progress_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default=text("0")
    )
    task_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class Phase(Base):
    __tablename__ = "phase"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED")


class Milestone(Base):
    __tablename__ = "milestone"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[MilestoneStatus] = mapped_column(
        ENUM(MilestoneStatus, name="milestone_status", create_type=False),
        nullable=False,
        default=MilestoneStatus.PLANNED,
    )
    completed_at: Mapped[datetime | None] = mapped_column()
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class Task(Base, TimestampMixin):
    __tablename__ = "task"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_task_project_number"),
        Index("ix_task_project", "project_id", "status"),
        Index("ix_task_assignee", "assignee_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("phase.id", ondelete="SET NULL"))
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestone.id", ondelete="SET NULL")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"))
    task_type: Mapped[TaskType] = mapped_column(
        ENUM(TaskType, name="task_type", create_type=False),
        nullable=False,
        default=TaskType.TASK,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[TaskStatus] = mapped_column(
        ENUM(TaskStatus, name="task_status", create_type=False),
        nullable=False,
        default=TaskStatus.NEW,
    )
    priority: Mapped[Priority] = mapped_column(
        ENUM(Priority, name="priority", create_type=False),
        nullable=False,
        default=Priority.MEDIUM,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    estimate_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    spent_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    completed_at: Mapped[datetime | None] = mapped_column()
    order_index: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=0, server_default=text("0")
    )


class TaskDependency(Base):
    __tablename__ = "task_dependency"
    __table_args__ = (
        CheckConstraint("predecessor_id <> successor_id", name="ck_task_dependency_distinct"),
        UniqueConstraint("predecessor_id", "successor_id", name="uq_task_dependency_pair"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), nullable=False
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), nullable=False
    )
    dep_kind: Mapped[DependencyKind] = mapped_column(
        ENUM(DependencyKind, name="dependency_kind", create_type=False),
        nullable=False,
        default=DependencyKind.FS,
    )
    lag_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )


class TaskCi(Base):
    __tablename__ = "task_ci"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), primary_key=True
    )
    ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="затронут")


class ProjectCi(Base):
    __tablename__ = "project_ci"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True
    )
    involvement: Mapped[str] = mapped_column(String(64), nullable=False, default="затронут")


class ProjectMember(Base):
    __tablename__ = "project_member"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="участник")


class TimeEntry(Base, TimestampMixin):
    __tablename__ = "time_entry"
    __table_args__ = (
        CheckConstraint("minutes > 0", name="ck_time_entry_minutes"),
        Index("ix_time_entry_emp_date", "employee_id", "work_date"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
