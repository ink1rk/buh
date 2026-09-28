"""Бюджет отдела и бюджет движения денежных средств."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Invalid, NotFound
from itms.models.finance import FinanceEntry

KINDS = frozenset({"BUDGET", "CASHFLOW"})
DIRECTIONS = frozenset({"IN", "OUT"})
FIELDS = ("department_id", "kind", "direction", "period", "article", "planned", "actual", "notes")


def _month(value: date) -> date:
    return value.replace(day=1)


async def list_entries(
    session: AsyncSession, kind: str | None = None
) -> list[FinanceEntry]:
    stmt = select(FinanceEntry).order_by(FinanceEntry.period.desc(), FinanceEntry.article)
    if kind:
        stmt = stmt.where(FinanceEntry.kind == kind)
    return list((await session.execute(stmt)).scalars())


async def create_entry(session: AsyncSession, data: dict[str, Any]) -> FinanceEntry:
    kind = data["kind"]
    direction = data["direction"]
    if kind not in KINDS:
        raise Invalid("Нужен бюджет отдела или БДДС", field="kind")
    if direction not in DIRECTIONS:
        raise Invalid("Направление — приход или расход", field="direction")
    item = FinanceEntry(
        department_id=data.get("department_id"),
        kind=kind,
        direction=direction,
        period=_month(data["period"]),
        article=data["article"].strip(),
        planned=Decimal(data.get("planned") or 0),
        actual=Decimal(data.get("actual") or 0),
        notes=data.get("notes"),
    )
    if not item.article:
        raise Invalid("Укажите статью", field="article")
    session.add(item)
    await session.flush()
    return item


async def update_entry(
    session: AsyncSession, entry_id: uuid.UUID, data: dict[str, Any]
) -> FinanceEntry:
    item = await session.get(FinanceEntry, entry_id)
    if item is None:
        raise NotFound("Строка бюджета не найдена", entity_id=str(entry_id))
    for field in FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == "period" and value is not None:
            value = _month(value)
        if field == "article" and isinstance(value, str):
            value = value.strip()
        if field in {"planned", "actual"} and value is not None:
            value = Decimal(value)
        setattr(item, field, value)
    if item.kind not in KINDS or item.direction not in DIRECTIONS:
        raise Invalid("Строка бюджета заполнена неверно")
    await session.flush()
    return item


async def delete_entry(session: AsyncSession, entry_id: uuid.UUID) -> None:
    item = await session.get(FinanceEntry, entry_id)
    if item is None:
        raise NotFound("Строка бюджета не найдена", entity_id=str(entry_id))
    await session.delete(item)
    await session.flush()
