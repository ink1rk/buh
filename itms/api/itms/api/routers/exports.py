from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from itms.api.deps import SessionDep, requires
from itms.domain.permissions import Permission
from itms.models.enums import CiStatus, CiType, Criticality
from itms.services import ci_service, export_service

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/ci.csv", dependencies=[requires(Permission.EXPORT_RUN)])
async def export_ci_csv(
    session: SessionDep,
    q: str | None = None,
    ci_type: Annotated[list[CiType] | None, Query()] = None,
    status: Annotated[list[CiStatus] | None, Query()] = None,
    criticality: Annotated[list[Criticality] | None, Query()] = None,
    location_id: uuid.UUID | None = None,
    archived: bool = False,
) -> Response:
    payload = await export_service.ci_csv(
        session,
        ci_service.CiFilter(
            q=q,
            ci_type=ci_type,
            status=status,
            criticality=criticality,
            location_id=location_id,
            archived=archived,
            limit=5000,
        ),
    )
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ci.csv"'},
    )
