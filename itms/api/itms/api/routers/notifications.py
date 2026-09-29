from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import CurrentUser, SessionDep
from itms.api.schemas.notifications import NotificationList
from itms.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
async def list_notifications(user: CurrentUser, session: SessionDep) -> NotificationList:
    return NotificationList.model_validate(await notification_service.inbox(session, user.id))


@router.post("/read", response_model=NotificationList)
async def read_all(user: CurrentUser, session: SessionDep) -> NotificationList:
    return NotificationList.model_validate(await notification_service.mark_all(session, user.id))


@router.post("/{notification_id}/read", response_model=NotificationList)
async def read_one(
    notification_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> NotificationList:
    payload = await notification_service.mark_read(session, user.id, notification_id)
    return NotificationList.model_validate(payload)
