from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from itms.core.config import settings

SCRATCH_DB = "itms_migrations_check"


def _dsn(database: str) -> str:
    url = make_url(settings.database_url).set(drivername="postgresql", database=database)
    return url.render_as_string(hide_password=False)


def _scratch_url() -> str:
    url = make_url(settings.database_url).set(database=SCRATCH_DB)
    return url.render_as_string(hide_password=False)


async def _run_sql(database: str, statements: list[str]) -> list[list[str]]:
    connection = await asyncpg.connect(_dsn(database))
    try:
        return [
            [row[0] for row in await connection.fetch(statement)]
            if statement.lstrip().upper().startswith("SELECT")
            else [await connection.execute(statement)]
            for statement in statements
        ]
    finally:
        await connection.close()


def _alembic(command: list[str], url: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *command],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "ITMS_DATABASE_URL": url},
        capture_output=True,
        check=False,
    )


@pytest.fixture
def scratch_database() -> Iterator[str]:
    """Отдельная пустая база: прогон миграций не должен трогать базу остальных тестов."""
    asyncio.run(
        _run_sql(
            "postgres",
            [
                f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)',
                f'CREATE DATABASE "{SCRATCH_DB}"',
            ],
        )
    )
    try:
        yield _scratch_url()
    finally:
        asyncio.run(_run_sql("postgres", [f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)']))


def test_migrations_apply_and_revert(scratch_database: str) -> None:
    """Схема должна накатываться, полностью откатываться и накатываться повторно."""
    up = _alembic(["upgrade", "head"], scratch_database)
    assert up.returncode == 0, up.stderr.decode()

    down = _alembic(["downgrade", "base"], scratch_database)
    assert down.returncode == 0, down.stderr.decode()

    leftovers, enums = asyncio.run(
        _run_sql(
            SCRATCH_DB,
            [
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'",
                "SELECT typname FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND t.typtype = 'e'",
            ],
        )
    )
    assert leftovers == [], f"после отката остались таблицы: {leftovers}"
    assert enums == [], f"после отката остались перечисления: {enums}"

    again = _alembic(["upgrade", "head"], scratch_database)
    assert again.returncode == 0, again.stderr.decode()
