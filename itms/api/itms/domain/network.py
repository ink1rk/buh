"""Правила сетевого слоя: порты, кабели, сквозная трассировка линка.

Модуль не знает про базу и HTTP: на вход приходят простые структуры, на выход —
решение и объяснение. Это позволяет покрыть инженерные инварианты unit-тестами.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from itms.core.errors import Invalid
from itms.models.enums import (
    INTERFACE_MEDIA,
    LOGICAL_INTERFACE_TYPES,
    PASSIVE_DEVICE_ROLES,
    CableMedium,
    DeviceRole,
    InterfaceType,
)

_PATTERN_PLACEHOLDER = re.compile(r"\{n(?::0(\d+))?\}")
_MAC_CLEAN = re.compile(r"[^0-9a-f]")


def expand_port_template(
    name_pattern: str, count: int, start_index: int = 1
) -> list[tuple[str, int]]:
    """Разворачивает шаблон `Gi1/0/{n}` в список имён портов и их позиций.

    Поддерживается выравнивание нулями: `Port-{n:03}` даёт `Port-001`.
    """
    if count < 1:
        raise Invalid(
            "Количество портов в шаблоне должно быть положительным", code_hint="bad_template"
        )
    if count > 512:
        raise Invalid("Шаблон не может создавать больше 512 портов", code_hint="template_too_large")
    match = _PATTERN_PLACEHOLDER.search(name_pattern)
    if match is None:
        if count > 1:
            raise Invalid(
                "В шаблоне нескольких портов должен быть заполнитель {n}", code_hint="bad_template"
            )
        return [(name_pattern, start_index)]
    width = int(match.group(1)) if match.group(1) else 0
    result: list[tuple[str, int]] = []
    for offset in range(count):
        index = start_index + offset
        rendered = str(index).rjust(width, "0") if width else str(index)
        result.append((_PATTERN_PLACEHOLDER.sub(rendered, name_pattern, count=1), index))
    return result


def normalize_mac(value: str | None) -> str | None:
    """Приводит MAC к виду `00:1a:2b:3c:4d:5e` независимо от формата ввода."""
    if value is None:
        return None
    raw = _MAC_CLEAN.sub("", value.strip().lower())
    if not raw:
        return None
    if len(raw) != 12:
        raise Invalid(f"MAC-адрес «{value}» некорректен", code_hint="bad_mac")
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


@dataclass(frozen=True, slots=True)
class InterfaceFacts:
    """Минимум об интерфейсе, нужный доменным правилам."""

    id: UUID
    ci_id: UUID
    name: str
    interface_type: InterfaceType
    medium: CableMedium | None = None
    speed_mbps: int | None = None
    device_role: DeviceRole | None = None
    paired_interface_id: UUID | None = None
    occupied: bool = False


@dataclass(slots=True)
class ConnectionCheck:
    """Результат проверки кабеля: запреты — исключением, сомнения — предупреждением."""

    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def validate_connection(
    side_a: InterfaceFacts,
    side_b: InterfaceFacts,
    medium: CableMedium,
    speed_mbps: int | None = None,
    occupies_port: bool = True,
) -> ConnectionCheck:
    """Проверяет кабель между двумя портами.

    Жёсткие запреты: соединение порта с самим собой, логический интерфейс, занятый порт.
    Остальное — предупреждения: инженер может осознанно подключить 10G-порт на 1G.
    """
    check = ConnectionCheck()
    if side_a.id == side_b.id:
        raise Invalid("Кабель не может соединять порт сам с собой", code_hint="self_connection")
    for side in (side_a, side_b):
        if side.interface_type in LOGICAL_INTERFACE_TYPES:
            raise Invalid(
                f"Порт «{side.name}» логический — кабель к нему не подключается",
                code_hint="logical_interface",
            )
        if occupies_port and side.occupied:
            raise Invalid(
                f"Порт «{side.name}» уже занят активным кабелем", code_hint="port_occupied"
            )
        allowed = INTERFACE_MEDIA.get(side.interface_type, frozenset())
        if allowed and medium not in allowed:
            check.warn(
                f"Среда {medium.value} нетипична для разъёма {side.interface_type.value} "
                f"порта «{side.name}»"
            )
    if side_a.interface_type != side_b.interface_type:
        check.warn(
            f"Разные типы разъёмов: {side_a.interface_type.value} и {side_b.interface_type.value}"
        )
    port_speeds = [s for s in (side_a.speed_mbps, side_b.speed_mbps) if s]
    if port_speeds:
        limit = min(port_speeds)
        if speed_mbps and speed_mbps > limit:
            check.warn(
                f"Заявленная скорость линка {speed_mbps} Мбит/с выше возможностей портов "
                f"({limit} Мбит/с)"
            )
        if side_a.speed_mbps and side_b.speed_mbps and side_a.speed_mbps != side_b.speed_mbps:
            check.warn(
                f"Скорости портов различаются: {side_a.speed_mbps} и {side_b.speed_mbps} Мбит/с"
            )
    return check


@dataclass(frozen=True, slots=True)
class LinkSegment:
    connection_id: UUID
    label: str | None
    length_m: float | None
    from_interface_id: UUID
    to_interface_id: UUID


@dataclass(slots=True)
class LinkPath:
    """Сквозной линк: из каких кусков состоит и где он реально заканчивается."""

    segments: list[LinkSegment] = field(default_factory=list)
    passed_through: list[UUID] = field(default_factory=list)
    endpoint_interface_id: UUID | None = None
    total_length_m: float | None = None
    truncated: bool = False

    @property
    def is_direct(self) -> bool:
        return len(self.segments) <= 1


def trace_link(
    start: InterfaceFacts,
    connection_of: Callable[[UUID], LinkSegment | None],
    interface_of: Callable[[UUID], InterfaceFacts | None],
    max_hops: int = 16,
) -> LinkPath:
    """Идёт по кабелям, проходя патч-панели насквозь через парный порт.

    Без этого обхода «кабель от сервера» всегда обрывался бы на первой панели,
    и ответить на вопрос «куда реально приходит порт» было бы нельзя.
    """
    path = LinkPath()
    current = start
    visited: set[UUID] = {start.id}
    length_known = True
    total = 0.0
    for _ in range(max_hops):
        segment = connection_of(current.id)
        if segment is None:
            break
        path.segments.append(segment)
        if segment.length_m is None:
            length_known = False
        else:
            total += float(segment.length_m)
        far_end_id = (
            segment.to_interface_id
            if segment.from_interface_id == current.id
            else segment.from_interface_id
        )
        far_end = interface_of(far_end_id)
        if far_end is None:
            path.endpoint_interface_id = far_end_id
            break
        path.endpoint_interface_id = far_end.id
        passes_through = (
            far_end.device_role in PASSIVE_DEVICE_ROLES and far_end.paired_interface_id is not None
        )
        if not passes_through:
            break
        path.passed_through.append(far_end.ci_id)
        paired = interface_of(far_end.paired_interface_id)  # type: ignore[arg-type]
        if paired is None or paired.id in visited:
            break
        visited.add(paired.id)
        current = paired
    else:
        path.truncated = True
    path.total_length_m = round(total, 2) if length_known and path.segments else None
    return path


def redundancy_violations(
    group: str,
    members: Sequence[tuple[UUID, str | None, str]],
) -> list[str]:
    """Проверяет пару резервных линков: одна трасса или нерабочий статус — это риск."""
    issues: list[str] = []
    if len(members) < 2:
        issues.append(f"В группе резервирования «{group}» только один линк")
    routes = [route for _, route, _ in members if route]
    if len(routes) > 1 and len(set(routes)) == 1:
        issues.append(f"Все линки группы «{group}» идут по одной трассе: {routes[0]}")
    broken = [status for _, _, status in members if status in {"FAULTY", "DECOMMISSIONED"}]
    if broken:
        issues.append(f"В группе «{group}» есть линк в состоянии {broken[0]}")
    return issues


def free_port_summary(
    interfaces: Iterable[InterfaceFacts], patchable: frozenset[InterfaceType]
) -> tuple[int, int]:
    """Возвращает пару «всего физических портов, из них свободных»."""
    total = 0
    free = 0
    for interface in interfaces:
        if interface.interface_type not in patchable:
            continue
        total += 1
        if not interface.occupied:
            free += 1
    return total, free
