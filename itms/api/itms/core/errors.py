from __future__ import annotations

from typing import Any


class ItmsError(Exception):
    """Базовая ошибка домена. Код ошибки локализуется на клиенте."""

    status_code = 400
    code = "error"

    def __init__(self, message: str | None = None, **details: Any) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details or {},
            }
        }


class NotFound(ItmsError):
    status_code = 404
    code = "not_found"


class Conflict(ItmsError):
    status_code = 409
    code = "conflict"


class Invalid(ItmsError):
    status_code = 422
    code = "invalid"


class Unauthorized(ItmsError):
    status_code = 401
    code = "unauthorized"


class Forbidden(ItmsError):
    status_code = 403
    code = "forbidden"


class RateLimited(ItmsError):
    status_code = 429
    code = "rate_limited"


class ProvenanceRequired(Invalid):
    """Критичное поле изменено без указания причины или ссылки на проект/изменение/задачу."""

    code = "provenance_required"


class DeletionForbidden(Forbidden):
    """Физическое удаление критического объекта запрещено — только RETIRED/архив."""

    code = "deletion_forbidden"


class CycleDetected(Conflict):
    code = "cycle_detected"
