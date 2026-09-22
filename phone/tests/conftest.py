import datetime
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Своя база на каждый тест: телефонные данные не должны перетекать."""
    path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("PHONE_DB", path)

    from phone import store
    store._local.__dict__.pop("conn", None)
    store.migrate()
    yield path
    conn = getattr(store._local, "conn", None)
    if conn is not None:
        conn.close()
        store._local.__dict__.pop("conn", None)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except OSError:
            pass


@pytest.fixture
def device():
    from phone import store
    return store.register_device("iPhone Кирилла", kind="iphone", model="iPhone 17 Pro")


def at(days_ago=0, hour=12, minute=0):
    """Момент в часовом поясе владельца: сутки считаются по нему, не по UTC."""
    from phone.config import config
    now = datetime.datetime.now(config.tz)
    day = now.date() - datetime.timedelta(days=days_ago)
    return datetime.datetime.combine(
        day, datetime.time(hour, minute), tzinfo=config.tz).timestamp()
