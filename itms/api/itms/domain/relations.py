"""Правила логических связей между объектами."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping

from itms.core.errors import CycleDetected, Invalid
from itms.models.enums import ACYCLIC_RELATIONS, CiType, RelationType

#: Питание описывается только моделью power_node + power_link.
#: Логическая связь между двумя узлами питания запрещена, чтобы не появился
#: второй источник истины по электрике.
POWER_TYPES = frozenset({CiType.POWER_NODE})


def validate_relation(
    *,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    source_type: CiType,
    target_type: CiType,
    rel_type: RelationType,
) -> None:
    if source_id == target_id:
        raise Invalid("Объект не может быть связан сам с собой", code_hint="self_relation")
    if source_type in POWER_TYPES and target_type in POWER_TYPES:
        raise Invalid(
            "Электропитание описывается моделью питания (power_link), "
            "а не логической связью между объектами",
            code_hint="power_relation_forbidden",
            rel_type=rel_type.value,
        )


def detect_cycle(
    *,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    rel_type: RelationType,
    edges: Mapping[uuid.UUID, Iterable[uuid.UUID]],
) -> None:
    """Проверяет, что новое ребро не замкнёт цикл.

    `edges` — существующие рёбра того же типа: источник → список целей.
    """
    if rel_type not in ACYCLIC_RELATIONS:
        return
    # Идём от target вниз по существующим рёбрам: если дойдём до source — будет цикл.
    seen: set[uuid.UUID] = set()
    stack: list[uuid.UUID] = [target_id]
    while stack:
        node = stack.pop()
        if node == source_id:
            raise CycleDetected(
                "Связь замыкает цикл зависимостей",
                rel_type=rel_type.value,
                source_id=str(source_id),
                target_id=str(target_id),
            )
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))


#: Как группируются связи в контекстной панели карточки объекта.
RELATION_GROUPS: dict[str, tuple[RelationType, ...]] = {
    "depends_on": (RelationType.DEPENDS_ON, RelationType.USES_STORAGE),
    "hosting": (RelationType.RUNS_ON, RelationType.MEMBER_OF, RelationType.PART_OF),
    "network": (RelationType.CONNECTED_TO,),
    "protection": (RelationType.BACKED_UP_BY, RelationType.REPLICATES_TO),
    "management": (RelationType.MANAGES, RelationType.SERVES),
    "other": (RelationType.RELATES_TO,),
}


def group_of(rel_type: RelationType) -> str:
    for group, types in RELATION_GROUPS.items():
        if rel_type in types:
            return group
    return "other"
