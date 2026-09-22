from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from itms.core.context import current_context, use_provenance
from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain import lifecycle
from itms.domain.locations import PATH_SEPARATOR
from itms.domain.relations import detect_cycle, group_of, validate_relation
from itms.domain.search import ci_document
from itms.models.audit import AuditChange, AuditLog
from itms.models.cmdb import Ci, CiRelation, CiTag, Location, Tag
from itms.models.documents import DocumentLink
from itms.models.enums import ACYCLIC_RELATIONS, CiStatus, CiType, RelationType
from itms.services import search_service


@contextmanager
def _default_reason(reason: str) -> Iterator[None]:
    """Явные действия (архив, восстановление, удаление) сами объясняют себя.

    Отдельную причину при этом можно указать заголовком — она имеет приоритет.
    """
    if current_context().provenance.is_empty:
        with use_provenance(reason=reason):
            yield
    else:
        yield


WRITABLE_FIELDS = (
    "code",
    "name",
    "criticality",
    "environment",
    "location_id",
    "owner_employee_id",
    "vendor",
    "model",
    "serial_number",
    "inventory_number",
    "description",
    "attributes",
    "valid_from",
    "valid_to",
)


@dataclass(slots=True)
class CiFilter:
    q: str | None = None
    ci_type: list[CiType] | None = None
    status: list[CiStatus] | None = None
    location_id: uuid.UUID | None = None
    include_sublocations: bool = True
    owner_employee_id: uuid.UUID | None = None
    tag: list[str] | None = None
    archived: bool = False
    sort: str = "name"
    limit: int = 50
    offset: int = 0


async def _ensure_unique_code(
    session: AsyncSession, code: str | None, exclude: uuid.UUID | None = None
) -> None:
    if not code:
        return
    stmt = select(Ci.id).where(Ci.code == code)
    if exclude:
        stmt = stmt.where(Ci.id != exclude)
    if (await session.execute(stmt.limit(1))).scalar_one_or_none():
        raise Conflict(f"Объект с кодом «{code}» уже существует", code=code, field="code")


async def _location_subtree_ids(session: AsyncSession, location_id: uuid.UUID) -> list[uuid.UUID]:
    path = (
        await session.execute(select(Location.path).where(Location.id == location_id))
    ).scalar_one_or_none()
    if path is None:
        return [location_id]
    rows = await session.execute(
        select(Location.id).where(
            or_(Location.id == location_id, Location.path.like(f"{path}{PATH_SEPARATOR}%"))
        )
    )
    return [row[0] for row in rows]


def _apply_sort(stmt: Select[Any], sort: str) -> Select[Any]:
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    column = {
        "name": Ci.name,
        "code": Ci.code,
        "status": Ci.status,
        "criticality": Ci.criticality,
        "updated_at": Ci.updated_at,
        "created_at": Ci.created_at,
    }.get(key, Ci.name)
    return stmt.order_by(column.desc() if descending else column.asc())


async def list_ci(session: AsyncSession, flt: CiFilter) -> tuple[list[Ci], int]:
    stmt = select(Ci).where(Ci.deleted_at.is_(None))
    stmt = stmt.where(Ci.archived_at.isnot(None) if flt.archived else Ci.archived_at.is_(None))

    if flt.ci_type:
        stmt = stmt.where(Ci.ci_type.in_(flt.ci_type))
    if flt.status:
        stmt = stmt.where(Ci.status.in_(flt.status))
    if flt.owner_employee_id:
        stmt = stmt.where(Ci.owner_employee_id == flt.owner_employee_id)
    if flt.location_id:
        if flt.include_sublocations:
            ids = await _location_subtree_ids(session, flt.location_id)
            stmt = stmt.where(Ci.location_id.in_(ids))
        else:
            stmt = stmt.where(Ci.location_id == flt.location_id)
    if flt.tag:
        stmt = stmt.where(
            Ci.id.in_(
                select(CiTag.ci_id).join(Tag, Tag.id == CiTag.tag_id).where(Tag.name.in_(flt.tag))
            )
        )
    if flt.q:
        pattern = f"%{flt.q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Ci.name).like(pattern),
                func.lower(Ci.code).like(pattern),
                func.lower(Ci.serial_number).like(pattern),
                func.lower(Ci.inventory_number).like(pattern),
            )
        )

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    stmt = _apply_sort(stmt, flt.sort).limit(flt.limit).offset(flt.offset)
    items = list((await session.execute(stmt)).scalars().unique())
    return items, int(total)


