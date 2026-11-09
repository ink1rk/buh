from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.robotparser import RobotFileParser

from app.adapters.http_client import USER_AGENT
from app.core.redact import redact
from app.core.timeutil import utcnow


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    circuit_open: bool = False
    enabled: bool = True
    robots_blocked: bool = False
    tos_blocked: bool = False
    health: str = "unknown"
    last_error: str = ""
    last_success_at: datetime | None = None
    next_retry_at: datetime | None = None

    def note_success(self, now: datetime | None = None) -> None:
        moment = now or utcnow()
        self.consecutive_failures = 0
        self.circuit_open = False
        self.health = "ok"
        self.last_error = ""
        self.last_success_at = moment
        self.next_retry_at = None

    def note_failure(self, error: str, now: datetime | None = None, threshold: int = 5) -> None:
        moment = now or utcnow()
        self.consecutive_failures += 1
        self.last_error = redact(error)[:300]
        self.health = "degraded"
        if self.consecutive_failures >= threshold:
            self.circuit_open = True
            delay = min(3600, 2 ** self.consecutive_failures)
            self.next_retry_at = moment + timedelta(seconds=delay)
            self.health = "open"

    def allow_request(self, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        if not self.enabled or self.robots_blocked or self.tos_blocked:
            return False
        if self.circuit_open and self.next_retry_at and moment < self.next_retry_at:
            return False
        return True


def robots_allow(robots_txt: str, url: str, user_agent: str = USER_AGENT) -> bool:
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return bool(parser.can_fetch(user_agent, url))


def apply_robots(state: CircuitState, robots_txt: str, url: str) -> bool:
    allowed = robots_allow(robots_txt, url)
    if not allowed:
        state.enabled = False
        state.robots_blocked = True
        state.health = "blocked"
        state.last_error = "robots_disallow"
    return allowed


def apply_tos_block(state: CircuitState, reason: str) -> None:
    state.enabled = False
    state.tos_blocked = True
    state.health = "blocked"
    state.last_error = reason[:300]
