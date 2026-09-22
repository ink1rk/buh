"""Модели данных ITMS.

Слой не содержит бизнес-логики: только структура, ограничения и связи.
"""

from itms.models.audit import AuditChange, AuditLog
from itms.models.base import Base
from itms.models.cmdb import (
    Ci,
    CiRelation,
    CiTag,
    CustomFieldDef,
    CustomFieldValue,
    Location,
    SearchIndex,
    Tag,
)
from itms.models.directory import (
    Department,
    Employee,
    EmployeeResponsibility,
    Organization,
    ResponsibilityArea,
    UserAccount,
    UserSession,
)
from itms.models.documents import (
    Attachment,
    Document,
    DocumentFolder,
    DocumentLink,
    DocumentVersion,
    FileObject,
)
from itms.models.system import AppSetting, ImportJob, OutboxEvent

__all__ = [
    "AppSetting",
    "Attachment",
    "AuditChange",
    "AuditLog",
    "Base",
    "Ci",
    "CiRelation",
    "CiTag",
    "CustomFieldDef",
    "CustomFieldValue",
    "Department",
    "Document",
    "DocumentFolder",
    "DocumentLink",
    "DocumentVersion",
    "Employee",
    "EmployeeResponsibility",
    "FileObject",
    "ImportJob",
    "Location",
    "Organization",
    "OutboxEvent",
    "ResponsibilityArea",
    "SearchIndex",
    "Tag",
    "UserAccount",
    "UserSession",
]