async def get_ci(session: AsyncSession, ci_id: uuid.UUID, *, with_deleted: bool = False) -> Ci:
    stmt = select(Ci).where(Ci.id == ci_id)
    if not with_deleted:
        stmt = stmt.where(Ci.deleted_at.is_(None))
    ci = (await session.execute(stmt)).scalar_one_or_none()
    if ci is None:
        raise NotFound("Объект не найден", entity_id=str(ci_id))
    return ci


async def reindex(session: AsyncSession, ci: Ci) -> None:
    location_path = None
    if ci.location_id:
        location_path = (
            await session.execute(select(Location.path).where(Location.id == ci.location_id))
        ).scalar_one_or_none()
    await search_service.index_entity(session, ci.id, ci_document(ci, location_path))


async def ensure_loaded(session: AsyncSession, ci: Ci) -> Ci:
    """Актуализирует объект после записи.

    В асинхронном режиме ленивой загрузки нет: значения, обновлённые базой, и связь
    с размещением нужно догрузить явно, иначе сериализация ответа упадёт.
    """
    await session.refresh(ci)
    await session.refresh(ci, attribute_names=["location"])
    return ci


async def create_ci(session: AsyncSession, data: dict[str, Any]) -> Ci:
    await _ensure_unique_code(session, data.get("code"))
    tags: list[str] = data.pop("tags", []) or []
    ci = Ci(
        ci_type=data["ci_type"],
        name=data["name"],
        status=data.get("status", CiStatus.ACTIVE),
        **{k: v for k, v in data.items() if k in WRITABLE_FIELDS and k != "name"},
    )
    session.add(ci)
    await session.flush()
    if tags:
        await set_tags(session, ci, tags)
    await reindex(session, ci)
    return await ensure_loaded(session, ci)


async def update_ci(session: AsyncSession, ci_id: uuid.UUID, data: dict[str, Any]) -> Ci:
    ci = await get_ci(session, ci_id)
    expected_version = data.pop("version", None)
    if expected_version is not None and expected_version != ci.version:
        raise Conflict(
            "Объект был изменён другим пользователем — обновите страницу",
            current_version=ci.version,
            expected_version=expected_version,
        )
    if "code" in data:
        await _ensure_unique_code(session, data["code"], exclude=ci_id)
    if "status" in data and data["status"] is not None:
        lifecycle.validate_status_transition(ci.status, CiStatus(data["status"]))
        ci.status = CiStatus(data["status"])
    tags = data.pop("tags", None)
    for field_name in WRITABLE_FIELDS:
        if field_name in data:
            setattr(ci, field_name, data[field_name])
    if tags is not None:
        await set_tags(session, ci, tags)
    await session.flush()
    await reindex(session, ci)
    return await ensure_loaded(session, ci)


async def archive_ci(session: AsyncSession, ci_id: uuid.UUID) -> Ci:
    ci = await get_ci(session, ci_id)
    lifecycle.ensure_can_archive(ci)
    ci.archived_at = datetime.now(UTC)
    with _default_reason("Объект отправлен в архив"):
        await session.flush()
    await search_service.remove_entity(session, "CI", ci.id)
    return await ensure_loaded(session, ci)


async def restore_ci(session: AsyncSession, ci_id: uuid.UUID) -> Ci:
    ci = await get_ci(session, ci_id, with_deleted=True)
    lifecycle.ensure_can_restore(ci)
    ci.archived_at = None
    ci.deleted_at = None
    with _default_reason("Объект восстановлен из архива"):
        await session.flush()
    await reindex(session, ci)
    return await ensure_loaded(session, ci)


