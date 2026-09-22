"""Раскладка схемы. Чистая функция: одинаковый вход даёт одинаковые координаты."""

from __future__ import annotations

from collections import defaultdict

#: Слои физической схемы: ядро сверху, доступ и серверы ниже.
ROLE_LAYER: dict[str, int] = {
    "ROUTER": 0,
    "L3_SWITCH": 0,
    "FIREWALL": 0,
    "L2_SWITCH": 1,
    "PATCH_PANEL": 2,
    "WALL_OUTLET": 2,
    "ACCESS_POINT": 3,
    "WLC": 3,
    "MODEM": 3,
    "SERVER": 4,
    "STORAGE": 4,
    "KVM": 4,
    "UPS": 5,
    "PDU": 5,
    "PRINTER": 5,
    "OTHER": 5,
}

CI_TYPE_LAYER: dict[str, int] = {
    "SERVICE": 0,
    "APPLICATION": 1,
    "DATABASE": 2,
    "VM": 3,
    "CLUSTER": 3,
    "DEVICE": 4,
}

STEP_X = 280
STEP_Y = 170


def layer_for(ci_type: str | None, device_role: str | None) -> int:
    if device_role and device_role in ROLE_LAYER:
        return ROLE_LAYER[device_role]
    if ci_type and ci_type in CI_TYPE_LAYER:
        return CI_TYPE_LAYER[ci_type]
    return 6


def layered_layout[T](
    items: list[tuple[T, str | None, str | None]],
) -> dict[T, tuple[float, float]]:
    """Иерархия сверху вниз: ключ → (x, y).

    `items` — (идентификатор, тип CI, роль устройства). Порядок внутри слоя
    сохраняется, поэтому повторный вызов не перетасовывает узлы.
    """
    buckets: dict[int, list[T]] = defaultdict(list)
    for item_id, ci_type, role in items:
        buckets[layer_for(ci_type, role)].append(item_id)

    positions: dict[T, tuple[float, float]] = {}
    for layer, ids in sorted(buckets.items()):
        width = (len(ids) - 1) * STEP_X
        for index, item_id in enumerate(ids):
            positions[item_id] = (index * STEP_X - width / 2, layer * STEP_Y)
    return positions
