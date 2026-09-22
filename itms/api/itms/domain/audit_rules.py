"""Что именно аудируется и какие поля считаются критичными.

Критичное поле нельзя изменить без указания причины или ссылки на проект,
изменение или задачу: через год по значению параметра должно быть понятно,
кто, когда и в рамках чего его изменил.
"""

from __future__ import annotations

from itms.core.audit import AuditConfig, install_audit, register_audit
from itms.models.catalog import DeviceModel, Manufacturer, PortTemplate
from itms.models.cmdb import Ci, CiRelation, CustomFieldDef, Location, Tag
from itms.models.directory import (
    Department,
    Employee,
    Organization,
    ResponsibilityArea,
    UserAccount,
)
from itms.models.documents import Document, DocumentFolder, DocumentLink
from itms.models.network import (
    CableRoute,
    Connection,
    Device,
    Interface,
    IpAddress,
    Prefix,
    Vlan,
    Vrf,
)

CI_CRITICAL_FIELDS = frozenset(
    {
        "status",
        "criticality",
        "location_id",
        "owner_employee_id",
        "archived_at",
        "deleted_at",
        "serial_number",
        # Электрические параметры появятся в Phase 4 и попадут сюда же.
    }
)

#: Поля устройства, которые нельзя менять молча: по ним считается питание,
#: строится топология и принимаются решения об обслуживании.
DEVICE_CRITICAL_FIELDS = frozenset(
    {"device_model_id", "device_role", "mgmt_ip", "power_nameplate_w", "power_max_w", "psu_count"}
)


def configure_audit() -> None:
    register_audit(
        Ci,
        AuditConfig(
            entity_type="CI",
            label_attr="name",
            critical_fields=CI_CRITICAL_FIELDS,
            ignore_fields=frozenset({"search_tsv"}),
        ),
    )
    register_audit(
        CiRelation,
        AuditConfig(entity_type="CI_RELATION", label_attr="rel_type"),
    )
    register_audit(
        Location,
        AuditConfig(
            entity_type="LOCATION",
            critical_fields=frozenset({"parent_id", "archived_at", "deleted_at"}),
        ),
    )
    register_audit(Tag, AuditConfig(entity_type="TAG"))
    register_audit(CustomFieldDef, AuditConfig(entity_type="CUSTOM_FIELD", label_attr="label"))
    register_audit(Organization, AuditConfig(entity_type="ORGANIZATION"))
    register_audit(Department, AuditConfig(entity_type="DEPARTMENT"))
    register_audit(
        Employee,
        AuditConfig(
            entity_type="EMPLOYEE",
            label_attr="full_name",
            critical_fields=frozenset({"status", "dismissed_on"}),
        ),
    )
    register_audit(ResponsibilityArea, AuditConfig(entity_type="RESPONSIBILITY_AREA"))
    register_audit(
        UserAccount,
        AuditConfig(
            entity_type="USER",
            label_attr="display_name",
            critical_fields=frozenset({"role", "status"}),
            ignore_fields=frozenset({"password_hash", "failed_login_count", "last_login_at"}),
        ),
    )
    register_audit(
        Document,
        AuditConfig(
            entity_type="DOCUMENT",
            label_attr="title",
            critical_fields=frozenset({"status", "archived_at", "deleted_at"}),
        ),
    )
    register_audit(DocumentFolder, AuditConfig(entity_type="DOCUMENT_FOLDER"))
    register_audit(DocumentLink, AuditConfig(entity_type="DOCUMENT_LINK", label_attr="entity_type"))
    register_audit(Manufacturer, AuditConfig(entity_type="MANUFACTURER"))
    register_audit(DeviceModel, AuditConfig(entity_type="DEVICE_MODEL", label_attr="model"))
    register_audit(PortTemplate, AuditConfig(entity_type="PORT_TEMPLATE",
                                             label_attr="name_pattern"))
    register_audit(
        Device,
        AuditConfig(
            entity_type="DEVICE",
            label_attr="hostname",
            critical_fields=DEVICE_CRITICAL_FIELDS,
        ),
    )
    register_audit(Interface, AuditConfig(entity_type="INTERFACE", label_attr="name"))
    register_audit(
        Connection,
        AuditConfig(
            entity_type="CONNECTION",
            label_attr="label",
            critical_fields=frozenset({"status", "a_interface_id", "b_interface_id"}),
        ),
    )
    register_audit(CableRoute, AuditConfig(entity_type="CABLE_ROUTE"))
    register_audit(Vrf, AuditConfig(entity_type="VRF"))
    register_audit(Vlan, AuditConfig(entity_type="VLAN"))
    register_audit(Prefix, AuditConfig(entity_type="PREFIX", label_attr="cidr"))
    register_audit(
        IpAddress,
        AuditConfig(
            entity_type="IP_ADDRESS",
            label_attr="address",
            critical_fields=frozenset({"status"}),
        ),
    )
    install_audit()
