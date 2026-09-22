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
from itms.models.datacenter import Rack, RackMount
from itms.models.diagram import Diagram, DiagramEdge, DiagramNode
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
from itms.models.power import (
    PowerFeed,
    PowerLink,
    PowerMeasurement,
    PowerNode,
    PowerScenario,
    PowerScenarioItem,
)
from itms.models.projects import (
    Milestone,
    Phase,
    Project,
    ProjectCi,
    ProjectMember,
    Task,
    TaskCi,
    TaskDependency,
    TimeEntry,
)
from itms.models.system import AppSetting, ImportJob, OutboxEvent
from itms.models.transition import ChangeItem, PlannedChange, StateSnapshot

__all__ = [
    "AppSetting",
    "Attachment",
    "AuditChange",
    "AuditLog",
    "Base",
    "CableRoute",
    "ChangeItem",
    "Ci",
    "CiRelation",
    "CiTag",
    "Connection",
    "CustomFieldDef",
    "CustomFieldValue",
    "Department",
    "Device",
    "DeviceModel",
    "Diagram",
    "DiagramEdge",
    "DiagramNode",
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
    "Milestone",
    "Organization",
    "OutboxEvent",
    "Phase",
    "PlannedChange",
    "PortTemplate",
    "PowerFeed",
    "PowerLink",
    "PowerMeasurement",
    "PowerNode",
    "PowerScenario",
    "PowerScenarioItem",
    "Prefix",
    "Project",
    "ProjectCi",
    "ProjectMember",
    "Rack",
    "RackMount",
    "ResponsibilityArea",
    "SearchIndex",
    "StateSnapshot",
    "Tag",
    "Task",
    "TaskCi",
    "TaskDependency",
    "TimeEntry",
    "UserAccount",
    "UserSession",
    "Vlan",
    "Vrf",
]
