from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from itms.api.deps import base_context
from itms.api.routers import (
    auth,
    catalog,
    ci,
    devices,
    diagrams,
    directory,
    documents,
    exports,
    files,
    finance,
    floorplans,
    ipam,
    locations,
    network,
    notifications,
    ops,
    platform,
    power,
    projects,
    racks,
    users,
    virtualization,
)
from itms.core.config import settings
from itms.core.context import set_context
from itms.core.db import dispose_engine, get_engine
from itms.core.errors import ItmsError
from itms.domain.audit_rules import configure_audit

logger = logging.getLogger("itms")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_audit()
    yield
    await dispose_engine()


class CommitBeforeResponse:
    """Коммитит сессию запроса до того, как клиент получит статус ответа.

    В актуальном FastAPI код после yield в зависимости выполняется уже после
    отправки ответа. Без этого вход сразу после смены пароля не видит новый хеш.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_and_commit(message):
            if message["type"] == "http.response.start" and message.get("status", 500) < 400:
                for session in list(scope.get("itms_sessions") or []):
                    if isinstance(session, AsyncSession) and session.in_transaction():
                        await session.commit()
            await send(message)

        await self.app(scope, receive, send_and_commit)


app = FastAPI(
    title="ITMS API",
    version="0.1.0",
    description="IT Management System — единая модель инфраструктуры, документации и работ",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
    lifespan=lifespan,
)

# Первый add_middleware оказывается ближе всех к приложению и коммитит
# в той же задаче, где открыта сессия.
app.add_middleware(CommitBeforeResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Контекст запроса и происхождение изменения живут в contextvars весь запрос."""
    ctx = base_context(request)
    set_context(ctx)
    response = await call_next(request)
    response.headers["X-Request-Id"] = ctx.request_id
    return response


@app.exception_handler(ItmsError)
async def itms_error_handler(request: Request, exc: ItmsError) -> JSONResponse:
    if exc.status_code >= 500:  # pragma: no cover
        logger.exception("Внутренняя ошибка", exc_info=exc)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["service"])
async def ready() -> dict[str, str]:
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}


prefix = settings.api_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(ci.router, prefix=prefix)
app.include_router(ci.relations_router, prefix=prefix)
app.include_router(locations.router, prefix=prefix)
app.include_router(catalog.router, prefix=prefix)
app.include_router(devices.router, prefix=prefix)
app.include_router(devices.interfaces_router, prefix=prefix)
app.include_router(network.router, prefix=prefix)
app.include_router(diagrams.router, prefix=prefix)
app.include_router(racks.router, prefix=prefix)
app.include_router(virtualization.router, prefix=prefix)
app.include_router(projects.router, prefix=prefix)
app.include_router(notifications.router, prefix=prefix)
app.include_router(power.router, prefix=prefix)
app.include_router(ipam.router, prefix=prefix)
app.include_router(directory.router, prefix=prefix)
app.include_router(users.router, prefix=prefix)
app.include_router(documents.router, prefix=prefix)
app.include_router(exports.router, prefix=prefix)
app.include_router(files.router, prefix=prefix)
app.include_router(finance.router, prefix=prefix)
app.include_router(floorplans.router, prefix=prefix)
app.include_router(ops.search_router, prefix=prefix)
app.include_router(ops.audit_router, prefix=prefix)
app.include_router(ops.import_router, prefix=prefix)
app.include_router(ops.dashboard_router, prefix=prefix)
app.include_router(platform.router, prefix=prefix)
