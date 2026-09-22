"""Проекты и универсальные задачи.

Проект — переход инфраструктуры, поэтому он ссылается на объекты через project_ci.
Задача не является объектом CMDB: связь с оборудованием живёт в task_ci.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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
    recurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_recurrence.id", ondelete="SET NULL")
    )
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


class TaskComment(Base):
    """Комментарий к задаче. Текст не переписывается задним числом."""

    __tablename__ = "task_comment"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Notification(Base):
    """Сообщение внутри системы. Почта и мессенджеры подключаются к этой же записи позже."""

    __tablename__ = "notification"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('assigned', 'status', 'comment', 'mention')",
            name="kind",
        ),
        Index("ix_notification_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE")
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskCheck(Base):
    """Пункт чеклиста. Прогресс задачи по статусу от него не зависит."""

    __tablename__ = "task_check"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class TaskRecurrence(Base, TimestampMixin):
    """Определение повтора. Выполненная задача его не копирует, а порождает новый экземпляр."""

    __tablename__ = "task_recurrence"
    __table_args__ = (
        CheckConstraint("cadence IN ('daily', 'weekly', 'monthly')", name="cadence"),
        CheckConstraint("interval_count >= 1", name="interval"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    cadence: Mapped[str] = mapped_column(String(16), nullable=False)
    interval_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    weekday: Mapped[int | None] = mapped_column(SmallInteger)
    month_day: Mapped[int | None] = mapped_column(SmallInteger)
    priority: Mapped[Priority] = mapped_column(
        ENUM(Priority, name="priority", create_type=False),
        nullable=False,
        default=Priority.MEDIUM,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    estimate_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_on: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class SavedView(Base, TimestampMixin):
    """Именованный фильтр задач владельца представления."""

    __tablename__ = "saved_view"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE")
    )
    status: Mapped[str | None] = mapped_column(String(32))
    priority: Mapped[str | None] = mapped_column(String(32))
    bucket: Mapped[str | None] = mapped_column(String(32))

