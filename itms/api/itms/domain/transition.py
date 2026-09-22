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
