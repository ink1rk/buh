"""Правила размещения в стойке. Чистые функции, без базы."""

from __future__ import annotations

import math

from itms.core.errors import Invalid

#: Статусы, из которых установка в стойку переводит объект в работу.
COMMISSION_STATUSES = frozenset({"PLANNED", "ORDERED", "IN_STOCK", "RESERVED"})


def units_for_model(u_height: float | None) -> int:
    """Стойка считается целыми юнитами. Половина юнита модели занимает целый."""
    if u_height is None:
        return 1
    value = float(u_height)
    if value <= 0:
        return 0
    return max(1, math.ceil(value - 1e-9))


def occupies(face: str, other: str) -> bool:
    """FULL делит юниты с обоими фасадами, FRONT — только с FRONT."""
    if face == "FULL" or other == "FULL":
        return True
    return face == other


def spans_overlap(start: int, height: int, other_start: int, other_height: int) -> bool:
    if height <= 0 or other_height <= 0:
        return False
    return start < other_start + other_height and other_start < start + height


def within_rack(position_u: int, u_height: int, rack_u: int) -> bool:
    if u_height <= 0:
        return True
    return position_u >= 1 and position_u + u_height - 1 <= rack_u


def ensure_within_rack(position_u: int, u_height: int, rack_u: int) -> None:
    if within_rack(position_u, u_height, rack_u):
        return
    raise Invalid(
        f"Диапазон U{position_u}–U{position_u + u_height - 1} выходит за стойку {rack_u}U",
        code_hint="out_of_rack",
    )


def free_blocks(
    rack_u: int, spans: list[tuple[int, int]]
) -> list[dict[str, int]]:
    """Непрерывные свободные участки: start — нижний юнит, length — сколько подряд."""
    occupied = [False] * (rack_u + 1)
    for start, height in spans:
        if height <= 0:
            continue
        for unit in range(start, start + height):
            if 1 <= unit <= rack_u:
                occupied[unit] = True
    blocks: list[dict[str, int]] = []
    unit = 1
    while unit <= rack_u:
        if occupied[unit]:
            unit += 1
            continue
        start = unit
        while unit <= rack_u and not occupied[unit]:
            unit += 1
        blocks.append({"start": start, "length": unit - start})
    return blocks


def placement_warnings(
    *,
    weight_kg: float | None,
    max_weight_kg: float | None,
    power_w: int | None,
    max_power_w: int | None,
    depth_mm: int | None,
    rack_depth_mm: int | None,
) -> list[str]:
    """Предупреждения не запрещают размещение: их подтверждают отдельно."""
    warnings: list[str] = []
    if (
        weight_kg is not None
        and max_weight_kg is not None
        and weight_kg > float(max_weight_kg)
    ):
        warnings.append("weight_exceeded")
    if power_w is not None and max_power_w is not None and power_w > max_power_w:
        warnings.append("power_exceeded")
    if depth_mm is not None and rack_depth_mm is not None and depth_mm > rack_depth_mm:
        warnings.append("depth_exceeded")
    return warnings
