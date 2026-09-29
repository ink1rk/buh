"""Уведомления о задачах. Получатель — учётная запись, привязанная к сотруднику.

Автор действия себе ничего не получает. Внешние каналы (почта, Telegram, push)
читают ту же таблицу и в этом слое не вызываются.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.context import current_context
from itms.core.errors import NotFound
from itms.models.directory import UserAccount
from itms.models.projects import Notification, Project, Task


async def task_assigned(session: AsyncSession, task: Task) -> None:
    if task.assignee_id is None:
        return
    label, title = await _heading(session, task)
    await _push(
        session,
        await _users_for_employees(session, [task.assignee_id]),
        kind="assigned",
        title=f"{label} {title}",
        body="",
        project_id=task.project_id,
        task_id=task.id,
    )


async def task_status(session: AsyncSession, task: Task, before: str, after: str) -> None:
    if task.assignee_id is None or before == after:
        return
    label, title = await _heading(session, task)
    await _push(
        session,
        await _users_for_employees(session, [task.assignee_id]),
        kind="status",
        title=f"{label} {title}",
        body=f"{before} → {after}",
        project_id=task.project_id,
        task_id=task.id,
    )


async def task_comment(session: AsyncSession, task: Task, body: str) -> None:
    mentioned = await _mentioned(session, body)
    assignee_users = (
        await _users_for_employees(session, [task.assignee_id]) if task.assignee_id else []
    )
    mentioned_ids = set(mentioned)
    comment_users = [user_id for user_id in assignee_users if user_id not in mentioned_ids]
    label, title = await _heading(session, task)
    text = body.strip()[:1000]
    await _push(
        session,
        mentioned,
        kind="mention",
        title=f"{label} {title}",
        body=text,
        project_id=task.project_id,
        task_id=task.id,
    )
    await _push(
        session,
        comment_users,
        kind="comment",
        title=f"{label} {title}",
        body=text,
        project_id=task.project_id,
        task_id=task.id,
    )


async def inbox(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc())
                .limit(40)
            )
        ).scalars()
    )
    unread = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    return {"unread": int(unread), "items": [_row(item) for item in rows]}


async def mark_read(
    session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
) -> dict[str, Any]:
    row = await session.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        raise NotFound("Уведомление не найдено", entity_id=str(notification_id))
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await session.flush()
    return await inbox(session, user_id)


async def mark_all(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Notification).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
    ).scalars()
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    await session.flush()
    return await inbox(session, user_id)


async def _push(
    session: AsyncSession,
    user_ids: list[uuid.UUID],
    *,
    kind: str,
    title: str,
    body: str,
    project_id: uuid.UUID,
    task_id: uuid.UUID,
) -> None:
    actor = current_context().actor_id
    now = datetime.now(UTC)
    seen: set[uuid.UUID] = set()
    for user_id in user_ids:
        if user_id == actor or user_id in seen:
            continue
        seen.add(user_id)
        session.add(
            Notification(
                user_id=user_id,
                kind=kind,
                title=title[:500],
                body=body,
                project_id=project_id,
                task_id=task_id,
                created_at=now,
            )
        )
    if seen:
        await session.flush()


async def _users_for_employees(
    session: AsyncSession, employee_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    if not employee_ids:
        return []
    return list(
        (
            await session.execute(
                select(UserAccount.id).where(UserAccount.employee_id.in_(employee_ids))
            )
        ).scalars()
    )


async def _mentioned(session: AsyncSession, body: str) -> list[uuid.UUID]:
    if "@" not in body:
        return []
    rows = (await session.execute(select(UserAccount.id, UserAccount.display_name))).all()
    return [user_id for user_id, name in rows if name and f"@{name}" in body]


async def _heading(session: AsyncSession, task: Task) -> tuple[str, str]:
    project = await session.get(Project, task.project_id)
    key = project.key if project is not None else ""
    return f"{key}-{task.number}", task.title


def _row(item: Notification) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "body": item.body,
        "project_id": item.project_id,
        "task_id": item.task_id,
        "read_at": item.read_at,
        "created_at": item.created_at,
    }
