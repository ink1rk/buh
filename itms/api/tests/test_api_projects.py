"""Критический путь считается на сервере и не зависит от того, чем его рисуют."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from itms.core.errors import CycleDetected
from itms.domain.projects import (
    Dependency,
    HealthMilestone,
    HealthTask,
    assess_health,
    critical_path,
    task_progress,
    weighted_progress,
)
from itms.models.enums import HealthStatus, ProjectStatus, TaskStatus

pytestmark = pytest.mark.anyio


def test_critical_path_chain_and_float() -> None:
    chain = critical_path(
        {"A": 3, "B": 2},
        [Dependency("A", "B", "FS", 0)],
    )
    assert chain.length_days == 5
    assert chain.points["A"].critical
    assert chain.points["B"].critical
    assert chain.points["A"].float_days == 0
    assert chain.points["B"].es == 3

    slack = critical_path(
        {"A": 2, "C": 2, "B": 5},
        [Dependency("A", "C", "FS", 0), Dependency("A", "B", "FS", 0)],
    )
    assert slack.length_days == 7
    assert slack.points["C"].float_days == 3
    assert not slack.points["C"].critical
    assert slack.points["A"].critical
    assert slack.points["B"].critical


def test_critical_path_rejects_a_cycle() -> None:
    with pytest.raises(CycleDetected):
        critical_path(
            {"A": 1, "B": 1},
            [Dependency("A", "B", "FS", 0), Dependency("B", "A", "FS", 0)],
        )


def test_progress_uses_children_and_estimates() -> None:
    assert task_progress(TaskStatus.DONE, []) == 100
    assert task_progress(TaskStatus.NEW, []) == 0
    assert (
        task_progress(
            TaskStatus.IN_PROGRESS, [TaskStatus.DONE, TaskStatus.NEW, TaskStatus.CANCELLED]
        )
        == 50
    )
    assert weighted_progress([(100, 60), (0, 30)]) == 66.67
    assert weighted_progress([(100, 0), (0, 0)]) == 50


def test_health_rules_are_explicit() -> None:
    today = date(2026, 9, 22)
    overdue = HealthTask("t1", TaskStatus.IN_PROGRESS, today - timedelta(days=1), None, 0, False, 0)
    calm = assess_health(
        project_status=ProjectStatus.IN_PROGRESS,
        today=today,
        tasks=[overdue],
        milestones=[],
        budget_planned=None,
        budget_actual=None,
        last_activity=today,
    )
    assert calm.status == HealthStatus.AT_RISK

    late_critical = HealthTask(
        "t1", TaskStatus.IN_PROGRESS, today - timedelta(days=1), None, 0, True, 0
    )
    delayed = assess_health(
        project_status=ProjectStatus.IN_PROGRESS,
        today=today,
        tasks=[late_critical],
        milestones=[],
        budget_planned=100,
        budget_actual=120,
        last_activity=today - timedelta(days=20),
    )
    rules = {item.rule for item in delayed.findings}
    assert delayed.status == HealthStatus.DELAYED
    assert {"critical_path", "budget", "inactive"} <= rules

    milestone = assess_health(
        project_status=ProjectStatus.PLANNING,
        today=today,
        tasks=[HealthTask("t1", TaskStatus.NEW, None, "m1", 10, False, 0)],
        milestones=[HealthMilestone("m1", "Согласование", today + timedelta(days=3), "PLANNED")],
        budget_planned=None,
        budget_actual=None,
        last_activity=today,
    )
    assert any(item.rule == "milestone_at_risk" for item in milestone.findings)

    blocked = assess_health(
        project_status=ProjectStatus.IN_PROGRESS,
        today=today,
        tasks=[HealthTask("t1", TaskStatus.BLOCKED, None, None, 0, False, 4)],
        milestones=[],
        budget_planned=None,
        budget_actual=None,
        last_activity=today,
    )
    assert any(item.rule == "blocked" for item in blocked.findings)


async def test_project_schedule_and_status_graph(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/projects",
        json={"key": "pwr", "name": "Мощность серверной", "description": "Переход"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["project"]["key"] == "PWR"
    project_id = body["project"]["id"]

    first = await client.post(
        f"{api}/projects/{project_id}/tasks",
        json={"title": "Обследовать", "estimate_min": 180},
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"{api}/projects/{project_id}/tasks",
        json={
            "title": "Смонтировать",
            "start_date": "2026-10-01",
            "due_date": "2026-10-05",
            "estimate_min": 240,
        },
    )
    assert second.status_code == 201, second.text
    tasks = {item["title"]: item for item in second.json()["tasks"]}
    assert tasks["Обследовать"]["label"] == "PWR-1"

    linked = await client.post(
        f"{api}/projects/{project_id}/dependencies",
        json={
            "predecessor_id": tasks["Обследовать"]["id"],
            "successor_id": tasks["Смонтировать"]["id"],
            "dep_kind": "FS",
        },
    )
    assert linked.status_code == 201, linked.text

    cycle = await client.post(
        f"{api}/projects/{project_id}/dependencies",
        json={
            "predecessor_id": tasks["Смонтировать"]["id"],
            "successor_id": tasks["Обследовать"]["id"],
            "dep_kind": "FS",
        },
    )
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "cycle_detected"

    schedule = await client.get(f"{api}/projects/{project_id}/schedule")
    assert schedule.status_code == 200, schedule.text
    points = {item["label"]: item for item in schedule.json()["items"]}
    assert points["PWR-1"]["critical"]
    assert points["PWR-2"]["critical"]
    assert points["PWR-2"]["duration_days"] == 5
    assert schedule.json()["length_days"] == points["PWR-1"]["duration_days"] + 5

    jumped = await client.patch(
        f"{api}/projects/{project_id}/tasks/{tasks['Обследовать']['id']}",
        json={"status": "DONE"},
    )
    assert jumped.status_code == 422
    assert jumped.json()["error"]["details"]["code_hint"] == "invalid_status_transition"

    started = await client.patch(
        f"{api}/projects/{project_id}/tasks/{tasks['Обследовать']['id']}",
        json={"status": "IN_PROGRESS"},
    )
    assert started.status_code == 200, started.text
    done = await client.patch(
        f"{api}/projects/{project_id}/tasks/{tasks['Обследовать']['id']}",
        json={"status": "DONE"},
    )
    assert done.status_code == 200, done.text
    finished = next(item for item in done.json()["tasks"] if item["label"] == "PWR-1")
    assert finished["progress_pct"] == 100
    assert done.json()["project"]["progress_pct"] == 42.86

    duplicate = await client.post(f"{api}/projects", json={"key": "PWR", "name": "Ещё один"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["code_hint"] == "duplicate_key"
