from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, init_db
from app.services.bank_sync import refresh_fingerprints
from app.services.seed import seed_if_empty


def create_app(*, testing: bool = False) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not testing:
            await init_db()
            async with AsyncSessionLocal() as session:
                await refresh_fingerprints(session)
                if settings.seed_demo:
                    await seed_if_empty(session)
                await session.commit()
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": settings.app_version, "name": settings.app_name}

    return app


app = create_app()
