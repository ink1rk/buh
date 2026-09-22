from __future__ import annotations

from enum import StrEnum


class CiType(StrEnum):
    LOCATION = "LOCATION"
    RACK = "RACK"
    DEVICE = "DEVICE"
    VM = "VM"
    CLUSTER = "CLUSTER"
    APPLICATION = "APPLICATION"
    DATABASE = "DATABASE"
    SERVICE = "SERVICE"
    STORAGE = "STORAGE"
    POWER_NODE = "POWER_NODE"
    DOMAIN = "DOMAIN"
    CERTIFICATE = "CERTIFICATE"
    CIRCUIT = "CIRCUIT"
    OTHER = "OTHER"


class CiStatus(StrEnum):
    PLANNED = "PLANNED"
    ORDERED = "ORDERED"
    IN_STOCK = "IN_STOCK"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"
    RESERVED = "RESERVED"
    DECOMMISSIONING = "DECOMMISSIONING"
    RETIRED = "RETIRED"


#: Статусы, из которых объект уже не возвращается в работу обычным редактированием.
TERMINAL_CI_STATUSES = frozenset({CiStatus.RETIRED})

#: Допустимые переходы статусов CI.
CI_STATUS_TRANSITIONS: dict[CiStatus, frozenset[CiStatus]] = {
    CiStatus.PLANNED: frozenset({CiStatus.ORDERED, CiStatus.IN_STOCK, CiStatus.ACTIVE,
                                 CiStatus.RESERVED, CiStatus.RETIRED}),
    CiStatus.ORDERED: frozenset({CiStatus.IN_STOCK, CiStatus.ACTIVE, CiStatus.RETIRED}),
    CiStatus.IN_STOCK: frozenset({CiStatus.ACTIVE, CiStatus.RESERVED,
                                  CiStatus.DECOMMISSIONING, CiStatus.RETIRED}),
    CiStatus.RESERVED: frozenset({CiStatus.ACTIVE, CiStatus.IN_STOCK, CiStatus.RETIRED}),
    CiStatus.ACTIVE: frozenset({CiStatus.DEGRADED, CiStatus.MAINTENANCE,
                                CiStatus.DECOMMISSIONING, CiStatus.RETIRED}),
    CiStatus.DEGRADED: frozenset({CiStatus.ACTIVE, CiStatus.MAINTENANCE,
                                  CiStatus.DECOMMISSIONING, CiStatus.RETIRED}),
    CiStatus.MAINTENANCE: frozenset({CiStatus.ACTIVE, CiStatus.DEGRADED,
                                     CiStatus.DECOMMISSIONING, CiStatus.RETIRED}),
    CiStatus.DECOMMISSIONING: frozenset({CiStatus.RETIRED, CiStatus.IN_STOCK}),
    CiStatus.RETIRED: frozenset(),
}


class Criticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Environment(StrEnum):
    PROD = "PROD"
    TEST = "TEST"
    DEV = "DEV"
    DR = "DR"


class LocationType(StrEnum):
    ORG = "ORG"
    SITE = "SITE"
    BUILDING = "BUILDING"
    FLOOR = "FLOOR"
    ROOM = "ROOM"
    ZONE = "ZONE"


#: Типы, которые могут быть корнем дерева размещений.
ROOT_LOCATION_TYPES = frozenset({LocationType.ORG, LocationType.SITE})

#: Какой тип может быть вложен в какой: физическая иерархия не должна ломаться.
LOCATION_PARENTS: dict[LocationType, frozenset[LocationType]] = {
    LocationType.ORG: frozenset(),
    LocationType.SITE: frozenset({LocationType.ORG}),
    LocationType.BUILDING: frozenset({LocationType.SITE, LocationType.ORG}),
    LocationType.FLOOR: frozenset({LocationType.BUILDING}),
    LocationType.ROOM: frozenset({LocationType.FLOOR, LocationType.BUILDING}),
    LocationType.ZONE: frozenset({LocationType.ROOM}),
}


class RelationType(StrEnum):
    """Логические связи.

    Значения POWERED_BY здесь нет и не будет: электрическая топология описывается
    только моделью power_node + power_link (см. docs/domain-model/02-domain-model.md §2.4).
    """

    DEPENDS_ON = "DEPENDS_ON"
    RUNS_ON = "RUNS_ON"
    MEMBER_OF = "MEMBER_OF"
    PART_OF = "PART_OF"
    CONNECTED_TO = "CONNECTED_TO"
    USES_STORAGE = "USES_STORAGE"
    BACKED_UP_BY = "BACKED_UP_BY"
    REPLICATES_TO = "REPLICATES_TO"
    MANAGES = "MANAGES"
    SERVES = "SERVES"
    RELATES_TO = "RELATES_TO"


#: Типы связей, для которых запрещены циклы.
ACYCLIC_RELATIONS = frozenset({RelationType.DEPENDS_ON, RelationType.PART_OF,
                               RelationType.MEMBER_OF})


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    OBSOLETE = "OBSOLETE"
    ARCHIVED = "ARCHIVED"


class DocumentKind(StrEnum):
    INSTRUCTION = "INSTRUCTION"
    REGULATION = "REGULATION"
    SCHEME = "SCHEME"
    PASSPORT = "PASSPORT"
    CONTRACT = "CONTRACT"
    ACT = "ACT"
    RUNBOOK = "RUNBOOK"
    NOTE = "NOTE"
    OTHER = "OTHER"


class EmployeeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    VACATION = "VACATION"
    SICK_LEAVE = "SICK_LEAVE"
    DISMISSED = "DISMISSED"


class SupportLine(StrEnum):
    FIRST = "FIRST"
    SECOND = "SECOND"
    THIRD = "THIRD"
    NONE = "NONE"


class UserRole(StrEnum):
    """Роли заложены сразу; в Phase 1 полноценный вход есть только у OWNER."""

    OWNER = "OWNER"
    ENGINEER = "ENGINEER"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    INVITED = "INVITED"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ARCHIVE = "ARCHIVE"
    RESTORE = "RESTORE"
    LINK = "LINK"
    UNLINK = "UNLINK"
    STATUS = "STATUS"
    APPLY = "APPLY"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"


class ImportStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"


class ImportTarget(StrEnum):
    CI = "CI"
    LOCATION = "LOCATION"
    EMPLOYEE = "EMPLOYEE"


class CustomFieldType(StrEnum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    SELECT = "SELECT"
    MULTISELECT = "MULTISELECT"
    URL = "URL"
