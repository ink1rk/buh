from __future__ import annotations

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.power import (
    PowerFeedCreate,
    PowerFeedCreated,
    PowerLinkCreate,
    PowerLinkCreated,
    PowerMeasurementCreate,
    PowerMeasurementCreated,
    PowerNodeCreate,
    PowerNodeCreated,
    PowerOverview,
    PowerScenarioCreate,
    PowerScenarioCreated,
)
from itms.domain.permissions import Permission
from itms.services import power_service

router = APIRouter(prefix="/power", tags=["power"])


@router.get("", response_model=PowerOverview, dependencies=[requires(Permission.CI_READ)])
async def power_overview(session: SessionDep) -> PowerOverview:
    return PowerOverview.model_validate(await power_service.overview(session))


@router.post(
    "/nodes",
    response_model=PowerNodeCreated,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_node(payload: PowerNodeCreate, session: SessionDep) -> PowerNodeCreated:
    created = await power_service.create_node(session, payload.model_dump())
    return PowerNodeCreated.model_validate(created)


@router.post(
    "/links",
    response_model=PowerLinkCreated,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_link(payload: PowerLinkCreate, session: SessionDep) -> PowerLinkCreated:
    created = await power_service.create_link(session, payload.model_dump())
    return PowerLinkCreated.model_validate(created)


@router.post(
    "/feeds",
    response_model=PowerFeedCreated,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_feed(payload: PowerFeedCreate, session: SessionDep) -> PowerFeedCreated:
    created = await power_service.create_feed(session, payload.model_dump())
    return PowerFeedCreated.model_validate(created)


@router.post(
    "/measurements",
    response_model=PowerMeasurementCreated,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_measurement(
    payload: PowerMeasurementCreate, session: SessionDep
) -> PowerMeasurementCreated:
    created = await power_service.create_measurement(session, payload.model_dump())
    return PowerMeasurementCreated.model_validate(created)


@router.post(
    "/scenarios",
    response_model=PowerScenarioCreated,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_scenario(
    payload: PowerScenarioCreate, session: SessionDep
) -> PowerScenarioCreated:
    created = await power_service.create_scenario(session, payload.model_dump())
    return PowerScenarioCreated.model_validate(created)
