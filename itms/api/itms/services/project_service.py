"""Проекты: паспорт, этапы, задачи, зависимости и расписание.

Даты зависимых задач сервис не сдвигает. Критический путь показывает, где график
не сходится, а решение о переносе остаётся за человеком.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.context import current_context
from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.projects import (
    Dependency,
    HealthMilestone,
    HealthTask,
    assess_health,
    critical_path,
    task_duration_days,
    task_progress,
    validate_project_transition,
    validate_task_transition,
    weighted_progress,
)
from itms.models.cmdb import Ci
from itms.models.directory import Employee
from itms.models.enums import (
    DependencyKind,
    MilestoneStatus,
    Priority,
    ProjectStatus,
    TaskStatus,
    TaskType,
)
from itms.models.projects import (
    Milestone,
    Phase,
    Project,
    ProjectCi,
    ProjectMember,
    Task,
    TaskCheck,
    TaskCi,
    TaskComment,
    TaskDependency,
    TimeEntry,
)
from itms.services import notification_service, transition_service

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_OPEN = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})


def _key(value: str) -> str:
    raw = value.strip()
    if not _KEY.match(raw):
        raise Invalid(
            "Ключ проекта: латинские буквы, цифры, дефис, до 32 символов",
            code_hint="invalid",
        )
    return raw.upper()


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _touched(obj: object) -> date:
    """Дата последней правки без ленивой загрузки: после flush поле ещё не прочитано."""
    state = inspect(obj)
    if "updated_at" in state.unloaded or "updated_at" in state.expired_attributes:
        return date.today()
    value = state.dict.get("updated_at")
    if isinstance(value, datetime):
        return value.date()
    return date.today()


def _age_days(value: date, today: date) -> int:
    return (today - value).days


def _check_span(start: date | None, due: date | None) -> None:
    if start is not None and due is not None and due < start:
        raise Invalid("Дата окончания раньше даты начала", code_hint="date_order")


async def _project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFound("Проект не найден", entity_id=str(project_id))
    return project


async def _employee(session: AsyncSession, employee_id: uuid.UUID) -> Employee:
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise NotFound("Сотрудник не найден", entity_id=str(employee_id))
    return employee


async def _ci(session: AsyncSession, ci_id: uuid.UUID) -> Ci:
    ci = await session.get(Ci, ci_id)
    if ci is None or ci.deleted_at is not None:
        raise NotFound("Объект не найден", entity_id=str(ci_id))
    return ci


async def _task(session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise NotFound("Задача не найдена", entity_id=str(task_id))
    return task


async def _phase(session: AsyncSession, project_id: uuid.UUID, phase_id: uuid.UUID) -> Phase:
    phase = await session.get(Phase, phase_id)
    if phase is None or phase.project_id != project_id:
        raise NotFound("Этап не найден", entity_id=str(phase_id))
    return phase


async def _milestone(
    session: AsyncSession, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> Milestone:
    milestone = await session.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != project_id:
        raise NotFound("Веха не найдена", entity_id=str(milestone_id))
    return milestone


async def list_projects(session: AsyncSession) -> list[dict[str, Any]]:
    projects = list((await session.execute(select(Project).order_by(Project.key))).scalars())
    if not projects:
        return []
    ids = [project.id for project in projects]
    tasks = list((await session.execute(select(Task).where(Task.project_id.in_(ids)))).scalars())
    deps = (
        list(
            (
                await session.execute(
                    select(TaskDependency).where(
                        TaskDependency.predecessor_id.in_(
                            [task.id for task in tasks] or [uuid.uuid4()]
                        )
                    )
                )
            ).scalars()
        )
        if tasks
        else []
    )
    milestones = list(
        (await session.execute(select(Milestone).where(Milestone.project_id.in_(ids)))).scalars()
    )
    names = await _names(session, {project.owner_id for project in projects})
    deficits = await transition_service.projects_with_power_deficit(session)
    by_project: dict[uuid.UUID, list[Task]] = {}
    for task in tasks:
        by_project.setdefault(task.project_id, []).append(task)
    task_ids = {task.id for task in tasks}
    dep_by_project: dict[uuid.UUID, list[TaskDependency]] = {}
    task_project = {task.id: task.project_id for task in tasks}
    for dep in deps:
        if dep.predecessor_id in task_ids and dep.successor_id in task_ids:
            dep_by_project.setdefault(task_project[dep.predecessor_id], []).append(dep)
    miles_by_project: dict[uuid.UUID, list[Milestone]] = {}
    for milestone in milestones:
        miles_by_project.setdefault(milestone.project_id, []).append(milestone)
    return [
        _summary(
            project,
            names.get(project.owner_id),
            by_project.get(project.id, []),
            dep_by_project.get(project.id, []),
            miles_by_project.get(project.id, []),
            power_deficit=project.id in deficits,
        )
        for project in projects
    ]


async def project_view(
    session: AsyncSession, project_id: uuid.UUID, *, persist_progress: bool = False
) -> dict[str, Any]:
    project = await _project(session, project_id)
    phases = list(
        (
            await session.execute(
                select(Phase)
                .where(Phase.project_id == project_id)
                .order_by(Phase.order_index, Phase.name)
            )
        ).scalars()
    )
    milestones = list(
        (
            await session.execute(
                select(Milestone)
                .where(Milestone.project_id == project_id)
                .order_by(Milestone.due_date)
            )
        ).scalars()
    )
    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.project_id == project_id).order_by(Task.number)
            )
        ).scalars()
    )
    task_ids = [task.id for task in tasks]
    deps = []
    if task_ids:
        deps = list(
            (
                await session.execute(
                    select(TaskDependency).where(TaskDependency.predecessor_id.in_(task_ids))
                )
            ).scalars()
        )
        deps = [dep for dep in deps if dep.successor_id in set(task_ids)]
    links = list(
        (
            await session.execute(
                select(ProjectCi, Ci)
                .join(Ci, Ci.id == ProjectCi.ci_id)
                .where(ProjectCi.project_id == project_id)
                .order_by(Ci.name)
            )
        ).all()
    )
    task_links: list[tuple[TaskCi, Ci]] = []
    if task_ids:
        task_links = list(
            (
                await session.execute(
                    select(TaskCi, Ci)
                    .join(Ci, Ci.id == TaskCi.ci_id)
                    .where(TaskCi.task_id.in_(task_ids))
                )
            ).all()
        )
    members = list(
        (
            await session.execute(
                select(ProjectMember, Employee)
                .join(Employee, Employee.id == ProjectMember.employee_id)
                .where(ProjectMember.project_id == project_id)
                .order_by(Employee.full_name)
            )
        ).all()
    )
    entries = []
    if task_ids:
        entries = list(
            (
                await session.execute(
                    select(TimeEntry)
                    .where(TimeEntry.task_id.in_(task_ids))
                    .order_by(TimeEntry.work_date.desc())
                )
            ).scalars()
        )
    people = {project.owner_id}
    people.update(task.assignee_id for task in tasks)
    people.update(entry.employee_id for entry in entries)
    names = await _names(session, people)
    deficits = await transition_service.projects_with_power_deficit(session)
    view = _compose(
        project,
        phases,
        milestones,
        tasks,
        deps,
        links,
        task_links,
        members,
        entries,
        names,
        power_deficit=project.id in deficits,
    )
    if persist_progress:
        project.progress_pct = Decimal(str(view["project"]["progress_pct"]))
        await session.flush()
    return view


async def create_project(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    key = _key(data["key"])
    taken = (
        await session.execute(select(Project.id).where(Project.key == key))
    ).scalar_one_or_none()
    if taken:
        raise Conflict("Проект с таким ключом уже есть", code_hint="duplicate_key")
    start = data.get("start_date")
    due = data.get("due_date")
    _check_span(start, due)
    owner_id = data.get("owner_id")
    if owner_id:
        await _employee(session, owner_id)
    project = Project(
        key=key,
        name=data["name"].strip(),
        description=(data.get("description") or "").strip(),
        status=ProjectStatus(data.get("status") or ProjectStatus.PLANNING),
        priority=Priority(data.get("priority") or Priority.MEDIUM),
        owner_id=owner_id,
        start_date=start,
        due_date=due,
        budget_planned=data.get("budget_planned"),
        budget_actual=data.get("budget_actual"),
    )
    if not project.name:
        raise Invalid("Укажите название проекта", code_hint="invalid")
    session.add(project)
    await session.flush()
    return await project_view(session, project.id, persist_progress=True)


async def update_project(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    project = await _project(session, project_id)
    if "key" in data and data["key"] is not None:
        key = _key(data["key"])
        taken = (
            await session.execute(
                select(Project.id).where(Project.key == key, Project.id != project.id)
            )
        ).scalar_one_or_none()
        if taken:
            raise Conflict("Проект с таким ключом уже есть", code_hint="duplicate_key")
        project.key = key
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise Invalid("Укажите название проекта", code_hint="invalid")
        project.name = name
    if "description" in data and data["description"] is not None:
        project.description = data["description"].strip()
    if "status" in data and data["status"] is not None:
        target = ProjectStatus(data["status"])
        validate_project_transition(project.status, target)
        project.status = target
        today = date.today()
        if target == ProjectStatus.IN_PROGRESS and project.actual_start_date is None:
            project.actual_start_date = today
        if target == ProjectStatus.COMPLETED and project.actual_end_date is None:
            project.actual_end_date = today
    if "priority" in data and data["priority"] is not None:
        project.priority = Priority(data["priority"])
    if "owner_id" in data:
        if data["owner_id"] is not None:
            await _employee(session, data["owner_id"])
        project.owner_id = data["owner_id"]
    for field in (
        "start_date",
        "due_date",
        "actual_start_date",
        "actual_end_date",
        "budget_planned",
        "budget_actual",
    ):
        if field in data:
            setattr(project, field, data[field])
    _check_span(project.start_date, project.due_date)
    await session.flush()
    return await project_view(session, project.id, persist_progress=True)


async def add_phase(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    await _project(session, project_id)
    name = data["name"].strip()
    if not name:
        raise Invalid("Укажите название этапа", code_hint="invalid")
    _check_span(data.get("start_date"), data.get("end_date"))
    order = data.get("order_index")
    if order is None:
        current = (
            await session.execute(
                select(func.coalesce(func.max(Phase.order_index), 0)).where(
                    Phase.project_id == project_id
                )
            )
        ).scalar_one()
        order = int(current) + 1
    session.add(
        Phase(
            project_id=project_id,
            name=name,
            order_index=order,
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
        )
    )
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def update_phase(
    session: AsyncSession, project_id: uuid.UUID, phase_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    phase = await _phase(session, project_id, phase_id)
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise Invalid("Укажите название этапа", code_hint="invalid")
        phase.name = name
    for field in ("order_index", "start_date", "end_date", "status"):
        if field in data and data[field] is not None:
            setattr(phase, field, data[field])
    _check_span(phase.start_date, phase.end_date)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def delete_phase(
    session: AsyncSession, project_id: uuid.UUID, phase_id: uuid.UUID
) -> dict[str, Any]:
    phase = await _phase(session, project_id, phase_id)
    await session.delete(phase)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def add_milestone(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    await _project(session, project_id)
    name = data["name"].strip()
    if not name:
        raise Invalid("Укажите название вехи", code_hint="invalid")
    session.add(
        Milestone(
            project_id=project_id,
            name=name,
            due_date=data.get("due_date"),
            description=(data.get("description") or "").strip(),
        )
    )
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def update_milestone(
    session: AsyncSession, project_id: uuid.UUID, milestone_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    milestone = await _milestone(session, project_id, milestone_id)
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise Invalid("Укажите название вехи", code_hint="invalid")
        milestone.name = name
    if "due_date" in data:
        milestone.due_date = data["due_date"]
    if "description" in data and data["description"] is not None:
        milestone.description = data["description"].strip()
    if "status" in data and data["status"] is not None:
        milestone.status = MilestoneStatus(data["status"])
        if milestone.status == MilestoneStatus.REACHED and milestone.completed_at is None:
            milestone.completed_at = datetime.now(UTC)
        if milestone.status != MilestoneStatus.REACHED:
            milestone.completed_at = None
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def delete_milestone(
    session: AsyncSession, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> dict[str, Any]:
    milestone = await _milestone(session, project_id, milestone_id)
    await session.delete(milestone)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def add_task(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    project = await _project(session, project_id)
    title = data["title"].strip()
    if not title:
        raise Invalid("Укажите название задачи", code_hint="invalid")
    await _check_task_refs(session, project_id, None, data)
    _check_span(data.get("start_date"), data.get("due_date"))
    project.task_seq += 1
    task = Task(
        project_id=project_id,
        number=project.task_seq,
        title=title,
        description=(data.get("description") or "").strip(),
        task_type=TaskType(data.get("task_type") or TaskType.TASK),
        priority=Priority(data.get("priority") or Priority.MEDIUM),
        phase_id=data.get("phase_id"),
        milestone_id=data.get("milestone_id"),
        parent_id=data.get("parent_id"),
        assignee_id=data.get("assignee_id"),
        start_date=data.get("start_date"),
        due_date=data.get("due_date"),
        estimate_min=int(data.get("estimate_min") or 0),
        order_index=project.task_seq,
    )
    session.add(task)
    await session.flush()
    if task.assignee_id:
        await notification_service.task_assigned(session, task)
    return await project_view(session, project_id, persist_progress=True)


async def update_task(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    task = await _task(session, project_id, task_id)
    previous_status = task.status
    previous_assignee = task.assignee_id
    await _check_task_refs(session, project_id, task.id, data)
    if "title" in data and data["title"] is not None:
        title = data["title"].strip()
        if not title:
            raise Invalid("Укажите название задачи", code_hint="invalid")
        task.title = title
    if "description" in data and data["description"] is not None:
        task.description = data["description"].strip()
    if "status" in data and data["status"] is not None:
        target = TaskStatus(data["status"])
        validate_task_transition(task.status, target)
        task.status = target
        if target == TaskStatus.DONE:
            task.completed_at = datetime.now(UTC)
    if "priority" in data and data["priority"] is not None:
        task.priority = Priority(data["priority"])
    if "task_type" in data and data["task_type"] is not None:
        task.task_type = TaskType(data["task_type"])
    for field in ("phase_id", "milestone_id", "parent_id", "assignee_id", "start_date", "due_date"):
        if field in data:
            setattr(task, field, data[field])
    if "estimate_min" in data and data["estimate_min"] is not None:
        task.estimate_min = int(data["estimate_min"])
    _check_span(task.start_date, task.due_date)
    await session.flush()
    if task.assignee_id and task.assignee_id != previous_assignee:
        await notification_service.task_assigned(session, task)
    if task.status != previous_status:
        await notification_service.task_status(
            session, task, previous_status.value, task.status.value
        )
    return await project_view(session, project_id, persist_progress=True)


async def delete_task(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID
) -> dict[str, Any]:
    task = await _task(session, project_id, task_id)
    await session.delete(task)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def add_dependency(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    predecessor = await _task(session, project_id, data["predecessor_id"])
    successor = await _task(session, project_id, data["successor_id"])
    if predecessor.id == successor.id:
        raise Invalid("Задача не может зависеть от самой себя", code_hint="self_dependency")
    existing = (
        await session.execute(
            select(TaskDependency.id).where(
                TaskDependency.predecessor_id == predecessor.id,
                TaskDependency.successor_id == successor.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise Conflict("Такая зависимость уже есть", code_hint="duplicate_dependency")
    kind = DependencyKind(data.get("dep_kind") or DependencyKind.FS)
    lag = int(data.get("lag_days") or 0)
    tasks = list(
        (await session.execute(select(Task).where(Task.project_id == project_id))).scalars()
    )
    deps = list(
        (
            await session.execute(
                select(TaskDependency).where(
                    TaskDependency.predecessor_id.in_([task.id for task in tasks])
                )
            )
        ).scalars()
    )
    known = {task.id for task in tasks}
    durations = {str(task.id): task_duration_days(task.start_date, task.due_date) for task in tasks}
    links = [
        Dependency(str(dep.predecessor_id), str(dep.successor_id), dep.dep_kind.value, dep.lag_days)
        for dep in deps
        if dep.predecessor_id in known and dep.successor_id in known
    ]
    links.append(Dependency(str(predecessor.id), str(successor.id), kind.value, lag))
    critical_path(durations, links)
    session.add(
        TaskDependency(
            predecessor_id=predecessor.id,
            successor_id=successor.id,
            dep_kind=kind,
            lag_days=lag,
        )
    )
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def delete_dependency(
    session: AsyncSession, project_id: uuid.UUID, dependency_id: uuid.UUID
) -> dict[str, Any]:
    dep = await session.get(TaskDependency, dependency_id)
    if dep is None:
        raise NotFound("Зависимость не найдена", entity_id=str(dependency_id))
    await _task(session, project_id, dep.predecessor_id)
    await session.delete(dep)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def link_ci(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    await _project(session, project_id)
    ci = await _ci(session, data["ci_id"])
    involvement = (data.get("involvement") or "затронут").strip() or "затронут"
    link = await session.get(ProjectCi, (project_id, ci.id))
    if link is None:
        session.add(ProjectCi(project_id=project_id, ci_id=ci.id, involvement=involvement))
    else:
        link.involvement = involvement
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def unlink_ci(
    session: AsyncSession, project_id: uuid.UUID, ci_id: uuid.UUID
) -> dict[str, Any]:
    link = await session.get(ProjectCi, (project_id, ci_id))
    if link is None:
        raise NotFound("Объект не привязан к проекту", entity_id=str(ci_id))
    await session.delete(link)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def link_task_ci(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    task = await _task(session, project_id, task_id)
    ci = await _ci(session, data["ci_id"])
    role = (data.get("role") or "затронут").strip() or "затронут"
    link = await session.get(TaskCi, (task.id, ci.id))
    if link is None:
        session.add(TaskCi(task_id=task.id, ci_id=ci.id, role=role))
    else:
        link.role = role
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def unlink_task_ci(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID, ci_id: uuid.UUID
) -> dict[str, Any]:
    await _task(session, project_id, task_id)
    link = await session.get(TaskCi, (task_id, ci_id))
    if link is None:
        raise NotFound("Объект не привязан к задаче", entity_id=str(ci_id))
    await session.delete(link)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def add_member(
    session: AsyncSession, project_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    await _project(session, project_id)
    employee = await _employee(session, data["employee_id"])
    role = (data.get("role") or "участник").strip() or "участник"
    member = await session.get(ProjectMember, (project_id, employee.id))
    if member is None:
        session.add(ProjectMember(project_id=project_id, employee_id=employee.id, role=role))
    else:
        member.role = role
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def remove_member(
    session: AsyncSession, project_id: uuid.UUID, employee_id: uuid.UUID
) -> dict[str, Any]:
    member = await session.get(ProjectMember, (project_id, employee_id))
    if member is None:
        raise NotFound("Участник не найден", entity_id=str(employee_id))
    await session.delete(member)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def add_time(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    task = await _task(session, project_id, task_id)
    employee = await _employee(session, data["employee_id"])
    session.add(
        TimeEntry(
            task_id=task.id,
            employee_id=employee.id,
            work_date=data["work_date"],
            minutes=int(data["minutes"]),
            note=(data.get("note") or "").strip(),
        )
    )
    await session.flush()
    total = (
        await session.execute(
            select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(
                TimeEntry.task_id == task.id
            )
        )
    ).scalar_one()
    task.spent_min = int(total)
    await session.flush()
    return await project_view(session, project_id, persist_progress=True)


async def schedule(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    view = await project_view(session, project_id)
    return view["schedule"]


async def _names(session: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    clean = {item for item in ids if item is not None}
    if not clean:
        return {}
    rows = await session.execute(
        select(Employee.id, Employee.full_name).where(Employee.id.in_(clean))
    )
    return {row[0]: row[1] for row in rows.all()}


async def _check_task_refs(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID | None, data: dict[str, Any]
) -> None:
    if data.get("phase_id"):
        await _phase(session, project_id, data["phase_id"])
    if data.get("milestone_id"):
        await _milestone(session, project_id, data["milestone_id"])
    if data.get("assignee_id"):
        await _employee(session, data["assignee_id"])
    parent_id = data.get("parent_id")
    if parent_id:
        if task_id is not None and parent_id == task_id:
            raise Invalid("Задача не может быть родителем самой себя", code_hint="self_dependency")
        seen: set[uuid.UUID] = set()
        current: uuid.UUID | None = parent_id
        while current is not None:
            if current in seen or current == task_id:
                raise Conflict("Иерархия задач образует цикл", code_hint="cycle_detected")
            seen.add(current)
            parent = await session.get(Task, current)
            if parent is None or parent.project_id != project_id:
                raise Invalid("Родительская задача из другого проекта", code_hint="cross_project")
            current = parent.parent_id


def _summary(
    project: Project,
    owner_name: str | None,
    tasks: list[Task],
    deps: list[TaskDependency],
    milestones: list[Milestone],
    *,
    power_deficit: bool = False,
) -> dict[str, Any]:
    progress, health, _schedule = _metrics(
        project, tasks, deps, milestones, power_deficit=power_deficit
    )
    open_tasks = sum(1 for task in tasks if task.status not in _OPEN)
    return {
        "id": project.id,
        "key": project.key,
        "name": project.name,
        "status": project.status,
        "priority": project.priority,
        "owner_name": owner_name,
        "start_date": project.start_date,
        "due_date": project.due_date,
        "progress_pct": progress,
        "health": health["status"],
        "task_count": len(tasks),
        "open_task_count": open_tasks,
    }


def _compose(
    project: Project,
    phases: list[Phase],
    milestones: list[Milestone],
    tasks: list[Task],
    deps: list[TaskDependency],
    links: list[tuple[ProjectCi, Ci]],
    task_links: list[tuple[TaskCi, Ci]],
    members: list[tuple[ProjectMember, Employee]],
    entries: list[TimeEntry],
    names: dict[uuid.UUID, str],
    *,
    power_deficit: bool = False,
) -> dict[str, Any]:
    progress, health, schedule = _metrics(
        project, tasks, deps, milestones, power_deficit=power_deficit
    )
    children: dict[uuid.UUID, list[TaskStatus]] = {}
    for task in tasks:
        if task.parent_id is not None:
            children.setdefault(task.parent_id, []).append(task.status)
    by_task_ci: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for link, ci in task_links:
        by_task_ci.setdefault(link.task_id, []).append(
            {"ci_id": ci.id, "code": ci.code, "name": ci.name, "role": link.role}
        )
    by_entry: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for entry in entries:
        by_entry.setdefault(entry.task_id, []).append(
            {
                "id": entry.id,
                "task_id": entry.task_id,
                "employee_id": entry.employee_id,
                "employee_name": names.get(entry.employee_id),
                "work_date": entry.work_date,
                "minutes": entry.minutes,
                "note": entry.note,
            }
        )
    phase_progress = _phase_progress(phases, tasks, children)
    open_tasks = sum(1 for task in tasks if task.status not in _OPEN)
    return {
        "project": {
            "id": project.id,
            "key": project.key,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "priority": project.priority,
            "owner_id": project.owner_id,
            "owner_name": names.get(project.owner_id) if project.owner_id else None,
            "start_date": project.start_date,
            "due_date": project.due_date,
            "actual_start_date": project.actual_start_date,
            "actual_end_date": project.actual_end_date,
            "budget_planned": _money(project.budget_planned),
            "budget_actual": _money(project.budget_actual),
            "progress_pct": progress,
            "task_count": len(tasks),
            "open_task_count": open_tasks,
        },
        "phases": [
            {
                "id": phase.id,
                "name": phase.name,
                "order_index": phase.order_index,
                "start_date": phase.start_date,
                "end_date": phase.end_date,
                "status": phase.status,
                "progress_pct": phase_progress.get(phase.id, 0.0),
            }
            for phase in phases
        ],
        "milestones": [
            {
                "id": milestone.id,
                "name": milestone.name,
                "due_date": milestone.due_date,
                "status": milestone.status,
                "description": milestone.description,
                "completed_at": milestone.completed_at,
            }
            for milestone in milestones
        ],
        "tasks": [
            {
                "id": task.id,
                "number": task.number,
                "label": f"{project.key}-{task.number}",
                "title": task.title,
                "description": task.description,
                "task_type": task.task_type,
                "status": task.status,
                "priority": task.priority,
                "phase_id": task.phase_id,
                "milestone_id": task.milestone_id,
                "parent_id": task.parent_id,
                "assignee_id": task.assignee_id,
                "assignee_name": names.get(task.assignee_id) if task.assignee_id else None,
                "start_date": task.start_date,
                "due_date": task.due_date,
                "estimate_min": task.estimate_min,
                "spent_min": task.spent_min,
                "progress_pct": task_progress(task.status, children.get(task.id, [])),
                "order_index": float(task.order_index),
                "cis": by_task_ci.get(task.id, []),
                "time_entries": by_entry.get(task.id, []),
            }
            for task in tasks
        ],
        "dependencies": [
            {
                "id": dep.id,
                "predecessor_id": dep.predecessor_id,
                "successor_id": dep.successor_id,
                "dep_kind": dep.dep_kind,
                "lag_days": dep.lag_days,
            }
            for dep in deps
        ],
        "cis": [
            {
                "ci_id": ci.id,
                "code": ci.code,
                "name": ci.name,
                "ci_type": ci.ci_type.value,
                "involvement": link.involvement,
            }
            for link, ci in links
        ],
        "members": [
            {
                "employee_id": employee.id,
                "full_name": employee.full_name,
                "role": member.role,
            }
            for member, employee in members
        ],
        "schedule": schedule,
        "health": health,
    }


def _metrics(
    project: Project,
    tasks: list[Task],
    deps: list[TaskDependency],
    milestones: list[Milestone],
    *,
    power_deficit: bool = False,
) -> tuple[float, dict[str, Any], dict[str, Any]]:
    children: dict[uuid.UUID, list[TaskStatus]] = {}
    for task in tasks:
        if task.parent_id is not None:
            children.setdefault(task.parent_id, []).append(task.status)
    progress_by_id = {
        task.id: task_progress(task.status, children.get(task.id, [])) for task in tasks
    }
    living = [task for task in tasks if task.status != TaskStatus.CANCELLED]
    progress = weighted_progress([(progress_by_id[task.id], task.estimate_min) for task in living])
    known = {task.id for task in tasks}
    durations = {str(task.id): task_duration_days(task.start_date, task.due_date) for task in tasks}
    links = [
        Dependency(
            str(dep.predecessor_id),
            str(dep.successor_id),
            dep.dep_kind.value,
            int(dep.lag_days),
        )
        for dep in deps
        if dep.predecessor_id in known and dep.successor_id in known
    ]
    computed = critical_path(durations, links)
    anchor = project.start_date or date.today()
    items = []
    for task in tasks:
        point = computed.points[str(task.id)]
        items.append(
            {
                "task_id": task.id,
                "number": task.number,
                "label": f"{project.key}-{task.number}",
                "title": task.title,
                "phase_id": task.phase_id,
                "parent_id": task.parent_id,
                "status": task.status,
                "duration_days": point.duration,
                "es": point.es,
                "ef": point.ef,
                "ls": point.ls,
                "lf": point.lf,
                "float_days": point.float_days,
                "critical": point.critical,
                "start_date": anchor.fromordinal(anchor.toordinal() + point.es),
                "finish_date": anchor.fromordinal(anchor.toordinal() + point.ef - 1),
                "planned_start": task.start_date,
                "planned_finish": task.due_date,
            }
        )
    items.sort(key=lambda item: (item["es"], item["number"]))
    schedule_milestones = []
    for milestone in milestones:
        offset = None
        if milestone.due_date is not None:
            offset = (milestone.due_date - anchor).days
        schedule_milestones.append(
            {
                "id": milestone.id,
                "name": milestone.name,
                "due_date": milestone.due_date,
                "offset_days": offset,
                "status": milestone.status,
                "overdue": bool(
                    milestone.due_date
                    and milestone.due_date < date.today()
                    and milestone.status != MilestoneStatus.REACHED
                ),
            }
        )
    today = date.today()
    critical_ids = {item["task_id"] for item in items if item["critical"]}
    health_tasks = [
        HealthTask(
            id=str(task.id),
            status=task.status,
            due=task.due_date,
            milestone_id=str(task.milestone_id) if task.milestone_id else None,
            progress=progress_by_id[task.id],
            critical=task.id in critical_ids,
            blocked_days=_age_days(_touched(task), today)
            if task.status == TaskStatus.BLOCKED
            else 0,
        )
        for task in tasks
    ]
    health_miles = [
        HealthMilestone(
            id=str(milestone.id),
            name=milestone.name,
            due=milestone.due_date,
            status=milestone.status.value,
        )
        for milestone in milestones
    ]
    activity_dates = [_touched(project)]
    activity_dates.extend(_touched(task) for task in tasks)
    last_activity = max(activity_dates) if activity_dates else None
    health = assess_health(
        project_status=project.status,
        today=today,
        tasks=health_tasks,
        milestones=health_miles,
        budget_planned=_money(project.budget_planned),
        budget_actual=_money(project.budget_actual),
        last_activity=last_activity,
        power_deficit=power_deficit,
    )
    return (
        progress,
        {
            "status": health.status,
            "findings": [
                {
                    "rule": finding.rule,
                    "level": finding.level,
                    "message": finding.message,
                    "entity_ids": list(finding.entity_ids),
                }
                for finding in health.findings
            ],
        },
        {
            "anchor": anchor,
            "length_days": computed.length_days,
            "items": items,
            "milestones": schedule_milestones,
        },
    )


def _phase_progress(
    phases: list[Phase], tasks: list[Task], children: dict[uuid.UUID, list[TaskStatus]]
) -> dict[uuid.UUID, float]:
    result: dict[uuid.UUID, float] = {}
    for phase in phases:
        owned = [
            task
            for task in tasks
            if task.phase_id == phase.id and task.status != TaskStatus.CANCELLED
        ]
        result[phase.id] = weighted_progress(
            [
                (task_progress(task.status, children.get(task.id, [])), task.estimate_min)
                for task in owned
            ]
        )
    return result


_CLOSED = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})


async def inbox(session: AsyncSession) -> list[dict[str, Any]]:
    """Открытые задачи всех проектов, разложенные по сроку."""
    today = date.today()
    soon = today + timedelta(days=7)
    rows = (
        await session.execute(
            select(Task, Project)
            .join(Project, Project.id == Task.project_id)
            .where(Task.status.notin_(_CLOSED))
            .order_by(Task.due_date.asc().nulls_last(), Project.key, Task.number)
        )
    ).all()
    names = await _names(session, {task.assignee_id for task, _ in rows})
    result = []
    for task, project in rows:
        due = task.due_date
        if due is None:
            bucket = "undated"
        elif due < today:
            bucket = "overdue"
        elif due == today:
            bucket = "today"
        elif due <= soon:
            bucket = "upcoming"
        else:
            bucket = "later"
        result.append(
            {
                "id": task.id,
                "project_id": project.id,
                "project_key": project.key,
                "project_name": project.name,
                "label": f"{project.key}-{task.number}",
                "title": task.title,
                "status": task.status.value,
                "priority": task.priority.value,
                "due_date": due,
                "assignee_name": names.get(task.assignee_id) if task.assignee_id else None,
                "bucket": bucket,
            }
        )
    return result


async def task_work(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID
) -> dict[str, Any]:
    await _task(session, project_id, task_id)
    comments = list(
        (
            await session.execute(
                select(TaskComment)
                .where(TaskComment.task_id == task_id)
                .order_by(TaskComment.created_at)
            )
        ).scalars()
    )
    checks = list(
        (
            await session.execute(
                select(TaskCheck)
                .where(TaskCheck.task_id == task_id)
                .order_by(TaskCheck.order_index, TaskCheck.title)
            )
        ).scalars()
    )
    return {
        "comments": [_comment_row(row) for row in comments],
        "checks": [_check_row(row) for row in checks],
    }


async def add_comment(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID, body: str
) -> dict[str, Any]:
    task = await _task(session, project_id, task_id)
    text_body = body.strip()
    if not text_body:
        raise Invalid("Комментарий пуст", code_hint="invalid")
    session.add(
        TaskComment(
            task_id=task_id,
            body=text_body,
            author_label=current_context().actor_label or "",
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    await notification_service.task_comment(session, task, text_body)
    return await task_work(session, project_id, task_id)


async def add_check(
    session: AsyncSession, project_id: uuid.UUID, task_id: uuid.UUID, title: str
) -> dict[str, Any]:
    await _task(session, project_id, task_id)
    name = title.strip()
    if not name:
        raise Invalid("Укажите пункт чеклиста", code_hint="invalid")
    session.add(TaskCheck(task_id=task_id, title=name, done=False, order_index=0))
    await session.flush()
    return await task_work(session, project_id, task_id)


async def update_check(
    session: AsyncSession,
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    check_id: uuid.UUID,
    done: bool,
) -> dict[str, Any]:
    await _task(session, project_id, task_id)
    row = await session.get(TaskCheck, check_id)
    if row is None or row.task_id != task_id:
        raise NotFound("Пункт чеклиста не найден", entity_id=str(check_id))
    row.done = done
    await session.flush()
    return await task_work(session, project_id, task_id)


def _comment_row(row: TaskComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "body": row.body,
        "author_label": row.author_label,
        "created_at": row.created_at,
    }


def _check_row(row: TaskCheck) -> dict[str, Any]:
    return {"id": row.id, "title": row.title, "done": row.done}
