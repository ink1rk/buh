from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def password_problems(password: str) -> list[str]:
    """Возвращает коды проблем пароля; пустой список означает, что пароль принимается."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append("password_too_short")
    if password.isdigit() or password.isalpha():
        problems.append("password_too_simple")
    if password.lower() in {"password", "пароль", "12345678901", "qwertyuiop"}:
        problems.append("password_common")
    return problems


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_fingerprint(token: str) -> str:
    """В БД хранится только отпечаток токена сессии, не сам токен."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


@dataclass
class RateLimiter:
    """Простой лимитер в памяти процесса: достаточно для одноузловой self-hosted установки."""

    limit: int
    window_seconds: int
    _hits: dict[str, list[float]] = field(default_factory=dict)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = [t for t in self._hits.get(key, []) if t > window_start]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def retry_after(self, key: str) -> int:
        hits = self._hits.get(key, [])
        if not hits:
            return 0
        return max(0, int(self.window_seconds - (time.monotonic() - hits[0])) + 1)
