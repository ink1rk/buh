from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from itms.core.context import ActorKind, current_context
from itms.core.errors import ProvenanceRequired
from itms.models.audit import AuditChange, AuditLog
from itms.models.base import VersionMixin
from itms.models.enums import AuditAction

#: Поля, которые не несут смысла в истории изменений.
GLOBAL_IGNORED_FIELDS = frozenset(
    {"updated_at", "created_at", "search_tsv", "version", "last_seen_at", "path", "depth"}
)


@dataclass(frozen=True, slots=True)
class AuditConfig:
    entity_type: str
    label_attr: str = "name"
    #: Изменение этих полей требует указания причины либо ссылки на проект/изменение/задачу.
    critical_fields: frozenset[str] = field(default_factory=frozenset)
    ignore_fields: frozenset[str] = field(default_factory=frozenset)
    audit_delete: bool = True


_REGISTRY: dict[type, AuditConfig] = {}
_INSTALLED = False


def register_audit(model: type, config: AuditConfig) -> None:
    _REGISTRY[model] = config


def audit_config_for(obj: object) -> AuditConfig | None:
    return _REGISTRY.get(type(obj))


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return str(value)


def _label_of(obj: object, config: AuditConfig) -> str | None:
    label = getattr(obj, config.label_attr, None)
    return str(label) if label is not None else None


def _collect_changes(obj: object, config: AuditConfig) -> list[tuple[str, Any, Any]]:
    state = inspect(obj)
    ignored = GLOBAL_IGNORED_FIELDS | config.ignore_fields
    changes: list[tuple[str, Any, Any]] = []
    for attr in state.mapper.column_attrs:
        name = attr.key
        if name in ignored:
            continue
        history = state.attrs[name].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        if old == new:
            continue
        changes.append((name, old, new))
    return changes


def _build_log(
    obj: object,
    config: AuditConfig,
    action: AuditAction,
    changes: list[tuple[str, Any, Any]],
) -> AuditLog:
    ctx = current_context()
    prov = ctx.provenance
    log = AuditLog(
        actor_id=ctx.actor_id,
        actor_kind=ctx.actor_kind.value,
        actor_label=ctx.actor_label,
        request_id=ctx.request_id,
        entity_type=config.entity_type,
        entity_id=getattr(obj, "id", None),
        entity_label=_label_of(obj, config),
        action=action,
        change_id=prov.change_id,
        project_id=prov.project_id,
        task_id=prov.task_id,
        document_id=prov.document_id,
        reason=prov.reason,
        source=ctx.source,
        ip=ctx.ip,
    )
    log.changes = [
        AuditChange(field=name, old_value=to_jsonable(old), new_value=to_jsonable(new))
        for name, old, new in changes
    ]
    return log


def _require_provenance(obj: object, config: AuditConfig, changed_fields: set[str]) -> None:
    """Критичные поля нельзя менять «молча»: нужна причина или ссылка на источник."""
    ctx = current_context()
    if ctx.actor_kind in (ActorKind.SYSTEM, ActorKind.IMPORT, ActorKind.JOB):
        return
    critical = changed_fields & config.critical_fields
    if not critical:
        return
    prov = ctx.provenance
    if prov.is_empty:
        raise ProvenanceRequired(
            "Изменение критичного параметра требует указания причины или ссылки "
            "на проект, изменение либо задачу",
            entity_type=config.entity_type,
            entity_id=str(getattr(obj, "id", "")),
            fields=sorted(critical),
        )


def _derive_action(changed_fields: set[str]) -> AuditAction:
    if "archived_at" in changed_fields:
        return AuditAction.ARCHIVE
    if "deleted_at" in changed_fields:
        return AuditAction.DELETE
    if "status" in changed_fields:
        return AuditAction.STATUS
    return AuditAction.UPDATE


def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    logs: list[AuditLog] = []

    for obj in session.new:
        config = audit_config_for(obj)
        if config is None:
            continue
        # Идентификатор нужен записи истории уже сейчас: она создаётся до flush.
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        changes = [
            (name, None, getattr(obj, name, None))
            for name in (
                a.key
                for a in inspect(obj).mapper.column_attrs
                if a.key not in (GLOBAL_IGNORED_FIELDS | config.ignore_fields)
            )
            if getattr(obj, name, None) is not None
        ]
        logs.append(_build_log(obj, config, AuditAction.CREATE, changes))

    for obj in session.dirty:
        config = audit_config_for(obj)
        if config is None or not session.is_modified(obj, include_collections=False):
            continue
        changes = _collect_changes(obj, config)
        if not changes:
            continue
        changed_fields = {name for name, _, _ in changes}
        _require_provenance(obj, config, changed_fields)
        if isinstance(obj, VersionMixin):
            obj.version = (obj.version or 0) + 1
        logs.append(_build_log(obj, config, _derive_action(changed_fields), changes))

    for obj in session.deleted:
        config = audit_config_for(obj)
        if config is None or not config.audit_delete:
            continue
        logs.append(_build_log(obj, config, AuditAction.DELETE, []))

    for log in logs:
        session.add(log)


def install_audit() -> None:
    """Подключает аудит ко всем сессиям. Вызывается один раз при старте приложения."""
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _INSTALLED = True


def uninstall_audit() -> None:  # pragma: no cover - используется в тестах
    global _INSTALLED
    if _INSTALLED:
        event.remove(Session, "before_flush", _before_flush)
        _INSTALLED = False
