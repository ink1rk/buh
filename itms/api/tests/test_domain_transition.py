"""Контрольная сумма снимка стабильна, разрыв считается по пределу плана."""

from itms.domain.transition import checksum, power_gap


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
