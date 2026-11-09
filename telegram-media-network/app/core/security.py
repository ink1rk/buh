from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ROLES = ("OWNER", "EDITOR", "REVIEWER_SECURITY", "VIEWER", "SERVICE")
ROLE_RANK = {name: index for index, name in enumerate(ROLES)}

_hasher = PasswordHasher()


class AttemptLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 900) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, list[float]] = {}

    def too_many(self, key: str, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        events = [stamp for stamp in self._events.get(key, []) if moment - stamp < self.window]
        self._events[key] = events
        return len(events) >= self.limit

    def record(self, key: str, now: float | None = None) -> None:
        moment = time.time() if now is None else now
        self._events.setdefault(key, []).append(moment)

    def reset(self) -> None:
        self._events.clear()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code or not code.isdigit():
        return False
    return bool(pyotp.TOTP(secret).verify(code, valid_window=1))


def new_totp_secret() -> str:
    return pyotp.random_base32()


@dataclass(frozen=True)
class Policy:
    dry_run: bool
    publish_enabled: bool
    kill_switch: bool
    sponsored_enabled: bool

    def network_allowed(self, channel_publish_enabled: bool, channel_paused: bool) -> bool:
        return (
            not self.dry_run
            and self.publish_enabled
            and not self.kill_switch
            and channel_publish_enabled
            and not channel_paused
        )
