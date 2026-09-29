from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.directory import (
    DepartmentRead,
    DepartmentWrite,
    EmployeeRead,
    EmployeeUpdate,
    EmployeeWrite,
    OrganizationRead,
    OrganizationWrite,
    ResponsibilityRead,
    ResponsibilityWrite,
    WorkloadRow,
)
from itms.domain.permissions import Permission
from itms.models.enums import EmployeeStatus
from itms.services import directory_service

router = APIRouter(prefix="/directory", tags=["directory"])


@router.get("/organization", response_model=OrganizationRead | None,
            dependencies=[requires(Permission.DIRECTORY_READ)])
async def get_organization(session: SessionDep) -> OrganizationRead | None:
    org = await directory_service.get_organization(session)
    return OrganizationRead.model_validate(org) if org else None


@router.put("/organization", response_model=OrganizationRead,
            dependencies=[requires(Permission.DIRECTORY_WRITE)])
async def upsert_organization(payload: OrganizationWrite, session: SessionDep) -> OrganizationRead:
    data = payload.model_dump(exclude_unset=True)
    org = await directory_service.upsert_organization(session, data)
    return OrganizationRead.model_validate(org)


@router.get("/departments", response_model=list[DepartmentRead],
            dependencies=[requires(Permission.DIRECTORY_READ)])
async def list_departments(session: SessionDep) -> list[DepartmentRead]:
    return [
        DepartmentRead.model_validate(d) for d in await directory_service.list_departments(session)
    ]


@router.post("/departments", response_model=DepartmentRead, status_code=201,
             dependencies=[requires(Permission.DIRECTORY_WRITE)])
async def create_department(payload: DepartmentWrite, session: SessionDep) -> DepartmentRead:
    department = await directory_service.create_department(
        session, payload.model_dump(exclude_unset=True)
    )
    return DepartmentRead.model_validate(department)


@router.patch("/departments/{department_id}", response_model=DepartmentRead,
              dependencies=[requires(Permission.DIRECTORY_WRITE)])
async def update_department(
    department_id: uuid.UUID, payload: DepartmentWrite, session: SessionDep
) -> DepartmentRead:
    department = await directory_service.update_department(
        session, department_id, payload.model_dump(exclude_unset=True)
    )
    return DepartmentRead.model_validate(department)


@router.get("/employees", response_model=list[EmployeeRead],
            dependencies=[requires(Permission.DIRECTORY_READ)])
async def list_employees(
    session: SessionDep,
    q: str | None = None,
    status: Annotated[list[EmployeeStatus] | None, Query()] = None,
    department_id: uuid.UUID | None = None,
) -> list[EmployeeRead]:
    employees = await directory_service.list_employees(
        session, q=q, status=status, department_id=department_id
    )
    return [EmployeeRead.model_validate(e) for e in employees]


@router.post("/employees", response_model=EmployeeRead, status_code=201,
             dependencies=[requires(Permission.DIRECTORY_WRITE)])
async def create_employee(payload: EmployeeWrite, session: SessionDep) -> EmployeeRead:
    employee = await directory_service.create_employee(
        session, payload.model_dump(exclude_unset=True)
    )
    return EmployeeRead.model_validate(employee)


@router.get("/employees/{employee_id}", response_model=EmployeeRead,
            dependencies=[requires(Permission.DIRECTORY_READ)])
async def get_employee(employee_id: uuid.UUID, session: SessionDep) -> EmployeeRead:
    return EmployeeRead.model_validate(await directory_service.get_employee(session, employee_id))


@router.patch("/employees/{employee_id}", response_model=EmployeeRead,
              dependencies=[requires(Permission.DIRECTORY_WRITE)])
async def update_employee(
    employee_id: uuid.UUID, payload: EmployeeUpdate, session: SessionDep
) -> EmployeeRead:
    employee = await directory_service.update_employee(
        session, employee_id, payload.model_dump(exclude_unset=True)
    )
    return EmployeeRead.model_validate(employee)


@router.get("/responsibilities", response_model=list[ResponsibilityRead],
            dependencies=[requires(Permission.DIRECTORY_READ)])
async def list_areas(session: SessionDep) -> list[ResponsibilityRead]:
    areas = await directory_service.list_areas(session)
    return [ResponsibilityRead.model_validate(area) for area in areas]


@router.post("/responsibilities", response_model=ResponsibilityRead, status_code=201,
             dependencies=[requires(Permission.DIRECTORY_WRITE)])
async def create_area(payload: ResponsibilityWrite, session: SessionDep) -> ResponsibilityRead:
    area = await directory_service.create_area(session, payload.model_dump(exclude_unset=True))
    return ResponsibilityRead.model_validate(area)


@router.get("/workload", response_model=list[WorkloadRow],
            dependencies=[requires(Permission.DIRECTORY_READ)])
async def workload(session: SessionDep) -> list[WorkloadRow]:
    rows = await directory_service.workload_summary(session)
    return [WorkloadRow.model_validate(row) for row in rows]
