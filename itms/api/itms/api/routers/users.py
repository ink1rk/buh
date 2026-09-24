from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import CurrentUser, SessionDep, requires
from itms.api.schemas.directory import UserCreate, UserRead, UserUpdate
from itms.domain.permissions import Permission
from itms.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead], dependencies=[requires(Permission.USER_MANAGE)])
async def list_users(session: SessionDep) -> list[UserRead]:
    return [UserRead.model_validate(item) for item in await user_service.list_users(session)]


@router.post(
    "",
    response_model=UserRead,
    status_code=201,
    dependencies=[requires(Permission.USER_MANAGE)],
)
async def create_user(payload: UserCreate, session: SessionDep, actor: CurrentUser) -> UserRead:
    user = await user_service.create_user(session, actor, payload.model_dump())
    return UserRead.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[requires(Permission.USER_MANAGE)],
)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, session: SessionDep, actor: CurrentUser
) -> UserRead:
    user = await user_service.update_user(
        session, actor, user_id, payload.model_dump(exclude_unset=True)
    )
    return UserRead.model_validate(user)
