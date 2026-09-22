"""Шаблоны проектов, сохранённые представления и сводка аналитики."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Invalid, NotFound
from itms.domain.templates import TEMPLATES
from itms.models.directory import Employee
from itms.models.enums import TaskStatus
from itms.models.projects import SavedView, Task
from itms.services import project_service

_CLOSED = (TaskStatus.DONE, TaskStatus.CANCELLED)
_BUCKETS = {"overdue", "today", "upcoming", "undated", "later"}


def template_catalog() -> list[dict[str, str]]:
    return [{"key": item["key"], "name": item["name"]} for item in TEMPLATES.values()]


async def create_from_template(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    spec = TEMPLATES.get(data["template"])
    if spec is None:
        raise Invalid("Неизвестный шаблон", code_hint="invalid")
    view = await project_service.create_project(
        session,
        {
            "key": data["key"],
            "name": data.get("name") or spec["name"],
            "description": spec["name"],
        },
    )
    project_id = view["project"]["id"]
    phase_ids: dict[str, uuid.UUID] = {}
    for index, name in enumerate(spec["phases"], start=1):
        view = await project_service.add_phase(
            session, project_id, {"name": name, "order_index": index}
        )
        phase = next(item for item in view["phases"] if item["name"] == name)
        phase_ids[name] = phase["id"]
    today = date.today()
    for task in spec["tasks"]:
        await project_service.add_task(
            session,
            project_id,
            {
                "title": task["title"],
                "phase_id": phase_ids[task["phase"]],
                "due_date": today + timedelta(days=task["due_in_days"]),
            },
        )
    for milestone in spec["milestones"]:
        await project_service.add_milestone(
            session,
            project_id,
            {
                "name": milestone["name"],
                "due_date": today + timedelta(days=milestone["due_in_days"]),
            },
        )
    return await project_service.project_view(session, project_id)


async def list_views(session: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SavedView).where(SavedView.user_id == user_id).order_by(SavedView.name)
        )
    ).scalars()
    return [_view(item) for item in rows]


async def save_view(
    session: AsyncSession, user_id: uuid.UUID, data: dict[str, Any]
) -> list[dict[str, Any]]:
    name = data["name"].strip()
    bucket = data.get("bucket") or None
    if not name or (bucket is not None and bucket not in _BUCKETS):
        raise Invalid("Укажите название представления", code_hint="invalid")
    session.add(
        SavedView(
            user_id=user_id,
            name=name,
            project_id=data.get("project_id"),
            status=data.get("status") or None,
            priority=data.get("priority") or None,
            bucket=bucket,
        )
    )
    await session.flush()
    return await list_views(session, user_id)


async def delete_view(
    session: AsyncSession, user_id: uuid.UUID, view_id: uuid.UUID
) -> list[dict[str, Any]]:
    row = await session.get(SavedView, view_id)
    if row is None or row.user_id != user_id:
        raise NotFound("Представление не найдено", entity_id=str(view_id))
    await session.delete(row)
    await session.flush()
    return await list_views(session, user_id)


async def analytics(session: AsyncSession) -> dict[str, Any]:
    tasks = list((await session.execute(select(Task))).scalars())
    today = date.today()
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    overdue = 0
    completed = 0
    open_count = 0
    load: dict[uuid.UUID, dict[str, int]] = {}
    for task in tasks:
        by_status[task.status.value] = by_status.get(task.status.value, 0) + 1
        by_priority[task.priority.value] = by_priority.get(task.priority.value, 0) + 1
        if task.status == TaskStatus.DONE:
            completed += 1
        if task.status not in _CLOSED:
            open_count += 1
            if task.due_date is not None and task.due_date < today:
                overdue += 1
            if task.assignee_id is not None:
                bucket = load.setdefault(task.assignee_id, {"open": 0, "estimate_min": 0})
                bucket["open"] += 1
                bucket["estimate_min"] += task.estimate_min
    names: dict[uuid.UUID, str] = {}
    if load:
        rows = (
            await session.execute(
                select(Employee.id, Employee.full_name).where(Employee.id.in_(load))
            )
        ).all()
        names = {row[0]: row[1] for row in rows}
    workload = [
        {"name": names.get(employee_id, ""), **counts}
        for employee_id, counts in sorted(load.items(), key=lambda item: -item[1]["estimate_min"])
    ]
    return {
        "by_status": by_status,
        "by_priority": by_priority,
        "open": open_count,
        "completed": completed,
        "overdue": overdue,
        "workload": workload,
    }


def _view(item: SavedView) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "project_id": item.project_id,
        "status": item.status,
        "priority": item.priority,
        "bucket": item.bucket,
    }
