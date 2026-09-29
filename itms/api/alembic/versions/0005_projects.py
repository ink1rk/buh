"""Проекты, задачи, зависимости и учёт времени

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-22 18:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIORITY = postgresql.ENUM(
    "LOW", "MEDIUM", "HIGH", "CRITICAL", name="priority", create_type=False
)
PROJECT_STATUS = postgresql.ENUM(
    "DRAFT", "PLANNING", "IN_PROGRESS", "ON_HOLD", "COMPLETED", "CANCELLED",
    name="project_status", create_type=False,
)
TASK_STATUS = postgresql.ENUM(
    "NEW", "IN_PROGRESS", "ON_HOLD", "BLOCKED", "REVIEW", "DONE", "CANCELLED",
    name="task_status", create_type=False,
)
TASK_TYPE = postgresql.ENUM(
    "TASK", "SUBTASK", "INCIDENT", "PROBLEM", "REQUEST", "MAINTENANCE", "CHANGE_TASK",
    name="task_type", create_type=False,
)
DEP_KIND = postgresql.ENUM(
    "FS", "SS", "FF", "SF", name="dependency_kind", create_type=False
)
MILESTONE_STATUS = postgresql.ENUM(
    "PLANNED", "REACHED", "MISSED", name="milestone_status", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE TYPE priority AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')")
    op.execute(
        "CREATE TYPE project_status AS ENUM "
        "('DRAFT', 'PLANNING', 'IN_PROGRESS', 'ON_HOLD', 'COMPLETED', 'CANCELLED')"
    )
    op.execute(
        "CREATE TYPE task_status AS ENUM "
        "('NEW', 'IN_PROGRESS', 'ON_HOLD', 'BLOCKED', 'REVIEW', 'DONE', 'CANCELLED')"
    )
    op.execute(
        "CREATE TYPE task_type AS ENUM "
        "('TASK', 'SUBTASK', 'INCIDENT', 'PROBLEM', 'REQUEST', 'MAINTENANCE', 'CHANGE_TASK')"
    )
    op.execute("CREATE TYPE dependency_kind AS ENUM ('FS', 'SS', 'FF', 'SF')")
    op.execute("CREATE TYPE milestone_status AS ENUM ('PLANNED', 'REACHED', 'MISSED')")

    op.create_table(
        "project",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("status", PROJECT_STATUS, server_default="PLANNING", nullable=False),
        sa.Column("priority", PRIORITY, server_default="MEDIUM", nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("actual_start_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("budget_planned", sa.Numeric(14, 2), nullable=True),
        sa.Column("budget_actual", sa.Numeric(14, 2), nullable=True),
        sa.Column("progress_pct", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("task_seq", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["employee.id"], name=op.f("fk_project_owner_id_employee"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project")),
        sa.UniqueConstraint("key", name="uq_project_key"),
    )
    op.create_table(
        "phase",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("order_index", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), server_default="PLANNED", nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_phase_project_id_project"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phase")),
    )
    op.create_table(
        "milestone",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", MILESTONE_STATUS, server_default="PLANNED", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_milestone_project_id_project"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestone")),
    )
    op.create_table(
        "task",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("phase_id", sa.UUID(), nullable=True),
        sa.Column("milestone_id", sa.UUID(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("task_type", TASK_TYPE, server_default="TASK", nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("status", TASK_STATUS, server_default="NEW", nullable=False),
        sa.Column("priority", PRIORITY, server_default="MEDIUM", nullable=False),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("reporter_id", sa.UUID(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("estimate_min", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("spent_min", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_index", sa.Numeric(12, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_task_project_id_project"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["phase_id"], ["phase.id"], name=op.f("fk_task_phase_id_phase"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestone.id"],
            name=op.f("fk_task_milestone_id_milestone"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["task.id"], name=op.f("fk_task_parent_id_task"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["employee.id"],
            name=op.f("fk_task_assignee_id_employee"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"], ["employee.id"],
            name=op.f("fk_task_reporter_id_employee"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task")),
        sa.UniqueConstraint("project_id", "number", name="uq_task_project_number"),
    )
    op.create_index("ix_task_project", "task", ["project_id", "status"])
    op.create_index("ix_task_assignee", "task", ["assignee_id", "status"])
    op.create_table(
        "task_dependency",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("predecessor_id", sa.UUID(), nullable=False),
        sa.Column("successor_id", sa.UUID(), nullable=False),
        sa.Column("dep_kind", DEP_KIND, server_default="FS", nullable=False),
        sa.Column("lag_days", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "predecessor_id <> successor_id", name=op.f("ck_task_dependency_distinct")
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_id"], ["task.id"],
            name=op.f("fk_task_dependency_predecessor_id_task"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["successor_id"], ["task.id"],
            name=op.f("fk_task_dependency_successor_id_task"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_dependency")),
        sa.UniqueConstraint("predecessor_id", "successor_id", name="uq_task_dependency_pair"),
    )
    op.create_table(
        "task_ci",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("ci_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(64), server_default="затронут", nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.id"], name=op.f("fk_task_ci_task_id_task"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ci_id"], ["ci.id"], name=op.f("fk_task_ci_ci_id_ci"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", "ci_id", name=op.f("pk_task_ci")),
    )
    op.create_table(
        "project_ci",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ci_id", sa.UUID(), nullable=False),
        sa.Column("involvement", sa.String(64), server_default="затронут", nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_project_ci_project_id_project"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ci_id"], ["ci.id"], name=op.f("fk_project_ci_ci_id_ci"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "ci_id", name=op.f("pk_project_ci")),
    )
    op.create_table(
        "project_member",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(64), server_default="участник", nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_project_member_project_id_project"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employee.id"],
            name=op.f("fk_project_member_employee_id_employee"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "employee_id", name=op.f("pk_project_member")),
    )
    op.create_table(
        "time_entry",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("minutes > 0", name=op.f("ck_time_entry_minutes")),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.id"], name=op.f("fk_time_entry_task_id_task"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employee.id"],
            name=op.f("fk_time_entry_employee_id_employee"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_time_entry")),
    )
    op.create_index("ix_time_entry_emp_date", "time_entry", ["employee_id", "work_date"])


def downgrade() -> None:
    op.drop_table("time_entry")
    op.drop_table("project_member")
    op.drop_table("project_ci")
    op.drop_table("task_ci")
    op.drop_table("task_dependency")
    op.drop_table("task")
    op.drop_table("milestone")
    op.drop_table("phase")
    op.drop_table("project")
    op.execute("DROP TYPE IF EXISTS milestone_status")
    op.execute("DROP TYPE IF EXISTS dependency_kind")
    op.execute("DROP TYPE IF EXISTS task_type")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.execute("DROP TYPE IF EXISTS project_status")
    op.execute("DROP TYPE IF EXISTS priority")
