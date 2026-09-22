from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from enum import StrEnum


class ActorKind(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    IMPORT = "IMPORT"
    JOB = "JOB"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Происхождение изменения: в рамках чего и почему оно выполнено.

    Заполняется из заголовков запроса (X-Change-Id, X-Project-Id, X-Task-Id, X-Reason)
    либо программно и автоматически попадает в каждую запись аудита.
    """

    change_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    reason: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.change_id, self.project_id, self.task_id, self.document_id, self.reason)
        )

    @property
    def has_link(self) -> bool:
        return any((self.change_id, self.project_id, self.task_id, self.document_id))


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actor_id: uuid.UUID | None = None
    actor_kind: ActorKind = ActorKind.SYSTEM
    actor_label: str | None = None
    source: str = "api"
    ip: str | None = None
    user_agent: str | None = None
    provenance: Provenance = field(default_factory=Provenance)


# Значение по умолчанию неизменяемо (frozen dataclass), поэтому общий объект безопасен.
_ctx: ContextVar[RequestContext] = ContextVar(
    "itms_request_context", default=RequestContext()  # noqa: B039
)


def current_context() -> RequestContext:
    return _ctx.get()


def set_context(ctx: RequestContext) -> None:
    _ctx.set(ctx)


@contextmanager
def use_context(ctx: RequestContext) -> Iterator[RequestContext]:
    token = _ctx.set(ctx)
    try:
        yield ctx
    finally:
        _ctx.reset(token)


@contextmanager
def use_provenance(**kwargs: object) -> Iterator[RequestContext]:
    """Временно уточняет происхождение изменений внутри блока."""
    base = current_context()
    prov = replace(base.provenance, **kwargs)  # type: ignore[arg-type]
    with use_context(replace(base, provenance=prov)) as ctx:
        yield ctx


@contextmanager
def system_context(source: str = "job", label: str = "system") -> Iterator[RequestContext]:
    with use_context(
        RequestContext(actor_kind=ActorKind.SYSTEM, actor_label=label, source=source)
    ) as ctx:
        yield ctx
