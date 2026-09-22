from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest

os.environ.setdefault(
    "ITMS_DATABASE_URL", "postgresql+asyncpg://itms:itms@localhost:5432/itms_test"
)
os.environ.setdefault("ITMS_STORAGE_BACKEND", "local")
os.environ.setdefault("ITMS_LOCAL_STORAGE_PATH", "/tmp/itms-test-files")
os.environ.setdefault("ITMS_BOOTSTRAP_OWNER_PASSWORD", "owner-password-1")
os.environ.setdefault("ITMS_ENV", "test")

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.config import settings
from itms.core.context import ActorKind, RequestContext, set_context
from itms.core.db import dispose_engine, get_engine, session_scope
from itms.domain.audit_rules import configure_audit
from itms.main import app
from itms.services import auth_service, directory_service

TABLES_TO_CLEAR = (
    "power_scenario_item",
    "power_scenario",
    "power_measurement",
    "power_link",
    "power_feed",
    "power_node",
    "audit_change",
    "time_entry",
    "task_dependency",
    "task_ci",
    "project_ci",
    "project_member",
    "task",
    "milestone",
    "phase",
    "project",
    "diagram_edge",
    "diagram_node",
    "diagram",
    "rack_mount",
    "rack",
    "audit_log",
    "interface_vlan",
    "ip_address",
    "connection",
    "interface",
    "device",
    "prefix",
    "vlan",
    "vrf",
    "cable_route",
    "port_template",
    "device_model",
    "manufacturer",
    "ci_tag",
    "ci_relation",
    "document_version",
    "document_link",
    "attachment",
    "document",
    "document_folder",
    "file_object",
    "custom_field_value",
    "custom_field_def",
    "search_index",
    "import_job",
    "outbox_event",
    "ci",
    "location",
    "employee_responsibility",
    "responsibility_area",
    "user_session",
    "user_account",
    "employee",
    "department",
    "organization",
    "tag",
    "app_setting",
)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Тесты идут на настоящем PostgreSQL: схема накатывается миграциями."""
    env = {**os.environ, "ITMS_DATABASE_URL": settings.database_url}
    alembic_cmd = [sys.executable, "-m", "alembic"]
    subprocess.run([*alembic_cmd, "downgrade", "base"], check=False, env=env, capture_output=True)
    result = subprocess.run([*alembic_cmd, "upgrade", "head"], env=env, capture_output=True)
    if result.returncode != 0:  # pragma: no cover
        raise RuntimeError(result.stderr.decode())
    configure_audit()
    yield
    asyncio.run(dispose_engine())


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_immutable")
        )
        await connection.execute(
            text("ALTER TABLE audit_change DISABLE TRIGGER trg_audit_change_immutable")
        )
        await connection.execute(
            text("TRUNCATE " + ", ".join(TABLES_TO_CLEAR) + " RESTART IDENTITY CASCADE")
        )
        await connection.execute(
            text("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_immutable")
        )
        await connection.execute(
            text("ALTER TABLE audit_change ENABLE TRIGGER trg_audit_change_immutable")
        )
    set_context(RequestContext(actor_kind=ActorKind.SYSTEM, actor_label="tests", source="test"))
    yield


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as db_session:
        yield db_session


@pytest.fixture
async def owner() -> AsyncIterator[uuid.UUID]:
    async with session_scope() as db_session:
        user, _ = await auth_service.bootstrap_owner(db_session)
        await directory_service.upsert_organization(db_session, {"name": "Тестовая организация"})
        user_id = user.id
    yield user_id


@pytest.fixture
async def client(owner: uuid.UUID) -> AsyncIterator[AsyncClient]:
    """Клиент с выполненным входом: куки сессии и CSRF выставлены."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            f"{settings.api_prefix}/auth/login",
            json={
                "email": settings.bootstrap_owner_email,
                "password": settings.bootstrap_owner_password,
            },
        )
        assert response.status_code == 200, response.text
        csrf = http_client.cookies.get(settings.csrf_cookie)
        http_client.headers[settings.csrf_header] = csrf or ""
        yield http_client


@pytest.fixture
async def anon_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def api() -> str:
    return settings.api_prefix
