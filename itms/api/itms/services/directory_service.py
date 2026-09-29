from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, NotFound
from itms.domain.search import employee_document
from itms.models.cmdb import Ci
from itms.models.directory import (
    Department,
    Employee,
    EmployeeResponsibility,
    Organization,
    ResponsibilityArea,
)
from itms.models.enums import EmployeeStatus
from itms.services import search_service

EMPLOYEE_FIELDS = (
    "full_name",
    "position",
    "email",
    "phone",
    "telegram",
    "support_line",
    "status",
    "hired_on",
    "dismissed_on",
    "weekly_hours",
    "department_id",
    "notes",
)


async def get_organization(session: AsyncSession) -> Organization | None:
    return (
        await session.execute(select(Organization).order_by(Organization.created_at).limit(1))
    ).scalar_one_or_none()


async def upsert_organization(session: AsyncSession, data: dict[str, Any]) -> Organization:
    org = await get_organization(session)
    if org is None:
        org = Organization(name=data["name"])
        session.add(org)
    for key in ("name", "full_name", "inn", "address", "timezone", "notes"):
        if key in data and data[key] is not None:
            setattr(org, key, data[key])
    await session.flush()
    return org


async def require_organization(session: AsyncSession) -> Organization:
    org = await get_organization(session)
    if org is None:
        raise NotFound("Организация ещё не заведена", code_hint="organization_missing")
    return org


async def list_departments(session: AsyncSession) -> list[Department]:
    rows = await session.execute(select(Department).order_by(Department.name))
    return list(rows.scalars().unique())


async def create_department(session: AsyncSession, data: dict[str, Any]) -> Department:
    org = await require_organization(session)
    department = Department(
        organization_id=org.id,
        name=data["name"],
        code=data.get("code"),
        parent_id=data.get("parent_id"),
        head_employee_id=data.get("head_employee_id"),
        description=data.get("description"),
    )
    session.add(department)
    await session.flush()
    return department


async def update_department(
    session: AsyncSession, department_id: uuid.UUID, data: dict[str, Any]
) -> Department:
    department = (
        await session.execute(select(Department).where(Department.id == department_id))
    ).scalar_one_or_none()
    if department is None:
        raise NotFound("Отдел не найден", entity_id=str(department_id))
    for key in ("name", "code", "parent_id", "head_employee_id", "description"):
        if key in data:
            setattr(department, key, data[key])
    await session.flush()
    return department


async def list_employees(
    session: AsyncSession,
    *,
    q: str | None = None,
    status: list[EmployeeStatus] | None = None,
    department_id: uuid.UUID | None = None,
) -> list[Employee]:
    stmt = select(Employee).where(Employee.deleted_at.is_(None))
    if q:
        stmt = stmt.where(func.lower(Employee.full_name).like(f"%{q.lower()}%"))
    if status:
        stmt = stmt.where(Employee.status.in_(status))
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    rows = await session.execute(stmt.order_by(Employee.full_name))
    return list(rows.scalars().unique())


async def refresh_employee(session: AsyncSession, employee: Employee) -> Employee:
    await session.refresh(employee)
    await session.refresh(employee, attribute_names=["responsibilities"])
    return employee


async def get_employee(session: AsyncSession, employee_id: uuid.UUID) -> Employee:
    employee = (
        await session.execute(
            select(Employee).where(Employee.id == employee_id, Employee.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if employee is None:
        raise NotFound("Сотрудник не найден", entity_id=str(employee_id))
    return employee


async def create_employee(session: AsyncSession, data: dict[str, Any]) -> Employee:
    org = await require_organization(session)
    employee = Employee(
        organization_id=org.id,
        full_name=data["full_name"],
        **{k: v for k, v in data.items() if k in EMPLOYEE_FIELDS and k != "full_name"},
    )
    session.add(employee)
    await session.flush()
    if data.get("responsibility_ids"):
        await set_responsibilities(session, employee.id, data["responsibility_ids"])
    await search_service.index_entity(session, employee.id, employee_document(employee))
    return await refresh_employee(session, employee)


async def update_employee(
    session: AsyncSession, employee_id: uuid.UUID, data: dict[str, Any]
) -> Employee:
    employee = await get_employee(session, employee_id)
    for key in EMPLOYEE_FIELDS:
        if key in data:
            setattr(employee, key, data[key])
    if "responsibility_ids" in data:
        await set_responsibilities(session, employee.id, data["responsibility_ids"] or [])
    await session.flush()
    await search_service.index_entity(session, employee.id, employee_document(employee))
    return await refresh_employee(session, employee)


async def set_responsibilities(
    session: AsyncSession, employee_id: uuid.UUID, area_ids: list[uuid.UUID]
) -> None:
    existing = (
        await session.execute(
            select(EmployeeResponsibility).where(
                EmployeeResponsibility.employee_id == employee_id
            )
        )
    ).scalars().all()
    for link in existing:
        await session.delete(link)
    for area_id in area_ids:
        session.add(EmployeeResponsibility(employee_id=employee_id, area_id=area_id))
    await session.flush()


async def list_areas(session: AsyncSession) -> list[ResponsibilityArea]:
    rows = await session.execute(select(ResponsibilityArea).order_by(ResponsibilityArea.name))
    return list(rows.scalars().unique())


async def create_area(session: AsyncSession, data: dict[str, Any]) -> ResponsibilityArea:
    duplicate = (
        await session.execute(
            select(ResponsibilityArea.id).where(ResponsibilityArea.name == data["name"])
        )
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict("Зона ответственности с таким названием уже есть")
    area = ResponsibilityArea(
        name=data["name"],
        code=data.get("code"),
        description=data.get("description"),
        color=data.get("color"),
    )
    session.add(area)
    await session.flush()
    return area


async def workload_summary(session: AsyncSession) -> list[dict[str, Any]]:
    """Сколько объектов закреплено за сотрудником.

    В Phase 1 нагрузка считается по владению объектами; задачи добавятся в Phase 5.
    """
    rows = await session.execute(
        select(Employee.id, Employee.full_name, Employee.status, func.count(Ci.id))
        .join(Ci, Ci.owner_employee_id == Employee.id, isouter=True)
        .where(Employee.deleted_at.is_(None))
        .group_by(Employee.id, Employee.full_name, Employee.status)
        .order_by(Employee.full_name)
    )
    return [
        {"id": row[0], "full_name": row[1], "status": row[2], "owned_ci": int(row[3])}
        for row in rows
    ]
