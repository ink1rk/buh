"""Доменные правила проверяются без базы: это чистая логика."""

from __future__ import annotations

import uuid

import pytest

from itms.core.errors import CycleDetected, Invalid
from itms.domain.lifecycle import is_deletion_protected, validate_status_transition
from itms.domain.locations import build_path, validate_hierarchy
from itms.domain.permissions import Permission, has_permission
from itms.domain.relations import detect_cycle, group_of, validate_relation
from itms.domain.search import normalize_keywords
from itms.models.cmdb import Ci
from itms.models.enums import CiStatus, CiType, Criticality, LocationType, RelationType, UserRole


def test_status_transition_allows_known_path() -> None:
    validate_status_transition(CiStatus.ACTIVE, CiStatus.MAINTENANCE)
    validate_status_transition(CiStatus.DECOMMISSIONING, CiStatus.RETIRED)


def test_status_transition_rejects_resurrection_from_retired() -> None:
    with pytest.raises(Invalid):
        validate_status_transition(CiStatus.RETIRED, CiStatus.ACTIVE)


def test_power_cannot_be_expressed_as_logical_relation() -> None:
    """Электрика описывается только power_link — второго источника истины быть не должно."""
    with pytest.raises(Invalid) as exc:
        validate_relation(
            source_id=uuid.uuid4(),
            target_id=uuid.uuid4(),
            source_type=CiType.POWER_NODE,
            target_type=CiType.POWER_NODE,
            rel_type=RelationType.DEPENDS_ON,
        )
    assert exc.value.details["code_hint"] == "power_relation_forbidden"


def test_relation_type_enum_has_no_powered_by() -> None:
    assert "POWERED_BY" not in {member.value for member in RelationType}


def test_dependency_cycle_is_detected() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    edges = {a: [b], b: [c]}
    detect_cycle(source_id=c, target_id=a, rel_type=RelationType.RELATES_TO, edges=edges)
    with pytest.raises(CycleDetected):
        detect_cycle(source_id=c, target_id=a, rel_type=RelationType.DEPENDS_ON, edges=edges)


def test_relation_grouping_covers_all_types() -> None:
    for rel_type in RelationType:
        assert group_of(rel_type)


def test_location_hierarchy_rules() -> None:
    validate_hierarchy(LocationType.ROOM, LocationType.FLOOR)
    with pytest.raises(Invalid):
        validate_hierarchy(LocationType.FLOOR, LocationType.ROOM)
    with pytest.raises(Invalid):
        validate_hierarchy(LocationType.ROOM, None)


def test_path_building() -> None:
    assert build_path(None, "Офис") == "Офис"
    assert build_path("Офис / Здание А", "2 этаж") == "Офис / Здание А / 2 этаж"


def test_critical_objects_are_protected_from_deletion() -> None:
    critical = Ci(ci_type=CiType.APPLICATION, name="Биллинг", criticality=Criticality.CRITICAL)
    ordinary = Ci(ci_type=CiType.OTHER, name="Черновик", criticality=Criticality.LOW)
    topology = Ci(ci_type=CiType.DEVICE, name="Коммутатор", criticality=Criticality.LOW)
    assert is_deletion_protected(critical)
    assert is_deletion_protected(topology)
    assert not is_deletion_protected(ordinary)


def test_keywords_include_stripped_variants() -> None:
    keywords = normalize_keywords(["00:1A:2B:3C:4D:5E", "SRV-01"])
    assert "00:1a:2b:3c:4d:5e" in keywords
    assert "001a2b3c4d5e" in keywords
    assert "srv-01" in keywords and "srv01" in keywords


def test_permissions_are_role_scoped() -> None:
    assert has_permission(UserRole.OWNER, Permission.SETTINGS_WRITE)
    assert not has_permission(UserRole.VIEWER, Permission.CI_WRITE)
    assert has_permission(UserRole.ENGINEER, Permission.CI_WRITE)
    assert not has_permission(UserRole.ENGINEER, Permission.USER_MANAGE)
