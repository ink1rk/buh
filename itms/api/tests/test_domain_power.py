"""Методика питания: учебный прогноз, ток, фазы, цикл и отказ ветки."""

from __future__ import annotations

import math

import pytest

from itms.core.errors import CycleDetected
from itms.domain.power import (
    Addition,
    LoadLink,
    LoadNode,
    breaker_limit_w,
    calculate,
    current_amps,
    ensure_power_acyclic,
    forecast,
    phase_disbalance_pct,
    recommended_breaker_w,
)

pytestmark = pytest.mark.anyio


def _node(node_id: str, **kwargs: object) -> LoadNode:
    name = str(kwargs.pop("name", node_id))
    node_type = str(kwargs.pop("node_type", "GENERIC_LOAD"))
    return LoadNode(id=node_id, name=name, node_type=node_type, **kwargs)  # type: ignore[arg-type]


def test_textbook_forecast_shows_half_kilowatt_deficit() -> None:
    additions = [
        Addition("Сервер R650", 1200, 2, 0.70),
        Addition("СХД ME5024", 1600, 1, 0.75),
        Addition("Коммутатор", 350, 2, 0.85),
    ]
    result = forecast(
        current_estimated_w=16800,
        current_nameplate_w=24000,
        input_limit_w=20000,
        additions=additions,
        ups_efficiency=0.94,
        charge_w=900,
        reserve=0.20,
    )
    assert result["current_headroom_w"] == 3200
    assert result["added_nameplate_w"] == 4700
    assert result["added_estimated_w"] == 3475
    assert result["ups_loss_w"] == 222
    assert result["inlet_added_w"] == 3697
    assert result["target_estimated_w"] == 20497
    assert result["headroom_w"] == -497
    assert result["deficit_w"] == 497
    assert result["estimated_with_charge_w"] == 21397
    assert result["required_input_w"] == 25621
    assert result["recommended_3x50_w"] == 32909
    assert round(result["target_estimated_w"] / 1000, 2) == 20.50
    assert round(result["estimated_with_charge_w"] / 1000, 2) == 21.40
    assert round(result["required_input_w"] / 1000, 1) == 25.6


def test_current_and_phase_disbalance_follow_the_formula() -> None:
    assert current_amps(5000, voltage_v=230, phases=1, power_factor=0.95) == pytest.approx(
        5000 / (230 * 0.95)
    )
    assert current_amps(16800, voltage_v=400, phases=3, power_factor=0.95) == pytest.approx(
        16800 / (math.sqrt(3) * 400 * 0.95)
    )
    assert recommended_breaker_w(50) == pytest.approx(math.sqrt(3) * 400 * 50 * 0.95)
    assert round(recommended_breaker_w(50)) == 32909
    # 7.2 / 6.8 / 6.5 кВт — это формула, а не округлённые 10.8% из повествования.
    assert round(phase_disbalance_pct(7200, 6800, 6500) or 0, 2) == 10.24
    assert breaker_limit_w(
        rated_current_a=32, derating=0.8, voltage_v=400, phases=3, power_factor=0.95
    ) == pytest.approx(32 * 0.8 * math.sqrt(3) * 400 * 0.95)


def test_ups_loss_and_shared_psu_nameplate() -> None:
    report = calculate(
        [
            _node("in", name="Ввод", node_type="INPUT", phases=3, max_load_w=20000, voltage_v=400),
            _node("ups", name="UPS", node_type="UPS", phases=3, efficiency=0.94),
            _node(
                "load",
                name="Нагрузка",
                phases=3,
                phase_label="L1L2L3",
                nameplate_w=1000,
                utilization=1,
            ),
        ],
        [LoadLink("in", "ups"), LoadLink("ups", "load")],
    )
    assert report.nodes["load"].estimated_w == 1000
    assert report.nodes["ups"].estimated_w == 1000
    assert report.nodes["ups"].inlet_w == 1064
    assert report.nodes["in"].inlet_w == 1064
    assert report.nodes["in"].headroom_w == 20000 - 1064

    split = calculate(
        [
            _node("pdu", name="PDU", node_type="PDU", phases=3, phase_label="L1L2L3"),
            _node(
                "a",
                name="PSU-A",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=750,
                parent_device_id="srv",
                device_role="SERVER",
            ),
            _node(
                "b",
                name="PSU-B",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=750,
                parent_device_id="srv",
                device_role="SERVER",
            ),
        ],
        [LoadLink("pdu", "a"), LoadLink("pdu", "b")],
    )
    assert split.nodes["a"].estimated_w == 262 or split.nodes["a"].estimated_w == 263
    assert split.nodes["pdu"].estimated_w == 525


