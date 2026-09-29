"""Правила жизненного цикла объектов: статусы, архивирование, запрет удаления."""

from __future__ import annotations

from itms.core.errors import DeletionForbidden, Invalid
from itms.models.cmdb import Ci
from itms.models.enums import CI_STATUS_TRANSITIONS, CiStatus, Criticality

#: Типы объектов, участвующих в инженерной топологии: их нельзя удалять даже мягко.
TOPOLOGY_PROTECTED_TYPES = frozenset({"RACK", "DEVICE", "POWER_NODE", "CIRCUIT", "LOCATION"})


def validate_status_transition(current: CiStatus, target: CiStatus) -> None:
    if current == target:
        return
    allowed = CI_STATUS_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise Invalid(
            f"Переход статуса {current.value} → {target.value} не разрешён",
            code_hint="invalid_status_transition",
            current=current.value,
            target=target.value,
            allowed=sorted(s.value for s in allowed),
        )


def is_deletion_protected(ci: Ci) -> bool:
    """Критические и топологические объекты не удаляются — только RETIRED или архив."""
    if ci.criticality == Criticality.CRITICAL:
        return True
    return ci.ci_type.value in TOPOLOGY_PROTECTED_TYPES


def ensure_can_soft_delete(ci: Ci, *, has_history: bool) -> None:
    if is_deletion_protected(ci):
        raise DeletionForbidden(
            "Критические инфраструктурные объекты не удаляются: переведите объект "
            "в статус RETIRED или отправьте в архив",
            entity_id=str(ci.id),
            ci_type=ci.ci_type.value,
            criticality=ci.criticality.value,
        )
    if has_history:
        raise DeletionForbidden(
            "У объекта есть история изменений, задач или документов — используйте архивирование",
            entity_id=str(ci.id),
        )


def ensure_can_archive(ci: Ci) -> None:
    if ci.archived_at is not None:
        raise Invalid("Объект уже в архиве", entity_id=str(ci.id))


def ensure_can_restore(ci: Ci) -> None:
    if ci.archived_at is None and ci.deleted_at is None:
        raise Invalid("Объект не в архиве", entity_id=str(ci.id))
