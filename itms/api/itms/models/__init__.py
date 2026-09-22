"""Модели данных ITMS.

Слой не содержит бизнес-логики: только структура, ограничения и связи.
"""

from itms.models.audit import AuditChange, AuditLog
from itms.models.base import Base
from itms.models.catalog import DeviceModel, Manufacturer, PortTemplate
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
from itms.models.network import (
    CableRoute,
    Connection,
    Device,
    Interface,
    InterfaceVlan,
    IpAddress,
    Prefix,
    Vlan,
    Vrf,
)
from itms.models.system import AppSetting, ImportJob, OutboxEvent

__all__ = [
    "AppSetting",
    "Attachment",
    "AuditChange",
    "AuditLog",
    "Base",
    "CableRoute",
    "Ci",
    "CiRelation",
    "CiTag",
    "Connection",
    "CustomFieldDef",
    "CustomFieldValue",
    "Department",
    "Device",
    "DeviceModel",
    "Document",
    "DocumentFolder",
    "DocumentLink",
    "DocumentVersion",
    "Employee",
    "EmployeeResponsibility",
    "FileObject",
    "ImportJob",
    "Interface",
    "InterfaceVlan",
    "IpAddress",
    "Location",
    "Manufacturer",
    "Organization",
    "OutboxEvent",
    "PortTemplate",
    "Prefix",
    "ResponsibilityArea",
    "SearchIndex",
    "Tag",
    "UserAccount",
    "UserSession",
    "Vlan",
    "Vrf",
]