def test_fresh_measurement_replaces_used_value_only() -> None:
    report = calculate(
        [
            _node(
                "in",
                name="Ввод",
                node_type="INPUT",
                phases=1,
                phase_label="L1",
                max_load_w=5000,
            ),
            _node(
                "load",
                name="Нагрузка",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=0.7,
                measured_w=900,
                measurement_fresh=True,
            ),
        ],
        [LoadLink("in", "load")],
    )
    assert report.nodes["load"].estimated_w == 700
    assert report.nodes["load"].used_w == 900
    assert report.nodes["in"].headroom_w == 4300
    assert any(item["code"] == "measurement_gap" for item in report.nodes["load"].warnings)


def test_power_cycle_is_rejected() -> None:
    with pytest.raises(CycleDetected):
        ensure_power_acyclic({"a": ["b"]}, "b", "a")
    with pytest.raises(CycleDetected):
        calculate(
            [_node("a", node_type="PANEL", phases=3), _node("b", node_type="PDU", phases=3)],
            [LoadLink("a", "b"), LoadLink("b", "a")],
        )


def test_failover_verdicts_and_shared_upstream() -> None:
    single = calculate(
        [
            _node("in", name="Ввод", node_type="INPUT", phases=3, max_load_w=10000, feed_id="A"),
            _node(
                "psu",
                name="PSU",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                feed_id="A",
            ),
        ],
        [LoadLink("in", "psu")],
    )
    assert single.device_failover["psu"] == "SINGLE_FEED"

    same = calculate(
        [
            _node("in", name="Ввод", node_type="INPUT", phases=3, max_load_w=10000, feed_id="A"),
            _node(
                "a",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                parent_device_id="dev",
                feed_id="A",
            ),
            _node(
                "b",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                parent_device_id="dev",
                feed_id="A",
            ),
        ],
        [LoadLink("in", "a"), LoadLink("in", "b")],
    )
    assert same.device_failover["dev"] == "SAME_FEED"

    resilient = _pair(limit_b=100_000)
    assert resilient.device_failover["dev"] == "RESILIENT"

    risk = _pair(limit_b=100)
    assert risk.device_failover["dev"] == "AT_RISK"

    unknown = calculate(
        [
            _node(
                "psu",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=100,
                utilization=1,
            )
        ],
        [],
    )
    assert unknown.device_failover["psu"] == "UNKNOWN"

    shared = _two_devices()
    assert shared.loss_inlet["A"]["ups-b"] == 2000


def _pair(limit_b: int):
    return calculate(
        [
            _node(
                "in-a",
                name="A",
                node_type="INPUT",
                phases=3,
                max_load_w=100_000,
                feed_id="A",
            ),
            _node(
                "in-b",
                name="B",
                node_type="INPUT",
                phases=3,
                max_load_w=limit_b,
                feed_id="B",
            ),
            _node(
                "a",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                parent_device_id="dev",
                feed_id="A",
            ),
            _node(
                "b",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                parent_device_id="dev",
                feed_id="B",
            ),
        ],
        [LoadLink("in-a", "a"), LoadLink("in-b", "b")],
    )


def _two_devices():
    nodes = [
        _node("ups-a", name="UPS-A", node_type="UPS", phases=3, feed_id="A"),
        _node("ups-b", name="UPS-B", node_type="UPS", phases=3, feed_id="B"),
    ]
    links = []
    for index, device in enumerate(("d1", "d2"), start=1):
        nodes.append(
            _node(
                f"a{index}",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                parent_device_id=device,
                feed_id="A",
            )
        )
        nodes.append(
            _node(
                f"b{index}",
                node_type="PSU",
                phases=1,
                phase_label="L1",
                nameplate_w=1000,
                utilization=1,
                parent_device_id=device,
                feed_id="B",
            )
        )
        links.append(LoadLink("ups-a", f"a{index}"))
        links.append(LoadLink("ups-b", f"b{index}"))
    return calculate(nodes, links)
