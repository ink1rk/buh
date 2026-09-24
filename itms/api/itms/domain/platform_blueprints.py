"""Шаблоны платформ поверх существующих типов CI.

Новых значений CI_TYPE здесь нет. vCenter — приложение со связью MANAGES,
а не хост виртуализации.
"""

from __future__ import annotations

from dataclasses import dataclass

from itms.models.enums import CiType, RelationType

BLUEPRINT_NOTE = "Шаблон платформы: предзаполненные атрибуты, не учтённый объект."


@dataclass(frozen=True, slots=True)
class BlueprintNode:
    code: str
    name: str
    ci_type: CiType
    attributes: tuple[tuple[str, str], ...] = ()
    description: str = BLUEPRINT_NOTE


@dataclass(frozen=True, slots=True)
class BlueprintLink:
    source: str
    target: str
    rel_type: RelationType


NODES: tuple[BlueprintNode, ...] = (
    BlueprintNode(
        "TPL-AD",
        "Домен Active Directory",
        CiType.DOMAIN,
        (("platform", "active_directory"),),
    ),
    BlueprintNode(
        "TPL-DC",
        "Контроллер домена",
        CiType.VM,
        (("ad_role", "domain_controller"), ("roles", "dns,dhcp")),
    ),
    BlueprintNode(
        "TPL-ESXI",
        "Хост ESXi",
        CiType.DEVICE,
        (("platform", "VMWARE"),),
        BLUEPRINT_NOTE + " Профиль compute_host ставится отдельно, это не vCenter.",
    ),
    BlueprintNode(
        "TPL-VCENTER",
        "VMware vCenter",
        CiType.APPLICATION,
        (("platform", "vcenter"),),
        BLUEPRINT_NOTE + " Управляющее приложение, не хост виртуализации.",
    ),
    BlueprintNode("TPL-EXCH", "Exchange", CiType.APPLICATION, (("role", "mailbox"),)),
    BlueprintNode("TPL-EXCH-VM", "Виртуальная машина Exchange", CiType.VM),
    BlueprintNode("TPL-1C", "1С:Предприятие", CiType.APPLICATION, (("platform", "1c"),)),
    BlueprintNode(
        "TPL-1C-DB",
        "Информационная база 1С",
        CiType.DATABASE,
        (("engine", "postgres"),),
    ),
    BlueprintNode("TPL-K8S", "Кластер Kubernetes", CiType.CLUSTER, (("platform", "kubernetes"),)),
    BlueprintNode("TPL-K8S-CP", "Узел control-plane", CiType.VM, (("k8s_role", "control_plane"),)),
    BlueprintNode("TPL-KAFKA", "Кластер Kafka", CiType.CLUSTER, (("platform", "kafka"),)),
    BlueprintNode("TPL-KAFKA-1", "Брокер Kafka", CiType.APPLICATION, (("role", "broker"),)),
    BlueprintNode("TPL-N8N", "n8n", CiType.APPLICATION, (("platform", "n8n"),)),
    BlueprintNode("TPL-N8N-VM", "Виртуальная машина n8n", CiType.VM),
    BlueprintNode("TPL-N8N-DB", "База n8n", CiType.DATABASE),
    BlueprintNode(
        "TPL-GPU",
        "Хост GPU",
        CiType.DEVICE,
        (("gpu_model", "каталожный ориентир"), ("vram_gb", "48")),
        BLUEPRINT_NOTE + " Объём VRAM — паспортный ориентир, не замер.",
    ),
    BlueprintNode("TPL-LLM", "Сервис инференса", CiType.SERVICE, (("platform", "llm"),)),
    BlueprintNode(
        "TPL-MCP",
        "MCP-сервер",
        CiType.SERVICE,
        (("protocol", "mcp"), ("auth", "token"), ("tools", "catalog")),
    ),
    BlueprintNode("TPL-AGENT", "Агент разработки", CiType.APPLICATION, (("platform", "agent"),)),
)

LINKS: tuple[BlueprintLink, ...] = (
    BlueprintLink("TPL-VCENTER", "TPL-ESXI", RelationType.MANAGES),
    BlueprintLink("TPL-DC", "TPL-AD", RelationType.MEMBER_OF),
    BlueprintLink("TPL-DC", "TPL-ESXI", RelationType.RUNS_ON),
    BlueprintLink("TPL-EXCH", "TPL-EXCH-VM", RelationType.RUNS_ON),
    BlueprintLink("TPL-EXCH", "TPL-AD", RelationType.DEPENDS_ON),
    BlueprintLink("TPL-EXCH-VM", "TPL-ESXI", RelationType.RUNS_ON),
    BlueprintLink("TPL-1C", "TPL-1C-DB", RelationType.DEPENDS_ON),
    BlueprintLink("TPL-K8S-CP", "TPL-K8S", RelationType.MEMBER_OF),
    BlueprintLink("TPL-K8S-CP", "TPL-ESXI", RelationType.RUNS_ON),
    BlueprintLink("TPL-KAFKA-1", "TPL-KAFKA", RelationType.PART_OF),
    BlueprintLink("TPL-KAFKA-1", "TPL-ESXI", RelationType.RUNS_ON),
    BlueprintLink("TPL-N8N", "TPL-N8N-VM", RelationType.RUNS_ON),
    BlueprintLink("TPL-N8N", "TPL-N8N-DB", RelationType.DEPENDS_ON),
    BlueprintLink("TPL-N8N-VM", "TPL-ESXI", RelationType.RUNS_ON),
    BlueprintLink("TPL-LLM", "TPL-GPU", RelationType.RUNS_ON),
    BlueprintLink("TPL-MCP", "TPL-LLM", RelationType.DEPENDS_ON),
    BlueprintLink("TPL-MCP", "TPL-AGENT", RelationType.SERVES),
    BlueprintLink("TPL-AGENT", "TPL-LLM", RelationType.DEPENDS_ON),
    BlueprintLink("TPL-AGENT", "TPL-MCP", RelationType.RELATES_TO),
)
