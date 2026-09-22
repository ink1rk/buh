"""Повторяющиеся задачи. Закрытие создаёт следующий экземпляр из определения."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Invalid
from itms.domain.recurrence import CADENCES, next_date
from itms.models.enums import Priority, TaskStatus, TaskType
from itms.models.projects import Project, Task, TaskRecurrence
from itms.services import notification_service, project_service


async def create_recurrence(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    await project_service.project_view(session, project_id)
    title = data["title"].strip()
    cadence = data["cadence"]
    if cadence not in CADENCES or not title:
        raise Invalid("Укажите название и период повтора", code_hint="invalid")
    interval = int(data.get("interval_count") or 1)
    weekday = data.get("weekday")
    month_day = data.get("month_day")
    first = next_date(
        cadence,
        after=date.today(),
        interval=interval,
        weekday=weekday,
        month_day=month_day,
        inclusive=True,
    )
    row = TaskRecurrence(
        project_id=project_id,
        title=title,
        description=(data.get("description") or "").strip(),
        cadence=cadence,
        interval_count=max(1, interval),
        weekday=weekday,
        month_day=month_day,
        priority=Priority(data.get("priority") or Priority.MEDIUM),
        assignee_id=data.get("assignee_id"),
        estimate_min=int(data.get("estimate_min") or 0),
        next_on=first,
        active=True,
    )
    session.add(row)
    await session.flush()
    await _open_instance(session, row, first)
    return await list_recurrences(session, project_id)


async def list_recurrences(session: AsyncSession, project_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(TaskRecurrence)
            .where(TaskRecurrence.project_id == project_id, TaskRecurrence.active.is_(True))
            .order_by(TaskRecurrence.title)
        )
    ).scalars()
    return [_row(item) for item in rows]


async def spawn_next(session: AsyncSession, task: Task) -> None:
    """После выполнения открывает следующий экземпляр, если повтор ещё активен."""
    if task.recurrence_id is None or task.status != TaskStatus.DONE:
        return
    row = await session.get(TaskRecurrence, task.recurrence_id)
    if row is None or not row.active:
        return
    open_one = (
        await session.execute(
            select(Task.id).where(
                Task.recurrence_id == row.id,
                Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
            )
        )
    ).scalar_one_or_none()
    if open_one is not None:
        return
    anchor = task.due_date or date.today()
    if anchor < date.today():
        anchor = date.today()
    due = next_date(
        row.cadence,
        after=anchor,
        interval=row.interval_count,
        weekday=row.weekday,
        month_day=row.month_day,
        inclusive=False,
    )
    row.next_on = due
    await _open_instance(session, row, due)


async def _open_instance(session: AsyncSession, row: TaskRecurrence, due: date) -> None:
    project = await session.get(Project, row.project_id)
    if project is None:
        return
    project.task_seq += 1
    task = Task(
        project_id=row.project_id,
        number=project.task_seq,
        title=row.title,
        description=row.description,
        task_type=TaskType.TASK,
        priority=row.priority,
        assignee_id=row.assignee_id,
        due_date=due,
        estimate_min=row.estimate_min,
        order_index=project.task_seq,
        recurrence_id=row.id,
    )
    session.add(task)
    await session.flush()
    if task.assignee_id:
        await notification_service.task_assigned(session, task)


def _row(item: TaskRecurrence) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "cadence": item.cadence,
        "interval_count": item.interval_count,
        "weekday": item.weekday,
        "month_day": item.month_day,
        "next_on": item.next_on,
        "priority": item.priority.value,
    }
