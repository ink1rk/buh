from __future__ import annotations

from fastapi import APIRouter, Request, Response

from itms.api.deps import CurrentUser, SessionDep
from itms.api.schemas.common import Ok
from itms.api.schemas.directory import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdate,
    SessionUser,
)
from itms.core.config import settings
from itms.core.errors import RateLimited
from itms.core.security import RateLimiter
from itms.domain.permissions import ROLE_PERMISSIONS
from itms.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_login_limiter = RateLimiter(
    limit=settings.login_rate_limit, window_seconds=settings.login_rate_window_seconds
)


def _set_session_cookies(response: Response, token: str, csrf: str, max_age: int) -> None:
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        path="/",
    )
    # CSRF-токен читается скриптом и возвращается заголовком: схема double-submit.
    response.set_cookie(
        settings.csrf_cookie,
        csrf,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        path="/",
    )


def _session_user(user) -> SessionUser:
    return SessionUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        locale=user.locale,
        theme=user.theme,
        permissions=sorted(p.value for p in ROLE_PERMISSIONS.get(user.role, frozenset())),
    )


@router.post("/login", response_model=SessionUser)
async def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> SessionUser:
    client_ip = request.client.host if request.client else "unknown"
    limit_key = f"{client_ip}:{payload.email}"
    if not _login_limiter.check(limit_key):
        raise RateLimited(
            "Слишком много попыток входа, попробуйте позже",
            retry_after=_login_limiter.retry_after(limit_key),
        )

    result = await auth_service.authenticate(
        session,
        email=payload.email,
        password=payload.password,
        ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    _login_limiter.reset(limit_key)
    _set_session_cookies(
        response,
        result.session_token,
        result.csrf_token,
        max_age=settings.session_ttl_hours * 3600,
    )
    return _session_user(result.user)


@router.post("/logout", response_model=Ok)
async def logout(request: Request, response: Response, session: SessionDep) -> Ok:
    token = request.cookies.get(settings.session_cookie)
    if token:
        await auth_service.logout(session, token)
    response.delete_cookie(settings.session_cookie, path="/")
    response.delete_cookie(settings.csrf_cookie, path="/")
    return Ok()


@router.get("/me", response_model=SessionUser)
async def me(user: CurrentUser) -> SessionUser:
    return _session_user(user)


@router.patch("/me", response_model=SessionUser)
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: SessionDep
) -> SessionUser:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    await session.flush()
    return _session_user(user)


@router.post("/password", response_model=Ok)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, session: SessionDep, response: Response
) -> Ok:
    await auth_service.change_password(
        session, user, current=payload.current_password, new=payload.new_password
    )
    response.delete_cookie(settings.session_cookie, path="/")
    response.delete_cookie(settings.csrf_cookie, path="/")
    return Ok()
