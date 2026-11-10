from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import Settings, assert_can_boot
from app.core.db import init_schema, make_engine, make_session_factory, prepare_database
from app.core.logging import configure_logging
from app.core.security import AttemptLimiter
from app.pipeline.urlsec import DEFAULT_ALLOWLIST, DefaultResolver
from app.publishing.gate import build_telegram_transport
from app.services.bootstrap import bootstrap
from app.ui.pages import router as ui_router


def create_app(settings: Settings | None = None, *, init_db: bool = True) -> FastAPI:
    settings = settings or Settings()
    assert_can_boot(settings)
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if init_db:
            engine = make_engine(settings.database_url)
            mode = os.environ.get("TMN_SCHEMA", "create_all")
            if mode == "check":
                from app.core.db import assert_schema_head

                assert_schema_head(engine)
            elif mode == "migrate":
                prepare_database(engine, "migrate")
            else:
                init_schema(engine)
            factory = make_session_factory(engine)
            app.state.engine = engine
            app.state.session_factory = factory
            with factory() as session:
                bootstrap(session, settings)
                session.commit()
        Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="Telegram Media Network", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.limiter = AttemptLimiter(settings.login_limit, settings.login_window_seconds)
    app.state.telegram_transport = build_telegram_transport(settings)
    app.state.resolver = DefaultResolver()
    app.state.allowlist = set(DEFAULT_ALLOWLIST)
    app.state.fetch_url = None
    app.include_router(router)
    app.include_router(ui_router)
    static_dir = Path(__file__).resolve().parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    return app


app = create_app()
