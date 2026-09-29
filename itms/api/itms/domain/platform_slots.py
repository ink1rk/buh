"""Имена мест на плате: процессоры и модули памяти.

Порядок памяти — рекомендуемое заполнение: сначала первый ранг каждого канала.
"""

from __future__ import annotations


def cpu_names(count: int | None) -> list[str]:
    return [f"CPU{index}" for index in range(1, (count or 0) + 1)]


def ram_names(count: int | None, sockets: int | None) -> list[str]:
    total = count or 0
    if total <= 0:
        return []
    groups = max(sockets or 1, 1)
    base, extra = divmod(total, groups)
    names: list[str] = []
    for cpu in range(groups):
        size = base + (1 if cpu < extra else 0)
        half = (size + 1) // 2
        for index in range(size):
            side = "A" if index < half else "B"
            rank = (index if index < half else index - half) + 1
            names.append(f"{side}{rank}/CPU{cpu + 1}")
    return names