async def delete_ci(session: AsyncSession, ci_id: uuid.UUID) -> None:
    """Мягкое удаление — только для объектов без истории и не критичных."""
    ci = await get_ci(session, ci_id)
    has_history = bool(
        (
            await session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.entity_type == "CI", AuditLog.entity_id == ci.id)
                .where(AuditLog.action != "CREATE")
            )
        ).scalar_one()
    )
    has_links = bool(
        (
            await session.execute(
                select(func.count())
                .select_from(CiRelation)
                .where(or_(CiRelation.source_ci_id == ci.id, CiRelation.target_ci_id == ci.id))
            )
        ).scalar_one()
    )
    lifecycle.ensure_can_soft_delete(ci, has_history=has_history or has_links)
    ci.deleted_at = datetime.now(UTC)
    with _default_reason("Объект удалён"):
        await session.flush()
    await search_service.remove_entity(session, "CI", ci.id)


async def set_tags(session: AsyncSession, ci: Ci, tag_names: list[str]) -> None:
    names = [t.strip() for t in tag_names if t and t.strip()]
    existing = {
        tag.name: tag
        for tag in (await session.execute(select(Tag).where(Tag.name.in_(names)))).scalars()
    }
    for name in names:
        if name not in existing:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
            existing[name] = tag
    await session.execute(delete(CiTag).where(CiTag.ci_id == ci.id))
    for name in names:
        session.add(CiTag(ci_id=ci.id, tag_id=existing[name].id))
    await session.flush()


async def get_tags(session: AsyncSession, ci_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(Tag.name)
        .join(CiTag, CiTag.tag_id == Tag.id)
        .where(CiTag.ci_id == ci_id)
        .order_by(Tag.name)
    )
    return [row[0] for row in rows]


