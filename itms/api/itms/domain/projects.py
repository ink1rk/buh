"""Проекты: переходы статусов, критический путь и здоровье.

Расписание не знает, чем его рисуют. Ранние и поздние даты, резерв и критический
путь считаются здесь и отдаются как числа; календарь и полосы — забота сервиса и UI.
Сдвиг зависимых задач по умолчанию мягкий: расчёт показывает конфликт, даты не двигает.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from itms.core.errors import CycleDetected, Invalid
from itms.models.enums import (
    HealthStatus,
    ProjectStatus,
    TaskStatus,
)

PROJECT_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.DRAFT: frozenset({ProjectStatus.PLANNING, ProjectStatus.CANCELLED}),
    ProjectStatus.PLANNING: frozenset(
        {ProjectStatus.IN_PROGRESS, ProjectStatus.ON_HOLD, ProjectStatus.CANCELLED}
    ),
    ProjectStatus.IN_PROGRESS: frozenset(
        {ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED, ProjectStatus.CANCELLED}
    ),
    ProjectStatus.ON_HOLD: frozenset({ProjectStatus.IN_PROGRESS, ProjectStatus.CANCELLED}),
    ProjectStatus.COMPLETED: frozenset(),
    ProjectStatus.CANCELLED: frozenset(),
}

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.NEW: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskStatus.ON_HOLD,
            TaskStatus.BLOCKED,
            TaskStatus.REVIEW,
            TaskStatus.DONE,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.ON_HOLD: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

TERMINAL_TASK_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})


def validate_project_transition(current: ProjectStatus, target: ProjectStatus) -> None:
    _validate(current, target, PROJECT_TRANSITIONS)


def validate_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    _validate(current, target, TASK_TRANSITIONS)


def _validate(
    current: ProjectStatus | TaskStatus, target: ProjectStatus | TaskStatus, graph: dict
) -> None:
    if current == target:
        return
    allowed = graph.get(current, frozenset())
    if target not in allowed:
        raise Invalid(
            f"Переход статуса {current.value} → {target.value} не разрешён",
            code_hint="invalid_status_transition",
            current=current.value,
            target=target.value,
            allowed=sorted(item.value for item in allowed),
        )


def task_duration_days(start: date | None, due: date | None) -> int:
    """Длительность в рабочих днях календаря: оба конца включительно, минимум один день."""
    if start is None or due is None:
        return 1
    return max(1, (due - start).days + 1)


def task_progress(status: TaskStatus, child_statuses: list[TaskStatus]) -> float:
    """DONE без детей — 100%. Если есть подзадачи, прогресс — доля выполненных среди живых."""
    living = [item for item in child_statuses if item != TaskStatus.CANCELLED]
    if living:
        done = sum(1 for item in living if item == TaskStatus.DONE)
        return round(100.0 * done / len(living), 2)
    if status == TaskStatus.DONE:
        return 100.0
    return 0.0


def weighted_progress(items: list[tuple[float, int]]) -> float:
    """Взвешивание по оценке. Если оценок нет — простое среднее по количеству."""
    if not items:
        return 0.0
    weight = sum(max(item_weight, 0) for _, item_weight in items)
    if weight == 0:
        return round(sum(progress for progress, _ in items) / len(items), 2)
    total = sum(progress * max(item_weight, 0) for progress, item_weight in items)
    return round(total / weight, 2)


@dataclass(frozen=True)
class SchedulePoint:
    duration: int
    es: int
    ef: int
    ls: int
    lf: int
    float_days: int
    critical: bool


@dataclass(frozen=True)
class Schedule:
    length_days: int
    points: dict[str, SchedulePoint]


@dataclass(frozen=True)
class Dependency:
    predecessor: str
    successor: str
    kind: str
    lag_days: int


def critical_path(durations: dict[str, int], dependencies: list[Dependency]) -> Schedule:
    """Метод критического пути.

    Смещения в днях от якоря проекта. Финиш включительный: якорь + ef − 1.
    Резерв — разница позднего и раннего старта. Нулевой резерв — критический путь.
    """
    if not durations:
        return Schedule(length_days=0, points={})
    clean = {task_id: max(1, duration) for task_id, duration in durations.items()}
    _ensure_known(clean, dependencies)
    order = _topological(clean, dependencies)

    incoming: dict[str, list[Dependency]] = {task_id: [] for task_id in clean}
    outgoing: dict[str, list[Dependency]] = {task_id: [] for task_id in clean}
    for link in dependencies:
        incoming[link.successor].append(link)
        outgoing[link.predecessor].append(link)

    early_start: dict[str, int] = {}
    early_finish: dict[str, int] = {}
    for task_id in order:
        bounds = [0]
        for link in incoming[task_id]:
            bounds.append(_early_start(link, early_start, early_finish, clean[task_id]))
        early_start[task_id] = max(bounds)
        early_finish[task_id] = early_start[task_id] + clean[task_id]

    length = max(early_finish.values(), default=0)
    late_start: dict[str, int] = {}
    late_finish: dict[str, int] = {}
    for task_id in reversed(order):
        bounds = [length]
        for link in outgoing[task_id]:
            bounds.append(_late_finish(link, late_start, late_finish, clean[task_id]))
        late_finish[task_id] = min(bounds)
        late_start[task_id] = late_finish[task_id] - clean[task_id]

    points = {}
    for task_id, duration in clean.items():
        slack = late_start[task_id] - early_start[task_id]
        points[task_id] = SchedulePoint(
            duration=duration,
            es=early_start[task_id],
            ef=early_finish[task_id],
            ls=late_start[task_id],
            lf=late_finish[task_id],
            float_days=slack,
            critical=slack <= 0,
        )
    return Schedule(length_days=length, points=points)


def _ensure_known(durations: dict[str, int], dependencies: list[Dependency]) -> None:
    for link in dependencies:
        if link.predecessor == link.successor:
            raise Invalid(
                "Задача не может зависеть от самой себя",
                code_hint="self_dependency",
            )
        if link.predecessor not in durations or link.successor not in durations:
            raise Invalid(
                "Зависимость ссылается на задачу вне проекта",
                code_hint="cross_project",
            )
        if link.kind not in {"FS", "SS", "FF", "SF"}:
            raise Invalid("Неизвестный тип зависимости", code_hint="invalid")


def _early_start(
    link: Dependency,
    early_start: dict[str, int],
    early_finish: dict[str, int],
    successor_duration: int,
) -> int:
    lag = link.lag_days
    if link.kind == "FS":
        return early_finish[link.predecessor] + lag
    if link.kind == "SS":
        return early_start[link.predecessor] + lag
    if link.kind == "FF":
        return early_finish[link.predecessor] + lag - successor_duration
    return early_start[link.predecessor] + lag - successor_duration


def _late_finish(
    link: Dependency,
    late_start: dict[str, int],
    late_finish: dict[str, int],
    predecessor_duration: int,
) -> int:
    lag = link.lag_days
    if link.kind == "FS":
        return late_start[link.successor] - lag
    if link.kind == "SS":
        return late_start[link.successor] - lag + predecessor_duration
    if link.kind == "FF":
        return late_finish[link.successor] - lag
    return late_finish[link.successor] - lag + predecessor_duration


def _topological(durations: dict[str, int], dependencies: list[Dependency]) -> list[str]:
    """Предшественники раньше преемников. Цикл — ошибка, а не бесконечный обход."""
    adjacency: dict[str, list[str]] = {task_id: [] for task_id in durations}
    for link in dependencies:
        adjacency[link.predecessor].append(link.successor)
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[str] = []

    def walk(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise CycleDetected("Зависимости задач образуют цикл")
        visiting.add(task_id)
        for successor in adjacency[task_id]:
            walk(successor)
        visiting.remove(task_id)
        visited.add(task_id)
        order.append(task_id)

    for task_id in durations:
        walk(task_id)
    order.reverse()
    return order


@dataclass(frozen=True)
class HealthTask:
    id: str
    status: TaskStatus
    due: date | None
    milestone_id: str | None
    progress: float
    critical: bool
    blocked_days: int


@dataclass(frozen=True)
class HealthMilestone:
    id: str
    name: str
    due: date | None
    status: str


@dataclass(frozen=True)
class Finding:
    rule: str
    level: str
    message: str
    entity_ids: tuple[str, ...]


@dataclass(frozen=True)
class Health:
    status: str
    findings: tuple[Finding, ...]


def assess_health(
    *,
    project_status: ProjectStatus,
    today: date,
    tasks: list[HealthTask],
    milestones: list[HealthMilestone],
    budget_planned: float | None,
    budget_actual: float | None,
    last_activity: date | None,
    power_deficit: bool = False,
) -> Health:
    """Каждое правило возвращает уровень и объяснение. Итог — худший из вкладов."""
    findings: list[Finding] = []
    open_overdue = [
        task
        for task in tasks
        if task.due is not None and task.due < today and task.status not in TERMINAL_TASK_STATUSES
    ]
    if open_overdue:
        critical_late = [task for task in open_overdue if task.critical]
        level = (
            HealthStatus.DELAYED
            if len(open_overdue) >= 5 or critical_late
            else HealthStatus.AT_RISK
        )
        findings.append(
            Finding(
                rule="overdue_tasks",
                level=level.value,
                message=f"Просрочено задач: {len(open_overdue)}",
                entity_ids=tuple(task.id for task in open_overdue),
            )
        )
        if critical_late:
            findings.append(
                Finding(
                    rule="critical_path",
                    level=HealthStatus.DELAYED.value,
                    message="На критическом пути есть просроченная задача",
                    entity_ids=tuple(task.id for task in critical_late),
                )
            )
    findings.extend(_milestone_findings(today, tasks, milestones))
    blocked = [
        task for task in tasks if task.status == TaskStatus.BLOCKED and task.blocked_days > 3
    ]
    if blocked:
        findings.append(
            Finding(
                rule="blocked",
                level=HealthStatus.AT_RISK.value,
                message="Есть задачи в блоке дольше трёх дней",
                entity_ids=tuple(task.id for task in blocked),
            )
        )
    if (
        budget_planned is not None
        and budget_actual is not None
        and budget_planned > 0
        and budget_actual > budget_planned * 1.1
    ):
        findings.append(
            Finding(
                rule="budget",
                level=HealthStatus.AT_RISK.value,
                message="Фактический бюджет превышает план больше чем на 10%",
                entity_ids=(),
            )
        )
    if power_deficit and project_status == ProjectStatus.IN_PROGRESS:
        findings.append(
            Finding(
                rule="power_deficit",
                level=HealthStatus.AT_RISK.value,
                message="Прогноз нагрузки выше предела ввода",
                entity_ids=(),
            )
        )
    if (
        project_status == ProjectStatus.IN_PROGRESS
        and last_activity is not None
        and (today - last_activity).days > 14
    ):
        findings.append(
            Finding(
                rule="inactive",
                level=HealthStatus.AT_RISK.value,
                message="По проекту нет активности больше 14 дней",
                entity_ids=(),
            )
        )
    if any(item.level == HealthStatus.DELAYED.value for item in findings):
        status = HealthStatus.DELAYED
    elif findings:
        status = HealthStatus.AT_RISK
    else:
        status = HealthStatus.ON_TRACK
    return Health(status=status.value, findings=tuple(findings))


def _milestone_findings(
    today: date, tasks: list[HealthTask], milestones: list[HealthMilestone]
) -> list[Finding]:
    findings: list[Finding] = []
    for milestone in milestones:
        if milestone.status == "REACHED" or milestone.due is None:
            continue
        days_left = (milestone.due - today).days
        if days_left > 7:
            continue
        linked = [task for task in tasks if task.milestone_id == milestone.id]
        progress = sum(task.progress for task in linked) / len(linked) if linked else 0.0
        if progress >= 70:
            continue
        findings.append(
            Finding(
                rule="milestone_at_risk",
                level=HealthStatus.AT_RISK.value,
                message=f"Веха «{milestone.name}» под угрозой: прогресс {progress:.0f}%",
                entity_ids=(milestone.id,),
            )
        )
    return findings
