"""Готовые составы проекта. Даты задач считаются от дня создания."""

from __future__ import annotations

from typing import TypedDict


class TaskSpec(TypedDict):
    title: str
    phase: str
    due_in_days: int


class MilestoneSpec(TypedDict):
    name: str
    due_in_days: int


class ProjectTemplate(TypedDict):
    key: str
    name: str
    phases: list[str]
    tasks: list[TaskSpec]
    milestones: list[MilestoneSpec]


INFRASTRUCTURE: ProjectTemplate = {
    "key": "infrastructure",
    "name": "ИТ-инфраструктура",
    "phases": ["Обследование", "Проектирование", "Внедрение", "Проверка"],
    "tasks": [
        {"title": "Обследовать площадку", "phase": "Обследование", "due_in_days": 7},
        {"title": "Собрать схему питания", "phase": "Проектирование", "due_in_days": 14},
        {"title": "Подготовить спецификацию", "phase": "Проектирование", "due_in_days": 21},
        {"title": "Смонтировать оборудование", "phase": "Внедрение", "due_in_days": 35},
        {"title": "Проверить и сдать", "phase": "Проверка", "due_in_days": 42},
    ],
    "milestones": [{"name": "Запуск", "due_in_days": 42}],
}

TEMPLATES: dict[str, ProjectTemplate] = {INFRASTRUCTURE["key"]: INFRASTRUCTURE}