async def tags_for_many(
    session: AsyncSession, ci_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not ci_ids:
        return {}
    rows = await session.execute(
        select(CiTag.ci_id, Tag.name)
        .join(Tag, Tag.id == CiTag.tag_id)
        .where(CiTag.ci_id.in_(ci_ids))
    )
    result: dict[uuid.UUID, list[str]] = defaultdict(list)
    for ci_id, name in rows:
        result[ci_id].append(name)
    return result


# --- Связи -------------------------------------------------------------------


async def _existing_edges(
    session: AsyncSession, rel_type: RelationType
) -> dict[uuid.UUID, list[uuid.UUID]]:
    rows = await session.execute(
        select(CiRelation.source_ci_id, CiRelation.target_ci_id).where(
            CiRelation.rel_type == rel_type
        )
    )
    edges: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for source, target in rows:
        edges[source].append(target)
    return edges


async def create_relation(session: AsyncSession, data: dict[str, Any]) -> CiRelation:
    source = await get_ci(session, data["source_ci_id"])
    target = await get_ci(session, data["target_ci_id"])
    rel_type = RelationType(data["rel_type"])
    validate_relation(
        source_id=source.id,
        target_id=target.id,
        source_type=source.ci_type,
        target_type=target.ci_type,
        rel_type=rel_type,
    )
    if rel_type in ACYCLIC_RELATIONS:
        detect_cycle(
            source_id=source.id,
            target_id=target.id,
            rel_type=rel_type,
            edges=await _existing_edges(session, rel_type),
        )
    duplicate = (
        await session.execute(
            select(CiRelation.id).where(
                CiRelation.source_ci_id == source.id,
                CiRelation.target_ci_id == target.id,
                CiRelation.rel_type == rel_type,
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict("Такая связь уже существует")
    relation = CiRelation(
        source_ci_id=source.id,
        target_ci_id=target.id,
        rel_type=rel_type,
        description=data.get("description"),
        attributes=data.get("attributes") or {},
    )
    if data.get("criticality"):
        relation.criticality = data["criticality"]
    session.add(relation)
    await session.flush()
    await session.refresh(relation, attribute_names=["source", "target"])
    return relation


async def delete_relation(session: AsyncSession, relation_id: uuid.UUID) -> None:
    relation = (
        await session.execute(select(CiRelation).where(CiRelation.id == relation_id))
    ).scalar_one_or_none()
    if relation is None:
        raise NotFound("Связь не найдена", entity_id=str(relation_id))
    await session.delete(relation)
    await session.flush()


async def related(session: AsyncSession, ci_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """Проекция графа для карточки объекта: всё связанное, сгруппированное по смыслу."""
    await get_ci(session, ci_id)
    rows = (
        await session.execute(
            select(CiRelation)
            .options(selectinload(CiRelation.source), selectinload(CiRelation.target))
            .where(or_(CiRelation.source_ci_id == ci_id, CiRelation.target_ci_id == ci_id))
        )
    ).scalars().unique()

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in rows:
        outgoing = relation.source_ci_id == ci_id
        other = relation.target if outgoing else relation.source
        groups[group_of(relation.rel_type)].append(
            {
                "relation_id": relation.id,
                "rel_type": relation.rel_type,
                "direction": "outgoing" if outgoing else "incoming",
                "criticality": relation.criticality,
                "description": relation.description,
                "ci": {
                    "id": other.id,
                    "name": other.name,
                    "code": other.code,
                    "ci_type": other.ci_type,
                    "status": other.status,
                },
            }
        )

    documents = (
        await session.execute(
            select(DocumentLink).where(
                DocumentLink.entity_type == "CI", DocumentLink.entity_id == ci_id
            )
        )
    ).scalars().all()
    groups["documents"] = [
        {"document_id": link.document_id, "relation": link.relation} for link in documents
    ]
    return dict(groups)


# --- История и происхождение --------------------------------------------------


async def history(
    session: AsyncSession, ci_id: uuid.UUID, *, limit: int = 100, offset: int = 0
) -> list[AuditLog]:
    rows = await session.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "CI", AuditLog.entity_id == ci_id)
        .order_by(AuditLog.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars().unique())


async def field_provenance(
    session: AsyncSession, ci_id: uuid.UUID, field_name: str
) -> list[dict[str, Any]]:
    """История конкретного параметра: кто, когда, почему и в рамках чего изменил."""
    await get_ci(session, ci_id, with_deleted=True)
    rows = await session.execute(
        select(AuditLog, AuditChange)
        .join(AuditChange, AuditChange.audit_log_id == AuditLog.id)
        .where(
            and_(
                AuditLog.entity_type == "CI",
                AuditLog.entity_id == ci_id,
                AuditChange.field == field_name,
            )
        )
        .order_by(AuditLog.occurred_at.desc())
    )
    result: list[dict[str, Any]] = []
    for log, change in rows:
        result.append(
            {
                "occurred_at": log.occurred_at,
                "actor_id": log.actor_id,
                "actor_label": log.actor_label,
                "actor_kind": log.actor_kind,
                "action": log.action,
                "field": change.field,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "reason": log.reason,
                "change_id": log.change_id,
                "project_id": log.project_id,
                "task_id": log.task_id,
                "document_id": log.document_id,
                "source": log.source,
            }
        )
    if not result:
        raise NotFound("По этому параметру изменений не зафиксировано", field=field_name)
    return result


async def stats(session: AsyncSession) -> dict[str, Any]:
    by_type = await session.execute(
        select(Ci.ci_type, func.count())
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .group_by(Ci.ci_type)
    )
    by_status = await session.execute(
        select(Ci.status, func.count())
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .group_by(Ci.status)
    )
    return {
        "by_type": {str(t): int(n) for t, n in by_type},
        "by_status": {str(s): int(n) for s, n in by_status},
    }


def ensure_type(value: str) -> CiType:
    try:
        return CiType(value)
    except ValueError as exc:  # pragma: no cover - защита от неверного ввода
        raise Invalid(f"Неизвестный тип объекта: {value}") from exc
