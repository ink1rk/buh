from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

LOCK_KEY = 8787001


class LeaderLock:
    """One scheduler process holds a Postgres advisory lock for its whole lifetime."""

    def __init__(self, engine: Engine) -> None:
        self._conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        self.held = False

    def acquire(self) -> bool:
        got = self._conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        self.held = bool(got)
        return self.held

    def release(self) -> None:
        if self.held:
            self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            self.held = False

    def close(self) -> None:
        self.release()
        self._conn.close()
