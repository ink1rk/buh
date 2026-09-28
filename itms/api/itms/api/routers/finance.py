from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok
from itms.api.schemas.finance import FinanceRead, FinanceUpdate, FinanceWrite
from itms.domain.permissions import Permission
from itms.services import finance_service

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("", response_model=list[FinanceRead], dependencies=[requires(Permission.CI_READ)])
async def list_entries(session: SessionDep, kind: str | None = None) -> list[FinanceRead]:
    rows = await finance_service.list_entries(session, kind)
    return [FinanceRead.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=FinanceRead,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_entry(payload: FinanceWrite, session: SessionDep) -> FinanceRead:
    item = await finance_service.create_entry(session, payload.model_dump())
    return FinanceRead.model_validate(item)


@router.patch(
    "/{entry_id}",
    response_model=FinanceRead,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_entry(
    entry_id: uuid.UUID, payload: FinanceUpdate, session: SessionDep
) -> FinanceRead:
    item = await finance_service.update_entry(
        session, entry_id, payload.model_dump(exclude_unset=True)
    )
    return FinanceRead.model_validate(item)


@router.delete("/{entry_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)])
async def delete_entry(entry_id: uuid.UUID, session: SessionDep) -> Ok:
    await finance_service.delete_entry(session, entry_id)
    return Ok()
