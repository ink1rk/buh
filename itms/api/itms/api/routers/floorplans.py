from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.floorplan import (
    FloorplanCreate,
    FloorplanSummary,
    FloorplanView,
    ItemMove,
    ItemPlace,
)
from itms.domain.permissions import Permission
from itms.services import floorplan_service

router = APIRouter(prefix="/floorplans", tags=["floorplans"])


@router.get("", response_model=list[FloorplanSummary], dependencies=[requires(Permission.CI_READ)])
async def list_plans(session: SessionDep) -> list[FloorplanSummary]:
    rows = await floorplan_service.list_plans(session)
    return [FloorplanSummary.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=FloorplanView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_plan(payload: FloorplanCreate, session: SessionDep) -> FloorplanView:
    view = await floorplan_service.create_plan(session, payload.model_dump())
    return FloorplanView.model_validate(view)


@router.get("/{plan_id}", response_model=FloorplanView, dependencies=[requires(Permission.CI_READ)])
async def get_plan(plan_id: uuid.UUID, session: SessionDep) -> FloorplanView:
    return FloorplanView.model_validate(await floorplan_service.view(session, plan_id))


@router.post(
    "/{plan_id}/items",
    response_model=FloorplanView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def place_item(plan_id: uuid.UUID, payload: ItemPlace, session: SessionDep) -> FloorplanView:
    view = await floorplan_service.place_item(session, plan_id, payload.model_dump())
    return FloorplanView.model_validate(view)


@router.patch(
    "/{plan_id}/items/{item_id}",
    response_model=FloorplanView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def move_item(
    plan_id: uuid.UUID, item_id: uuid.UUID, payload: ItemMove, session: SessionDep
) -> FloorplanView:
    view = await floorplan_service.move_item(
        session, plan_id, item_id, payload.model_dump(exclude_unset=True)
    )
    return FloorplanView.model_validate(view)


@router.delete(
    "/{plan_id}/items/{item_id}",
    response_model=FloorplanView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def remove_item(plan_id: uuid.UUID, item_id: uuid.UUID, session: SessionDep) -> FloorplanView:
    return FloorplanView.model_validate(
        await floorplan_service.remove_item(session, plan_id, item_id)
    )
