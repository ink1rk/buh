"""Контрольная сумма снимка стабильна, разрыв считается по пределу плана."""

from itms.domain.transition import architecture_items, checksum, power_gap


def test_checksum_ignores_key_order() -> None:
    left = checksum({"b": 1, "a": "ввод"})
    right = checksum({"a": "ввод", "b": 1})
    assert left == right
    assert left != checksum({"a": "ввод", "b": 2})


def test_gap_blocks_when_the_ceiling_is_the_current_input() -> None:
    findings = {
        item.rule: item
        for item in power_gap(
            current_limit_w=20000,
            target_estimated_w=20497,
            required_input_w=25621,
            planned_limit_w=None,
            applied=False,
        )
    }
    assert findings["power_target"].level == "BLOCKER"
    assert findings["power_reserve"].level == "WARNING"
    assert "power_unapplied" not in findings


def test_gap_accepts_a_planned_3x50_input() -> None:
    planned = power_gap(
        current_limit_w=20000,
        target_estimated_w=20497,
        required_input_w=25621,
        planned_limit_w=32909,
        applied=False,
    )
    levels = {item.rule: item.level for item in planned}
    assert levels["power_target"] == "OK"
    assert levels["power_reserve"] == "OK"
    assert levels["power_unapplied"] == "WARNING"

    applied = power_gap(
        current_limit_w=32909,
        target_estimated_w=20497,
        required_input_w=25621,
        planned_limit_w=32909,
        applied=True,
    )
    assert {item.rule: item.level for item in applied} == {
        "power_target": "OK",
        "power_reserve": "OK",
    }
    assert "32,91 кВт" in applied[0].message


def test_architecture_puts_the_new_ups_between_the_panel_and_the_pdu() -> None:
    items = architecture_items(
        location_id="room",
        source_code="PN-1",
        source_is_panel=True,
        side_b_code="IN-B",
    )
    by_ref = {item["ref"]: item for item in items}
    assert by_ref["R2"]["create"]["plan_x"] == 1200
    assert by_ref["UPS-2"]["create"]["efficiency"] == 0.94
    assert by_ref["PDU-R2-A"]["create"]["rack_ref"] == "R2"
    assert by_ref["link-ups"]["connect"] == {"source_code": "PN-1", "target_ref": "UPS-2"}
    assert by_ref["link-pdu-a"]["connect"]["source_ref"] == "UPS-2"
    assert by_ref["link-pdu-b"]["connect"]["source_code"] == "IN-B"


def test_architecture_uses_the_only_input_when_there_is_no_second_feed() -> None:
    items = architecture_items(
        location_id=None,
        source_code="UPG-IN",
        source_is_panel=False,
        side_b_code=None,
    )
    by_ref = {item["ref"]: item for item in items}
    assert "plan_x" not in by_ref["R2"]["create"]
    assert by_ref["link-ups"]["connect"]["source_code"] == "UPG-IN"
    assert by_ref["link-pdu-b"]["connect"]["source_code"] == "UPG-IN"
