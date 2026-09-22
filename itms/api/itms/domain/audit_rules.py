"""Что именно аудируется и какие поля считаются критичными.

Критичное поле нельзя изменить без указания причины или ссылки на проект,
изменение или задачу: через год по значению параметра должно быть понятно,
кто, когда и в рамках чего его изменил.
"""

from __future__ import annotations

from itms.core.audit import AuditConfig, install_audit, register_audit
from itms.models.cmdb import Ci, CiRelation, CustomFieldDef, Location, Tag
from itms.models.directory import (
    Department,
    Employee,
    Organization,
    ResponsibilityArea,
    UserAccount,
)
from itms.models.documents import Document, DocumentFolder, DocumentLink

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
    install_audit()
