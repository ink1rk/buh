"""Расчёт питания: чистая функция над графом, без базы и HTTP.

Четыре величины не смешиваются. Номинал и расчётная живут рядом с фактической:
свежий замер подменяет значение в проверке пределов, но паспорт и расчёт
в ответе остаются отдельно. Потери UPS и блоков питания — это P_in = P_out / КПД.
Подзаряд батарей в расчётную не входит: он показывается отдельно.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from itms.core.errors import CycleDetected, Invalid

DEFAULT_POWER_FACTOR = 0.95
DEFAULT_DERATING = 0.8
DEFAULT_UTILIZATION = 0.80
DISBALANCE_LIMIT_PCT = 15.0
MEASUREMENT_TTL_DAYS = 180
MEASUREMENT_GAP = 0.25
CHARGE_FRACTION = 0.10
SQRT3 = math.sqrt(3)

NETWORK_ROLES = frozenset(
    {"ROUTER", "L3_SWITCH", "L2_SWITCH", "FIREWALL", "ACCESS_POINT", "WLC", "MODEM"}
)
LEAF_TYPES = frozenset({"PSU", "GENERIC_LOAD"})
CURRENT_LIMIT_TYPES = frozenset({"BREAKER", "LINE", "PDU"})

FAILOVER_TEXT = {
    "RESILIENT": "Оставшаяся ветка выдерживает полную нагрузку",
    "AT_RISK": "При отказе одной ветки оставшаяся перегружается",
    "SINGLE_FEED": "Питание только от одной ветки",
    "SAME_FEED": "Несколько блоков питания сидят на одной ветке",
    "UNKNOWN": "Цепочка питания не доведена до ввода",
}


@dataclass(frozen=True)
class LoadNode:
    id: str
    name: str
    node_type: str
    phases: int = 1
    phase_label: str | None = None
    voltage_v: float | None = None
    rated_current_a: float | None = None
    derating_factor: float = DEFAULT_DERATING
    power_factor: float | None = None
    efficiency: float | None = None
    nameplate_w: float | None = None
    peak_w: float | None = None
    max_load_w: float | None = None
    ups_capacity_va: float | None = None
    ups_capacity_w: float | None = None
    feed_id: str | None = None
    feed_side: str = "SINGLE"
    parent_device_id: str | None = None
    utilization: float | None = None
    device_role: str | None = None
    measured_w: float | None = None
    measurement_fresh: bool = False
    measurement_stale: bool = False
    charge_w: float | None = None


@dataclass(frozen=True)
class LoadLink:
    source_id: str
    target_id: str


@dataclass(frozen=True)
class Addition:
    name: str
    nameplate_w: int
    quantity: int = 1
    utilization: float = DEFAULT_UTILIZATION
    behind_new_ups: bool = True


@dataclass
class NodeResult:
    node_id: str
    name: str
    node_type: str
    nameplate_w: int
    peak_w: int
    estimated_w: int
    used_w: int
    inlet_w: int
    limit_w: int | None
    headroom_w: int | None
    current_a: float | None
    phases_w: dict[str, int]
    disbalance_pct: float | None
    value_source: str
    measured_coverage_pct: float
    warnings: list[dict[str, str]] = field(default_factory=list)
    trace: list[dict[str, object]] = field(default_factory=list)
    estimated_with_charge_w: int = 0
    failover: str | None = None
    failover_detail: str | None = None


@dataclass
class PowerReport:
    nodes: dict[str, NodeResult]
    device_failover: dict[str, str]
    #: Вход узла после переноса нагрузки при потере ветки: ветка → узел → ватты.
    loss_inlet: dict[str, dict[str, int]]


@dataclass
class _Calc:
    nameplate: float = 0
    peak: float = 0
    estimated: float = 0
    used: float = 0
    inlet_nameplate: float = 0
    inlet_estimated: float = 0
    inlet_used: float = 0
    measured_inlet: float = 0
    phases: dict[str, float] = field(default_factory=lambda: {"L1": 0.0, "L2": 0.0, "L3": 0.0})
    value_source: str = "ESTIMATE"
    trace: list[dict[str, object]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)


def utilization_for(node: LoadNode) -> float:
    if node.utilization is not None:
        return node.utilization
    role = node.device_role
    if role == "SERVER":
        return 0.70
    if role == "STORAGE":
        return 0.75
    if role in NETWORK_ROLES:
        return 0.85
    return DEFAULT_UTILIZATION


def current_amps(power_w: float, *, voltage_v: float, phases: int, power_factor: float) -> float:
    if power_w <= 0 or voltage_v <= 0 or power_factor <= 0:
        return 0.0
    if phases == 3:
        return power_w / (SQRT3 * voltage_v * power_factor)
    return power_w / (voltage_v * power_factor)


def phase_disbalance_pct(l1: float, l2: float, l3: float) -> float | None:
    average = (l1 + l2 + l3) / 3
    if average <= 0:
        return None
    return (max(l1, l2, l3) - min(l1, l2, l3)) / average * 100


def recommended_breaker_w(
    current_a: float, *, voltage_v: float = 400, power_factor: float = DEFAULT_POWER_FACTOR
) -> float:
    """Мощность трёхфазного ввода: √3 × U × I × cos φ."""
    return SQRT3 * voltage_v * current_a * power_factor


def breaker_limit_w(
    *,
    rated_current_a: float,
    derating: float,
    voltage_v: float,
    phases: int,
    power_factor: float,
) -> float:
    allowed = rated_current_a * derating
    factor = SQRT3 if phases == 3 else 1.0
    return allowed * voltage_v * power_factor * factor


def _watts(value: float) -> int:
    return round(value)


def _apply_efficiency(value: float, efficiency: float | None) -> float:
    if efficiency is not None and 0 < efficiency < 1:
        return value / efficiency
    return value


def _split_phases(power: float, *, phases: int, phase_label: str | None) -> dict[str, float]:
    blank = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
    if power == 0:
        return blank
    if phases == 3 or phase_label == "L1L2L3":
        part = power / 3
        return {"L1": part, "L2": part, "L3": part}
    if phase_label in blank:
        blank[phase_label] = power
    return blank


def _voltage(node: LoadNode) -> float:
    if node.voltage_v:
        return node.voltage_v
    return 400.0 if node.phases == 3 else 230.0


def _power_factor(node: LoadNode) -> float:
    return node.power_factor if node.power_factor else DEFAULT_POWER_FACTOR


def power_limit_w(node: LoadNode) -> float | None:
    """Предел, с которым сравнивается нагрузка узла.

    Ввод ограничен мощностью. Автомат, линия и PDU — током с коэффициентом.
    UPS — меньшей из ваттной ёмкости и 0,9×ВА.
    """
    limits: list[float] = []
    if node.node_type == "INPUT":
        return float(node.max_load_w) if node.max_load_w else None
    if node.max_load_w:
        limits.append(float(node.max_load_w))
    if node.node_type == "UPS":
        if node.ups_capacity_w:
            limits.append(float(node.ups_capacity_w))
        if node.ups_capacity_va:
            limits.append(float(node.ups_capacity_va) * 0.9)
    if node.node_type in CURRENT_LIMIT_TYPES and node.rated_current_a:
        limits.append(
            breaker_limit_w(
                rated_current_a=node.rated_current_a,
                derating=node.derating_factor or DEFAULT_DERATING,
                voltage_v=_voltage(node),
                phases=node.phases,
                power_factor=_power_factor(node),
            )
        )
    if not limits:
        return None
    return min(limits)


def _checked_power(node: LoadNode, outlet: float, inlet: float) -> float:
    # Номинал UPS — это мощность на выходе. Ввод и автомат видят вход с потерями.
    if node.node_type == "UPS":
        return outlet
    return inlet


def ensure_power_acyclic(edges: dict[str, list[str]], source_id: str, target_id: str) -> None:
    """Новое ребро «питающий → потребитель» не должно замкнуть цепочку."""
    if source_id == target_id:
        raise Invalid("Узел питания не может питать сам себя", code_hint="self_link")
    seen: set[str] = set()
    stack = [target_id]
    while stack:
        node = stack.pop()
        if node == source_id:
            raise CycleDetected(
                "Связь замыкает цикл в графе питания",
                source_id=source_id,
                target_id=target_id,
            )
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))


def forecast(
    *,
    current_estimated_w: float,
    current_nameplate_w: float,
    input_limit_w: float,
    additions: list[Addition],
    ups_efficiency: float | None = None,
    charge_w: float = 0,
    reserve: float = 0.20,
) -> dict[str, int | float]:
    """Прирост нагрузки. Новый UPS добавляет потери только к тому, что за ним."""
    added_nameplate = sum(item.nameplate_w * item.quantity for item in additions)
    behind = sum(
        item.nameplate_w * item.quantity * item.utilization
        for item in additions
        if item.behind_new_ups
    )
    direct = sum(
        item.nameplate_w * item.quantity * item.utilization
        for item in additions
        if not item.behind_new_ups
    )
    added_estimated = behind + direct
    if ups_efficiency is not None and 0 < ups_efficiency < 1 and behind:
        inlet = behind / ups_efficiency
        loss = _watts(inlet) - _watts(behind)
        growth = _watts(inlet) + _watts(direct)
    else:
        loss = 0
        growth = _watts(added_estimated)
    target = _watts(current_estimated_w) + growth
    headroom = _watts(input_limit_w) - target
    required = target / (1 - reserve) if reserve < 1 else float(target)
    charged = target + _watts(charge_w)
    return {
        "current_estimated_w": _watts(current_estimated_w),
        "current_nameplate_w": _watts(current_nameplate_w),
        "current_headroom_w": _watts(input_limit_w) - _watts(current_estimated_w),
        "added_nameplate_w": _watts(added_nameplate),
        "added_estimated_w": _watts(added_estimated),
        "ups_loss_w": loss,
        "inlet_added_w": growth,
        "target_estimated_w": target,
        "headroom_w": headroom,
        "deficit_w": max(0, -headroom),
        "charge_w": _watts(charge_w),
        "estimated_with_charge_w": charged,
        "required_input_w": _watts(required),
        "recommended_3x50_w": _watts(recommended_breaker_w(50)),
    }


def _children_map(
    nodes: dict[str, LoadNode], links: list[LoadLink]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    children: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    parents: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for link in links:
        if link.source_id not in nodes or link.target_id not in nodes:
            raise Invalid("Связь питания ссылается на неизвестный узел", code_hint="missing_node")
        children[link.source_id].append(link.target_id)
        parents[link.target_id].append(link.source_id)
    return children, parents


def _topological(children: dict[str, list[str]], parents: dict[str, list[str]]) -> list[str]:
    pending = {node_id: len(kids) for node_id, kids in children.items()}
    queue = [node_id for node_id, count in pending.items() if count == 0]
    order: list[str] = []
    while queue:
        node_id = queue.pop()
        order.append(node_id)
        for parent_id in parents[node_id]:
            pending[parent_id] -= 1
            if pending[parent_id] == 0:
                queue.append(parent_id)
    if len(order) != len(children):
        raise CycleDetected("Граф питания содержит цикл")
    return order


def _shares(nodes: dict[str, LoadNode], children: dict[str, list[str]]) -> dict[str, float]:
    """Несколько БП одного устройства делят один паспорт, а не умножают его."""
    groups: dict[str, list[LoadNode]] = {}
    for node in nodes.values():
        if node.node_type != "PSU" or not node.parent_device_id or children[node.id]:
            continue
        groups.setdefault(node.parent_device_id, []).append(node)
    shares: dict[str, float] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        fraction = 1 / len(group)
        for node in group:
            shares[node.id] = fraction
    return shares


def _leaf(node: LoadNode, fraction: float, step: int) -> _Calc:
    factor = utilization_for(node)
    nameplate = (node.nameplate_w or 0) * fraction
    peak_basis = node.peak_w if node.peak_w is not None else (node.nameplate_w or 0)
    estimated = nameplate * factor
    used = estimated
    source = "ESTIMATE"
    warnings: list[dict[str, str]] = []
    if node.measurement_fresh and node.measured_w is not None:
        used = node.measured_w
        source = "MEASUREMENT"
        if estimated > 0 and abs(node.measured_w - estimated) / estimated > MEASUREMENT_GAP:
            warnings.append(
                {
                    "code": "measurement_gap",
                    "message": (
                        f"{node.name}: замер {_watts(node.measured_w)} Вт отличается от расчёта "
                        f"{_watts(estimated)} Вт больше чем на 25%"
                    ),
                }
            )
    if node.measurement_stale:
        warnings.append(
            {
                "code": "stale_measurement",
                "message": f"{node.name}: замер старше срока годности и в расчёт не взят",
            }
        )
    formula = f"{_watts(node.nameplate_w or 0)} × {factor:.2f}"
    if fraction != 1:
        formula = f"({formula}) / {round(1 / fraction)}"
    trace = [
        {
            "step": step,
            "source": node.name,
            "value_source": source,
            "nameplate_w": _watts(nameplate),
            "factor": factor,
            "value_w": _watts(estimated),
            "used_w": _watts(used),
            "formula": formula,
        }
    ]
    return _Calc(
        nameplate=nameplate,
        peak=peak_basis * fraction,
        estimated=estimated,
        used=used,
        value_source=source,
        trace=trace,
        warnings=warnings,
        measured_inlet=used if source == "MEASUREMENT" else 0,
    )


def _aggregate(node: LoadNode, kids: list[_Calc], step: int) -> _Calc:
    calc = _Calc(
        nameplate=sum(kid.inlet_nameplate for kid in kids),
        peak=sum(kid.peak for kid in kids),
        estimated=sum(kid.inlet_estimated for kid in kids),
        used=sum(kid.inlet_used for kid in kids),
        measured_inlet=sum(kid.measured_inlet for kid in kids),
        warnings=[warning for kid in kids for warning in kid.warnings],
        trace=[step_row for kid in kids for step_row in kid.trace],
    )
    sources = {kid.value_source for kid in kids}
    if len(sources) == 1:
        calc.value_source = sources.pop()
    elif sources:
        calc.value_source = "MIXED"
    calc.trace.append(
        {
            "step": step,
            "source": f"Сумма потребителей {node.name}",
            "value_w": _watts(calc.estimated),
            "formula": "Σ потребителей",
        }
    )
    if node.measurement_fresh and node.measured_w is not None:
        calc.used = node.measured_w
        calc.measured_inlet = node.measured_w
        calc.value_source = "MIXED" if calc.estimated else "MEASUREMENT"
        calc.trace.append(
            {
                "step": step + 1,
                "source": node.name,
                "value_source": "MEASUREMENT",
                "value_w": _watts(node.measured_w),
                "formula": "свежий замер",
            }
        )
    if node.measurement_stale:
        calc.warnings.append(
            {
                "code": "stale_measurement",
                "message": f"{node.name}: замер старше срока годности и в расчёт не взят",
            }
        )
    return calc


def _finish_node(node: LoadNode, calc: _Calc, child_phases: dict[str, float] | None) -> _Calc:
    outlet_estimated = calc.estimated
    calc.inlet_nameplate = calc.nameplate
    calc.inlet_estimated = _apply_efficiency(outlet_estimated, node.efficiency)
    calc.inlet_used = _apply_efficiency(calc.used, node.efficiency)
    if node.efficiency is not None and 0 < node.efficiency < 1 and outlet_estimated:
        calc.trace.append(
            {
                "step": len(calc.trace) + 1,
                "source": f"Потери {node.name}",
                "efficiency": node.efficiency,
                "value_w": _watts(calc.inlet_estimated),
                "formula": f"{_watts(outlet_estimated)} / {node.efficiency:.2f}",
            }
        )
    # Лист делит свой вход по фазе. У родителя фазы — сумма входов детей,
    # а собственные потери добавляются по фазам самого узла.
    loss = calc.inlet_estimated - outlet_estimated
    if child_phases is None:
        phases = _split_phases(
            calc.inlet_estimated, phases=node.phases, phase_label=node.phase_label
        )
    else:
        phases = dict(child_phases)
        if loss:
            extra = _split_phases(loss, phases=node.phases, phase_label=node.phase_label)
            phases = {key: phases[key] + extra[key] for key in phases}
    if (
        node.phases == 1
        and node.node_type not in {"INPUT", "PANEL"}
        and node.phase_label not in {"L1", "L2", "L3"}
    ):
        calc.warnings.append(
            {
                "code": "missing_phase",
                "message": f"{node.name}: у однофазного потребителя не указана фаза",
            }
        )
        phases = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
    calc.phases = phases
    calc.measured_inlet = _apply_efficiency(calc.measured_inlet, node.efficiency)
    return calc


def _charge_w(node: LoadNode) -> float:
    if node.charge_w is not None:
        return node.charge_w
    if node.node_type == "UPS" and node.ups_capacity_w:
        return 0.0
    return 0.0


def _warnings_for_limits(node: LoadNode, calc: _Calc, limit: float | None) -> None:
    checked = _checked_power(node, calc.estimated, calc.inlet_estimated)
    used = _checked_power(node, calc.used, calc.inlet_used)
    if limit is not None and checked > limit:
        calc.warnings.append(
            {
                "code": "over_limit",
                "message": (
                    f"{node.name}: расчётная {_watts(checked)} Вт выше предела {_watts(limit)} Вт"
                ),
            }
        )
    if limit is not None and used > limit and abs(used - checked) > 1:
        calc.warnings.append(
            {
                "code": "measured_over_limit",
                "message": (
                    f"{node.name}: замер {_watts(used)} Вт выше предела {_watts(limit)} Вт"
                ),
            }
        )
    if node.phases == 3:
        balance = phase_disbalance_pct(calc.phases["L1"], calc.phases["L2"], calc.phases["L3"])
        if balance is not None and balance > DISBALANCE_LIMIT_PCT:
            calc.warnings.append(
                {
                    "code": "phase_disbalance",
                    "message": (
                        f"{node.name}: дисбаланс фаз {balance:.1f}% при норме "
                        f"{DISBALANCE_LIMIT_PCT:.0f}%"
                    ),
                }
            )
    if node.node_type in CURRENT_LIMIT_TYPES and node.rated_current_a:
        allowed = node.rated_current_a * (node.derating_factor or DEFAULT_DERATING)
        amps = current_amps(
            calc.inlet_estimated,
            voltage_v=_voltage(node),
            phases=node.phases,
            power_factor=_power_factor(node),
        )
        if amps > allowed:
            calc.warnings.append(
                {
                    "code": "current_over_limit",
                    "message": (
                        f"{node.name}: ток {amps:.1f} А выше {allowed:.1f} А с учётом коэффициента"
                    ),
                }
            )


def _feed_of(node_id: str, nodes: dict[str, LoadNode], parents: dict[str, list[str]]) -> str | None:
    if nodes[node_id].feed_id:
        return nodes[node_id].feed_id
    seen: set[str] = set()
    stack = list(parents.get(node_id, ()))
    while stack:
        parent_id = stack.pop()
        if parent_id in seen:
            continue
        seen.add(parent_id)
        if nodes[parent_id].feed_id:
            return nodes[parent_id].feed_id
        stack.extend(parents.get(parent_id, ()))
    return None


def _ancestors(node_id: str, parents: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    stack = list(parents.get(node_id, ()))
    ordered: list[str] = []
    while stack:
        parent_id = stack.pop()
        if parent_id in seen:
            continue
        seen.add(parent_id)
        ordered.append(parent_id)
        stack.extend(parents.get(parent_id, ()))
    return ordered


def _consumers(nodes: dict[str, LoadNode]) -> dict[str, list[LoadNode]]:
    grouped: dict[str, list[LoadNode]] = {}
    for node in nodes.values():
        if node.node_type == "PSU" and node.parent_device_id:
            grouped.setdefault(node.parent_device_id, []).append(node)
        elif node.node_type in LEAF_TYPES:
            grouped.setdefault(node.id, []).append(node)
    return grouped


def _propagate(
    start_id: str,
    extra_out: float,
    extras: dict[str, float],
    nodes: dict[str, LoadNode],
    parents: dict[str, list[str]],
) -> None:
    stack = [(start_id, extra_out)]
    seen: set[str] = set()
    while stack:
        node_id, extra = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = nodes[node_id]
        extra_in = _apply_efficiency(extra, node.efficiency)
        extras[node_id] = extras.get(node_id, 0) + extra_in
        for parent_id in parents.get(node_id, ()):
            stack.append((parent_id, extra_in))


def _failover(
    nodes: dict[str, LoadNode],
    parents: dict[str, list[str]],
    calcs: dict[str, _Calc],
) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    consumers = _consumers(nodes)
    feeds = {node.feed_id for node in nodes.values() if node.feed_id}
    for node in nodes.values():
        found = _feed_of(node.id, nodes, parents)
        if found:
            feeds.add(found)
    loss_inlet: dict[str, dict[str, int]] = {}
    per_feed: dict[str, dict[str, str]] = {}
    for feed_id in feeds:
        extras: dict[str, float] = {}
        verdicts: dict[str, str] = {}
        for key, members in consumers.items():
            member_feeds = {_feed_of(member.id, nodes, parents) for member in members}
            if None in member_feeds:
                verdicts[key] = "UNKNOWN"
                continue
            if len(member_feeds) == 1:
                verdicts[key] = "SAME_FEED" if len(members) > 1 else "SINGLE_FEED"
                continue
            lost = [member for member in members if _feed_of(member.id, nodes, parents) == feed_id]
            surviving = [
                member for member in members if _feed_of(member.id, nodes, parents) != feed_id
            ]
            if not lost or not surviving:
                verdicts[key] = "RESILIENT"
                continue
            portion = sum(calcs[member.id].inlet_estimated for member in lost) / len(surviving)
            for member in surviving:
                _propagate(member.id, portion, extras, nodes, parents)
            verdicts[key] = "PENDING"
        for key, members in consumers.items():
            if verdicts.get(key) != "PENDING":
                continue
            surviving = [
                member for member in members if _feed_of(member.id, nodes, parents) != feed_id
            ]
            overloaded = False
            for member in surviving:
                for node_id in [member.id, *_ancestors(member.id, parents)]:
                    limit = power_limit_w(nodes[node_id])
                    if limit is None:
                        continue
                    load = calcs[node_id].inlet_estimated + extras.get(node_id, 0)
                    if nodes[node_id].node_type == "UPS":
                        load = calcs[node_id].estimated + extras.get(node_id, 0)
                    if load > limit + 1e-6:
                        overloaded = True
            verdicts[key] = "AT_RISK" if overloaded else "RESILIENT"
        per_feed[feed_id] = verdicts
        loss_inlet[feed_id] = {
            node_id: _watts(calcs[node_id].inlet_estimated + extras.get(node_id, 0))
            for node_id in nodes
        }
    overall: dict[str, str] = {}
    for key, members in consumers.items():
        member_feeds = {_feed_of(member.id, nodes, parents) for member in members}
        if None in member_feeds or not member_feeds:
            overall[key] = "UNKNOWN"
            continue
        if len(member_feeds) == 1:
            overall[key] = "SAME_FEED" if len(members) > 1 else "SINGLE_FEED"
            continue
        if any(per_feed.get(feed_id, {}).get(key) == "AT_RISK" for feed_id in member_feeds):
            overall[key] = "AT_RISK"
        else:
            overall[key] = "RESILIENT"
    return overall, loss_inlet


def _result(node: LoadNode, calc: _Calc, failover: str | None) -> NodeResult:
    limit = power_limit_w(node)
    checked = _checked_power(node, calc.estimated, calc.inlet_estimated)
    headroom = _watts(limit - checked) if limit is not None else None
    amps = current_amps(
        calc.inlet_estimated,
        voltage_v=_voltage(node),
        phases=node.phases,
        power_factor=_power_factor(node),
    )
    balance = None
    if node.phases == 3:
        balance = phase_disbalance_pct(calc.phases["L1"], calc.phases["L2"], calc.phases["L3"])
    coverage = 0.0
    if calc.inlet_used > 0:
        coverage = min(100.0, calc.measured_inlet / calc.inlet_used * 100)
    charge = _charge_w(node)
    return NodeResult(
        node_id=node.id,
        name=node.name,
        node_type=node.node_type,
        nameplate_w=_watts(calc.nameplate),
        peak_w=_watts(calc.peak),
        estimated_w=_watts(calc.estimated),
        used_w=_watts(calc.used),
        inlet_w=_watts(calc.inlet_estimated),
        limit_w=_watts(limit) if limit is not None else None,
        headroom_w=headroom,
        current_a=round(amps, 2) if amps else None,
        phases_w={key: _watts(value) for key, value in calc.phases.items()},
        disbalance_pct=round(balance, 2) if balance is not None else None,
        value_source=calc.value_source,
        measured_coverage_pct=round(coverage, 2),
        warnings=calc.warnings,
        trace=calc.trace,
        estimated_with_charge_w=_watts(calc.inlet_estimated + charge),
        failover=failover,
        failover_detail=FAILOVER_TEXT.get(failover) if failover else None,
    )


def calculate(nodes: list[LoadNode], links: list[LoadLink]) -> PowerReport:
    by_id = {node.id: node for node in nodes}
    if len(by_id) != len(nodes):
        raise Invalid("Повторяется идентификатор узла питания", code_hint="duplicate_node")
    children, parents = _children_map(by_id, links)
    order = _topological(children, parents)
    shares = _shares(by_id, children)
    calcs: dict[str, _Calc] = {}
    for node_id in order:
        node = by_id[node_id]
        kid_ids = children[node_id]
        if kid_ids:
            calc = _aggregate(node, [calcs[kid] for kid in kid_ids], len(calcs) + 1)
            summed = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
            for kid in kid_ids:
                for phase, value in calcs[kid].phases.items():
                    summed[phase] += value
            child_phases: dict[str, float] | None = summed
        else:
            calc = _leaf(node, shares.get(node_id, 1.0), len(calcs) + 1)
            child_phases = None
        calcs[node_id] = _finish_node(node, calc, child_phases)
        _warnings_for_limits(node, calcs[node_id], power_limit_w(node))
    device_failover, loss_inlet = _failover(by_id, parents, calcs)
    results: dict[str, NodeResult] = {}
    for node in nodes:
        if node.node_type == "PSU" and node.parent_device_id:
            key = node.parent_device_id
        else:
            key = node.id
        verdict = device_failover.get(key) if node.node_type in LEAF_TYPES else None
        results[node.id] = _result(node, calcs[node.id], verdict)
    return PowerReport(nodes=results, device_failover=device_failover, loss_inlet=loss_inlet)
