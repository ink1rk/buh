import datetime
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Every test gets its own database; nothing touches the live one."""
    path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("ASSISTANT_DB", path)

    from core import db
    db._local.__dict__.pop("conn", None)
    db.migrate()
    yield path
    conn = getattr(db._local, "conn", None)
    if conn is not None:
        conn.close()
        db._local.__dict__.pop("conn", None)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def daytime(monkeypatch):
    """Pin the clock: quiet hours must not decide whether the suite passes."""
    from core import notifications
    from core.config import config
    monkeypatch.setattr(
        notifications, "_now",
        lambda: datetime.datetime(2026, 9, 21, 12, 0, tzinfo=config.tz))


class FakeLLM:
    """Deterministic provider: tests must not depend on a model being up."""

    def __init__(self, structured=None, text="ответ"):
        self.structured = structured or {}
        self.text = text
        self.calls = []

    def generate(self, messages, **kwargs):
        self.calls.append(messages)
        return self.text, "fake"

    def structured_output(self, messages, schema, **kwargs):
        self.calls.append(messages)
        value = self.structured.get(schema.__name__)
        if value is None:
            return schema()
        return schema.model_validate(value) if isinstance(value, dict) else value


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def bus():
    """Bus wired exactly like in production: every event is audited."""
    from core import audit
    from core.events import EventBus
    instance = EventBus(workers=1)
    audit.subscribe(instance)
    yield instance
    instance.stop()
