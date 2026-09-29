"""Срез состояния и разрыв между текущим вводом и целевой нагрузкой.

Снимок неизменяем: это цельная картина на дату, а не журнал правок.
Разрыв считается по числам прогноза и по пределу, который закладывает план.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GapFinding:
    rule: str
    level: str
    message: str


def _kw(watts: int) -> str:
    return f"{watts / 1000:.2f}".replace(".", ",") + " кВт"


TARGET_PLAN_NAME = "Целевая схема: ввод 3×50 А, UPS и стойка R2"


def architecture_items(
    *,
    location_id: str | None,
    source_code: str,
    source_is_panel: bool,
    side_b_code: str | None,
) -> list[dict[str, Any]]:
    """Стойка, UPS и PDU, которых ещё нет в модели. Нагрузка сценария остаётся прогнозом."""
    place = location_id is not None
    source_title = "Щит" if source_is_panel else "Ввод"
    side_b = side_b_code or source_code
    side_b_title = "Ввод B" if side_b_code else source_title
    rack: dict[str, Any] = {
        "name": "Стойка R2",
        "code": "R2",
        "u_height": 42,
        "depth_mm": 1000,
        "max_weight_kg": 800,
        "max_power_w": 8000,
    }
    if location_id is not None:
        rack["location_id"] = location_id
    if place:
        rack["plan_x"] = 1200
        rack["plan_y"] = 2800
    ups = _node(
        "UPS целевой",
        "UPS-2",
        "UPS",
        location_id,
        efficiency=0.94,
        ups_capacity_w=10000,
        voltage_v=400,
        feed_side="A",
    )
    pdu_a = _node(
        "PDU стойки R2, сторона A",
        "PDU-R2-A",
        "PDU",
        location_id,
        rack_ref="R2",
        feed_side="A",
        phase_label="L1L2L3",
    )
    pdu_b = _node(
        "PDU стойки R2, сторона B",
        "PDU-R2-B",
        "PDU",
        location_id,
        rack_ref="R2",
        feed_side="B",
        phase_label="L1L2L3",
    )
    return [
        {
            "operation": "CREATE",
            "entity_type": "rack",
            "ref": "R2",
            "summary": "Новая стойка R2, 42U",
            "create": rack,
        },
        {
            "operation": "CREATE",
            "entity_type": "power_node",
            "ref": "UPS-2",
            "summary": "Новый UPS 10 кВт, КПД 0,94",
            "create": ups,
        },
        {
            "operation": "CREATE",
            "entity_type": "power_node",
            "ref": "PDU-R2-A",
            "summary": "PDU стойки R2, сторона A",
            "create": pdu_a,
        },
        {
            "operation": "CREATE",
            "entity_type": "power_node",
            "ref": "PDU-R2-B",
            "summary": "PDU стойки R2, сторона B",
            "create": pdu_b,
        },
        {
            "operation": "CONNECT",
            "entity_type": "power_link",
            "ref": "link-ups",
            "summary": f"{source_title} {source_code} питает новый UPS",
            "connect": {"source_code": source_code, "target_ref": "UPS-2"},
        },
        {
            "operation": "CONNECT",
            "entity_type": "power_link",
            "ref": "link-pdu-a",
            "summary": "Новый UPS питает PDU стороны A",
            "connect": {"source_ref": "UPS-2", "target_ref": "PDU-R2-A"},
        },
        {
            "operation": "CONNECT",
            "entity_type": "power_link",
            "ref": "link-pdu-b",
            "summary": f"{side_b_title} {side_b} питает PDU стороны B",
            "connect": {
                "source_code": side_b,
                "target_ref": "PDU-R2-B",
            },
        },
    ]


def _node(
    name: str, code: str, node_type: str, location_id: str | None, **extra: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "code": code,
        "node_type": node_type,
        "phases": 3,
        **extra,
    }
    if location_id is not None:
        payload["location_id"] = location_id
    return payload


def checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def power_gap(
    *,
    current_limit_w: int,
    target_estimated_w: int,
    required_input_w: int,
    planned_limit_w: int | None,
    applied: bool,
) -> list[GapFinding]:
    """Цель сравнивается с пределом плана, если план есть, иначе с текущим вводом."""
    ceiling = planned_limit_w if planned_limit_w is not None else current_limit_w
    findings: list[GapFinding] = []
    if target_estimated_w > ceiling:
        findings.append(
            GapFinding(
                rule="power_target",
                level="BLOCKER",
                message=(
                    f"Расчётная цель {_kw(target_estimated_w)} выше предела ввода {_kw(ceiling)}"
                ),
            )
        )
    else:
        findings.append(
            GapFinding(
                rule="power_target",
                level="OK",
                message=(
                    f"Предел ввода {_kw(ceiling)} вмещает расчётную цель {_kw(target_estimated_w)}"
                ),
            )
        )
    if required_input_w > ceiling:
        findings.append(
            GapFinding(
                rule="power_reserve",
                level="WARNING",
                message=(f"Для запаса 20% нужно {_kw(required_input_w)}, предел {_kw(ceiling)}"),
            )
        )
    else:
        findings.append(
            GapFinding(
                rule="power_reserve",
                level="OK",
                message=(f"Запас 20% закрыт: нужно {_kw(required_input_w)}, предел {_kw(ceiling)}"),
            )
        )
    if planned_limit_w is not None and not applied and target_estimated_w > current_limit_w:
        findings.append(
            GapFinding(
                rule="power_unapplied",
                level="WARNING",
                message=(
                    f"Текущий ввод {_kw(current_limit_w)} не вмещает прогноз "
                    f"{_kw(target_estimated_w)}, план ещё не применён"
                ),
            )
        )
    return findings
