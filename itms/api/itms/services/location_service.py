from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.locations import PATH_SEPARATOR, build_path, validate_hierarchy
from itms.domain.search import location_document
from itms.models.cmdb import Ci, Location
from itms.models.enums import LocationType
from itms.services import search_service

WRITABLE_FIELDS = ("name", "code", "address", "area_m2", "responsible_employee_id",
                   "description", "attributes")


async def get_location(session: AsyncSession, location_id: uuid.UUID) -> Location:
    location = (
        await session.execute(
            select(Location).where(Location.id == location_id, Location.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if location is None:
        raise NotFound("Размещение не найдено", entity_id=str(location_id))
    return location


async def list_locations(session: AsyncSession, *, archived: bool = False) -> list[Location]:
    stmt = select(Location).where(Location.deleted_at.is_(None))
    stmt = stmt.where(
        Location.archived_at.isnot(None) if archived else Location.archived_at.is_(None)
    )
    rows = await session.execute(stmt.order_by(Location.path))
    return list(rows.scalars().unique())


async def tree(session: AsyncSession) -> list[dict[str, Any]]:
    """Дерево размещений с количеством объектов в каждом узле."""
    locations = await list_locations(session)
    counts = dict(
        (
            await session.execute(
                select(Ci.location_id, func.count())
                .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
                .group_by(Ci.location_id)
            )
        ).all()
    )
    nodes: dict[uuid.UUID, dict[str, Any]] = {}
    for loc in locations:
        nodes[loc.id] = {
            "id": loc.id,
            "parent_id": loc.parent_id,
            "location_type": loc.location_type,
            "name": loc.name,
            "code": loc.code,
            "path": loc.path,
            "depth": loc.depth,
            "ci_count": int(counts.get(loc.id, 0)),
            "children": [],
        }
    roots: list[dict[str, Any]] = []
    for node in nodes.values():
        parent = nodes.get(node["parent_id"]) if node["parent_id"] else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    return roots


async def create_location(session: AsyncSession, data: dict[str, Any]) -> Location:
    location_type = LocationType(data["location_type"])
    parent: Location | None = None
    if data.get("parent_id"):
        parent = await get_location(session, data["parent_id"])
    validate_hierarchy(location_type, parent.location_type if parent else None)

    location = Location(
        location_type=location_type,
        parent_id=parent.id if parent else None,
        name=data["name"],
        **{k: v for k, v in data.items() if k in WRITABLE_FIELDS and k != "name"},
    )
    location.path = build_path(parent.path if parent else None, location.name)
    location.depth = (parent.depth + 1) if parent else 0
    duplicate = (
        await session.execute(select(Location.id).where(Location.path == location.path))
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict("Размещение с таким названием уже есть на этом уровне", path=location.path)
    session.add(location)
    await session.flush()
    await search_service.index_entity(session, location.id, location_document(location))
    return location


async def update_location(
    session: AsyncSession, location_id: uuid.UUID, data: dict[str, Any]
) -> Location:
    location = await get_location(session, location_id)
    if "parent_id" in data and data["parent_id"] != location.parent_id:
        await _move(session, location, data["parent_id"])
    for field_name in WRITABLE_FIELDS:
        if field_name in data:
            setattr(location, field_name, data[field_name])
    if "name" in data:
        await _rebuild_paths(session, location)
    await session.flush()
    await search_service.index_entity(session, location.id, location_document(location))
    return location


async def _move(session: AsyncSession, location: Location, parent_id: uuid.UUID | None) -> None:
    parent = await get_location(session, parent_id) if parent_id else None
    if parent is not None and (
        parent.id == location.id or parent.path.startswith(location.path + PATH_SEPARATOR)
    ):
        raise Invalid("Нельзя переместить размещение внутрь самого себя")
    validate_hierarchy(location.location_type, parent.location_type if parent else None)
    location.parent_id = parent.id if parent else None
    await _rebuild_paths(session, location, parent)


async def _rebuild_paths(
    session: AsyncSession, location: Location, parent: Location | None = None
) -> None:
    if parent is None and location.parent_id:
        parent = await get_location(session, location.parent_id)
    old_path = location.path
    location.path = build_path(parent.path if parent else None, location.name)
    location.depth = (parent.depth + 1) if parent else 0
    if old_path == location.path:
        return
    children = (
        await session.execute(
            select(Location).where(Location.path.like(f"{old_path}{PATH_SEPARATOR}%"))
        )
    ).scalars().all()
    for child in children:
        child.path = location.path + child.path[len(old_path):]
        child.depth = child.path.count(PATH_SEPARATOR)
    await session.flush()


async def archive_location(session: AsyncSession, location_id: uuid.UUID) -> Location:
    location = await get_location(session, location_id)
    used = (
        await session.execute(
            select(func.count()).select_from(Ci).where(
                Ci.location_id == location.id, Ci.deleted_at.is_(None), Ci.archived_at.is_(None)
            )
        )
    ).scalar_one()
    if used:
        raise Conflict(
            "В размещении есть действующие объекты — перенесите их перед архивированием",
            ci_count=int(used),
        )
    location.archived_at = datetime.now(UTC)
    await session.flush()
    await search_service.remove_entity(session, "LOCATION", location.id)
    return location
