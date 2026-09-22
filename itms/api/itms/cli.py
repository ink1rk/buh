"""Служебные команды: python -m itms.cli <команда>."""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.config import settings
from itms.core.context import ActorKind, RequestContext, use_context
from itms.core.db import dispose_engine, session_scope
from itms.domain.audit_rules import configure_audit
from itms.models.catalog import Manufacturer
from itms.models.cmdb import Ci, Location
from itms.models.diagram import Diagram
from itms.models.directory import Employee, Organization
from itms.models.enums import (
    CableCategory,
    CableMedium,
    CiStatus,
    CiType,
    Criticality,
    DeviceRole,
    DiagramType,
    InterfaceType,
    IpRole,
    LocationType,
    PanelSide,
    Priority,
    ProjectStatus,
    RackFace,
    SupportLine,
    VlanMode,
    ZeroUSide,
)
from itms.models.network import Interface
from itms.models.projects import Project
from itms.services import (
    auth_service,
    catalog_service,
    ci_service,
    device_service,
    diagram_service,
    directory_service,
    ipam_service,
    location_service,
    network_service,
    project_service,
    rack_service,
)

USAGE = """Команды:
  bootstrap        создать владельца системы и организацию
  seed-demo        добавить небольшой демонстрационный набор данных
  cleanup-sessions удалить истёкшие сессии
"""


async def bootstrap() -> None:
    configure_audit()
    async with session_scope() as session:
        with use_context(
            RequestContext(actor_kind=ActorKind.SYSTEM, actor_label="Установка", source="cli")
        ):
            owner, generated_password = await auth_service.bootstrap_owner(session)
            organization = (
                await session.execute(select(Organization).limit(1))
            ).scalar_one_or_none()
            if organization is None:
                await directory_service.upsert_organization(session, {"name": "Моя организация"})
    print(f"Владелец системы: {owner.email}")
    if generated_password:
        print(f"Сгенерированный пароль (сохраните его): {generated_password}")
    else:
        print("Пароль задан переменной окружения ITMS_BOOTSTRAP_OWNER_PASSWORD")


async def seed_demo() -> None:
    configure_audit()
    async with session_scope() as session:
        with use_context(
            RequestContext(actor_kind=ActorKind.SYSTEM, actor_label="Демо-данные", source="cli")
        ):
            await directory_service.upsert_organization(session, {"name": "Моя организация"})
            site, server_room, floor, server, switch = await _ensure_demo_cmdb(session)
            seeded = (
                await session.execute(select(Manufacturer.id).where(Manufacturer.name == "Dell"))
            ).scalar_one_or_none()
            if not seeded:
                await _seed_network(
                    session, site.id, server_room.id, floor.id, server.id, switch.id
                )
            await _ensure_demo_diagram(session, floor.id)
            await _ensure_demo_rack(session, server_room.id)
            await _ensure_demo_project(session)
            if seeded:
                print("Демонстрационные данные уже есть")
                return
    print("Демонстрационные данные добавлены")


async def _ci_by_code(session: AsyncSession, code: str) -> Ci | None:
    return (
        await session.execute(select(Ci).where(Ci.code == code, Ci.deleted_at.is_(None)))
    ).scalar_one_or_none()


async def _walk_to_type(
    session: AsyncSession, location_id: uuid.UUID | None, location_type: LocationType
) -> Location | None:
    current_id = location_id
    while current_id:
        location = await session.get(Location, current_id)
        if location is None:
            return None
        if location.location_type == location_type:
            return location
        current_id = location.parent_id
    return None


async def _ensure_demo_cmdb(
    session: AsyncSession,
) -> tuple[Location, Location, Location, Ci, Ci]:
    """Создаёт площадку и базовые объекты Phase 1, либо находит уже заведённые."""
    server = await _ci_by_code(session, "SRV-01")
    switch = await _ci_by_code(session, "SW-CORE-1")
    if server and switch and server.location_id:
        server_room = await session.get(Location, server.location_id)
        floor = await _walk_to_type(session, server.location_id, LocationType.FLOOR)
        site = await _walk_to_type(session, server.location_id, LocationType.SITE)
        if server_room and floor and site:
            return site, server_room, floor, server, switch

    site = await location_service.create_location(
        session, {"name": "Главный офис", "location_type": LocationType.SITE}
    )
    building = await location_service.create_location(
        session,
        {"name": "Здание А", "location_type": LocationType.BUILDING, "parent_id": site.id},
    )
    floor = await location_service.create_location(
        session,
        {"name": "2 этаж", "location_type": LocationType.FLOOR, "parent_id": building.id},
    )
    server_room = await location_service.create_location(
        session,
        {"name": "Серверная", "location_type": LocationType.ROOM, "parent_id": floor.id},
    )
    engineer = await directory_service.create_employee(
        session,
        {
            "full_name": "Иванов Иван",
            "position": "Системный администратор",
            "support_line": SupportLine.SECOND,
        },
    )
    server = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.DEVICE,
            "code": "SRV-01",
            "name": "Сервер виртуализации 1",
            "criticality": Criticality.CRITICAL,
            "location_id": server_room.id,
            "owner_employee_id": engineer.id,
            "vendor": "Dell",
            "model": "PowerEdge R650",
            "serial_number": "CN0X1Y2Z",
            "tags": ["виртуализация", "прод"],
        },
    )
    switch = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.DEVICE,
            "code": "SW-CORE-1",
            "name": "Ядро сети",
            "criticality": Criticality.CRITICAL,
            "location_id": server_room.id,
            "vendor": "MikroTik",
            "model": "CRS354",
        },
    )
    service = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.SERVICE,
            "code": "SVC-1C",
            "name": "1С: Предприятие",
            "criticality": Criticality.CRITICAL,
            "status": CiStatus.ACTIVE,
        },
    )
    await ci_service.create_relation(
        session,
        {
            "source_ci_id": service.id,
            "target_ci_id": server.id,
            "rel_type": "DEPENDS_ON",
            "description": "Сервис работает на этом сервере",
        },
    )
    await ci_service.create_relation(
        session,
        {
            "source_ci_id": server.id,
            "target_ci_id": switch.id,
            "rel_type": "CONNECTED_TO",
        },
    )
    return site, server_room, floor, server, switch


async def _ensure_demo_diagram(session: AsyncSession, floor_id: uuid.UUID) -> None:
    """Сетевая схема этажа: серверная и точка доступа попадают в одно поддерево."""
    existing = (
        await session.execute(select(Diagram.id).where(Diagram.name == "Сеть 2 этажа"))
    ).scalar_one_or_none()
    if existing:
        return
    await diagram_service.create_diagram(
        session,
        {
            "name": "Сеть 2 этажа",
            "diagram_type": DiagramType.NETWORK,
            "location_id": floor_id,
            "description": (
                "Кабели серверной и точки доступа. Раскладка хранится отдельно от модели."
            ),
            "autofill": True,
        },
    )


async def _ensure_demo_project(session: AsyncSession) -> None:
    """Проект перехода серверной: этапы, цепочка FS и связь со стойкой R1."""
    existing = (
        await session.execute(select(Project.id).where(Project.key == "PWR"))
    ).scalar_one_or_none()
    if existing:
        return
    engineer = (
        await session.execute(select(Employee).where(Employee.full_name == "Иванов Иван"))
    ).scalar_one_or_none()
    today = date.today()
    view = await project_service.create_project(
        session,
        {
            "key": "PWR",
            "name": "Увеличение мощности серверной",
            "description": (
                "Переход серверной из текущего состояния к целевому: обследование ввода, "
                "расчёт нагрузки, согласование, монтаж и обновление модели."
            ),
            "status": ProjectStatus.IN_PROGRESS,
            "priority": Priority.HIGH,
            "owner_id": engineer.id if engineer else None,
            "start_date": today,
            "due_date": today + timedelta(days=26),
            "budget_planned": 1_500_000,
        },
    )
    project_id = view["project"]["id"]
    phase_names = ["Обследование", "Расчёт", "Согласование", "Монтаж", "Ввод"]
    phase_ids: list[uuid.UUID] = []
    for index, name in enumerate(phase_names, start=1):
        view = await project_service.add_phase(
            session, project_id, {"name": name, "order_index": index}
        )
        phase_ids.append(next(item["id"] for item in view["phases"] if item["name"] == name))
    view = await project_service.add_milestone(
        session,
        project_id,
        {
            "name": "Согласование получено",
            "due_date": today + timedelta(days=15),
            "description": "Технические условия согласованы",
        },
    )
    milestone_id = next(item["id"] for item in view["milestones"])
    plan = [
        ("Обследовать ввод", 0, 0, 4, 480, None),
        ("Рассчитать нагрузку", 1, 5, 8, 360, None),
        ("Согласовать технические условия", 2, 9, 15, 240, milestone_id),
        ("Смонтировать оборудование", 3, 16, 23, 960, None),
        ("Обновить модель", 4, 24, 26, 180, None),
        ("Подготовить спецификацию", 1, 5, 6, 120, None),
    ]
    task_ids: list[uuid.UUID] = []
    for title, phase_index, start_offset, due_offset, estimate, milestone in plan:
        view = await project_service.add_task(
            session,
            project_id,
            {
                "title": title,
                "phase_id": phase_ids[phase_index],
                "milestone_id": milestone,
                "assignee_id": engineer.id if engineer else None,
                "start_date": today + timedelta(days=start_offset),
                "due_date": today + timedelta(days=due_offset),
                "estimate_min": estimate,
                "priority": Priority.HIGH if phase_index == 3 else Priority.MEDIUM,
            },
        )
        task_ids.append(next(item["id"] for item in view["tasks"] if item["title"] == title))
    chain = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5)]
    for predecessor, successor in chain:
        await project_service.add_dependency(
            session,
            project_id,
            {
                "predecessor_id": task_ids[predecessor],
                "successor_id": task_ids[successor],
                "dep_kind": "FS",
                "lag_days": 0,
            },
        )
    for code, involvement in (("R1", "изменяется"), ("SRV-01", "затронут")):
        ci = await _ci_by_code(session, code)
        if ci:
            await project_service.link_ci(
                session, project_id, {"ci_id": ci.id, "involvement": involvement}
            )
    if engineer:
        await project_service.add_member(
            session, project_id, {"employee_id": engineer.id, "role": "владелец"}
        )


async def _ensure_demo_rack(session: AsyncSession, server_room_id: uuid.UUID) -> None:
    """Стойка серверной: сервер на оба фасада, коммутатор и панель спереди, PDU сбоку."""
    if await _ci_by_code(session, "R1"):
        return
    created = await rack_service.create_rack(
        session,
        {
            "name": "Стойка R1",
            "code": "R1",
            "location_id": server_room_id,
            "u_height": 42,
            "depth_mm": 1000,
            "max_weight_kg": 800,
            "max_power_w": 5000,
        },
    )
    rack_id = created["rack"]["id"]
    server = await _ci_by_code(session, "SRV-01")
    switch = await _ci_by_code(session, "SW-CORE-1")
    panel = await _ci_by_code(session, "PP-01")
    if server is None or switch is None or panel is None:
        return
    await rack_service.place_mount(
        session,
        rack_id,
        {
            "ci_id": server.id,
            "position_u": 20,
            "u_height": 1,
            "face": RackFace.FULL,
            "weight_kg": 18,
        },
    )
    await rack_service.place_mount(
        session,
        rack_id,
        {
            "ci_id": switch.id,
            "position_u": 36,
            "u_height": 1,
            "face": RackFace.FRONT,
            "weight_kg": 6,
        },
    )
    await rack_service.place_mount(
        session,
        rack_id,
        {
            "ci_id": panel.id,
            "position_u": 38,
            "u_height": 1,
            "face": RackFace.FRONT,
            "weight_kg": 3,
        },
    )
    pdu = await _ci_by_code(session, "PDU-R1")
    if pdu is None:
        pdu = await ci_service.create_ci(
            session,
            {
                "ci_type": CiType.DEVICE,
                "code": "PDU-R1",
                "name": "PDU стойки R1",
                "criticality": Criticality.HIGH,
                "location_id": server_room_id,
                "status": CiStatus.ACTIVE,
            },
        )
        await device_service.upsert_device(session, pdu.id, {"device_role": DeviceRole.PDU})
    await rack_service.place_mount(
        session,
        rack_id,
        {
            "ci_id": pdu.id,
            "position_u": 1,
            "u_height": 0,
            "face": RackFace.FRONT,
            "zero_u_side": ZeroUSide.LEFT,
        },
    )


async def _seed_network(
    session: AsyncSession,
    site_id: uuid.UUID,
    server_room_id: uuid.UUID,
    floor_id: uuid.UUID,
    server_id: uuid.UUID,
    switch_id: uuid.UUID,
) -> None:
    """Каталог, профили устройств, кабельная трасса через панель и адресация.

    Топология намеренно маленькая, но в ней есть всё, ради чего заводился слой:
    сквозной линк через патч-панель, резервированный аплинк и занятые подсети.
    """
    dell = await catalog_service.create_manufacturer(session, {"name": "Dell"})
    mikrotik = await catalog_service.create_manufacturer(session, {"name": "MikroTik"})
    legrand = await catalog_service.create_manufacturer(session, {"name": "Legrand"})

    server_model = await catalog_service.create_model(
        session,
        {
            "manufacturer_id": dell.id,
            "model": "PowerEdge R650",
            "default_role": DeviceRole.SERVER,
            "u_height": 1,
            "psu_count": 2,
            "power_nameplate_w": 750,
            "power_max_w": 1100,
            "port_templates": [
                {
                    "name_pattern": "Gi{n}",
                    "count": 4,
                    "interface_type": InterfaceType.RJ45,
                    "speed_mbps": 1000,
                    "position": 10,
                },
                {
                    "name_pattern": "SFP+{n}",
                    "count": 2,
                    "interface_type": InterfaceType.SFP_PLUS,
                    "speed_mbps": 10000,
                    "position": 20,
                },
            ],
        },
    )
    switch_model = await catalog_service.create_model(
        session,
        {
            "manufacturer_id": mikrotik.id,
            "model": "CRS354-48G-4S+2Q",
            "default_role": DeviceRole.L2_SWITCH,
            "u_height": 1,
            "power_nameplate_w": 60,
            "port_templates": [
                {
                    "name_pattern": "ether{n}",
                    "count": 24,
                    "interface_type": InterfaceType.RJ45,
                    "speed_mbps": 1000,
                    "poe_capable": True,
                    "position": 10,
                },
                {
                    "name_pattern": "sfp-sfpplus{n}",
                    "count": 4,
                    "interface_type": InterfaceType.SFP_PLUS,
                    "speed_mbps": 10000,
                    "position": 20,
                },
            ],
        },
    )
    panel_model = await catalog_service.create_model(
        session,
        {
            "manufacturer_id": legrand.id,
            "model": "LCS3 24xRJ45",
            "default_role": DeviceRole.PATCH_PANEL,
            "u_height": 1,
            "psu_count": 0,
            "port_templates": [
                {
                    "name_pattern": "Front-{n}",
                    "count": 12,
                    "interface_type": InterfaceType.RJ45,
                    "position": 10,
                },
                {
                    "name_pattern": "Rear-{n}",
                    "count": 12,
                    "interface_type": InterfaceType.RJ45,
                    "position": 20,
                },
            ],
        },
    )

    panel = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.DEVICE,
            "code": "PP-01",
            "name": "Патч-панель серверной",
            "criticality": Criticality.MEDIUM,
            "location_id": server_room_id,
            "vendor": "Legrand",
        },
    )
    access_point = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.DEVICE,
            "code": "AP-201",
            "name": "Точка доступа 2 этаж",
            "criticality": Criticality.MEDIUM,
            "location_id": floor_id,
            "vendor": "MikroTik",
        },
    )

    await device_service.upsert_device(
        session,
        server_id,
        {
            "device_model_id": server_model.id,
            "device_role": DeviceRole.SERVER,
            "hostname": "srv-01.office.local",
            "asset_tag": "INV-000101",
            "mgmt_ip": "10.10.10.11",
            "psu_count": 2,
            "power_nameplate_w": 750,
            "warranty_until": date.today() + timedelta(days=45),
        },
    )
    await device_service.upsert_device(
        session,
        switch_id,
        {
            "device_model_id": switch_model.id,
            "device_role": DeviceRole.L2_SWITCH,
            "hostname": "sw-core-1.office.local",
            "asset_tag": "INV-000102",
            "mgmt_ip": "10.10.10.2",
        },
    )
    await device_service.upsert_device(
        session,
        panel.id,
        {"device_model_id": panel_model.id, "device_role": DeviceRole.PATCH_PANEL, "psu_count": 0},
    )
    await device_service.upsert_device(
        session,
        access_point.id,
        {
            "device_role": DeviceRole.ACCESS_POINT,
            "hostname": "ap-201.office.local",
            "mgmt_ip": "10.10.10.31",
        },
    )
    await network_service.create_interface(
        session,
        access_point.id,
        {"name": "eth1", "interface_type": InterfaceType.RJ45, "speed_mbps": 1000},
    )

    ports = await _port_index(session, [server_id, switch_id, panel.id, access_point.id])

    # Фронт и тыл панели сопряжены попарно — только так трассировка проходит насквозь.
    for index in range(1, 13):
        await network_service.update_interface(
            session,
            ports[(panel.id, f"Front-{index}")],
            {
                "panel_side": PanelSide.FRONT,
                "paired_interface_id": ports[(panel.id, f"Rear-{index}")],
            },
        )
        await network_service.update_interface(
            session,
            ports[(panel.id, f"Rear-{index}")],
            {
                "panel_side": PanelSide.REAR,
                "paired_interface_id": ports[(panel.id, f"Front-{index}")],
            },
        )

    route = await network_service.create_route(
        session,
        {
            "name": "Лоток «Серверная — 2 этаж»",
            "route_type": "Кабельный лоток",
            "from_location_id": server_room_id,
            "to_location_id": floor_id,
            "length_m": 42,
            "capacity": 24,
        },
    )

    # Аплинк сервера продублирован двумя оптическими линками в одной группе.
    for index in (1, 2):
        await network_service.create_connection(
            session,
            {
                "a_interface_id": ports[(server_id, f"SFP+{index}")],
                "b_interface_id": ports[(switch_id, f"sfp-sfpplus{index}")],
                "medium": CableMedium.FIBER,
                "category": CableCategory.OM4,
                "label": f"SRV01-SW-{index}",
                "length_m": 3,
                "is_redundant": True,
                "redundancy_group": "SRV-01 uplink",
            },
        )
    await network_service.create_connection(
        session,
        {
            "a_interface_id": ports[(switch_id, "ether1")],
            "b_interface_id": ports[(panel.id, "Rear-1")],
            "medium": CableMedium.COPPER,
            "category": CableCategory.CAT6,
            "label": "SW-PP-01",
            "length_m": 2,
        },
    )
    await network_service.create_connection(
        session,
        {
            "a_interface_id": ports[(panel.id, "Front-1")],
            "b_interface_id": ports[(access_point.id, "eth1")],
            "medium": CableMedium.COPPER,
            "category": CableCategory.CAT6,
            "label": "PP-AP-201",
            "length_m": 38,
            "route_id": route.id,
        },
    )

    mgmt_vlan = await ipam_service.create_vlan(
        session, {"vid": 10, "name": "Управление", "site_id": site_id, "purpose": "Управление"}
    )
    server_vlan = await ipam_service.create_vlan(
        session, {"vid": 20, "name": "Серверы", "site_id": site_id, "purpose": "Продуктив"}
    )
    user_vlan = await ipam_service.create_vlan(
        session, {"vid": 30, "name": "Пользователи", "site_id": site_id}
    )
    await ipam_service.create_prefix(
        session,
        {
            "cidr": "10.10.10.0/24",
            "vlan_id": mgmt_vlan.id,
            "gateway": "10.10.10.1",
            "site_id": site_id,
            "description": "Сеть управления оборудованием",
        },
    )
    await ipam_service.create_prefix(
        session,
        {
            "cidr": "10.10.20.0/24",
            "vlan_id": server_vlan.id,
            "gateway": "10.10.20.1",
            "site_id": site_id,
            "description": "Серверный сегмент",
        },
    )
    await ipam_service.create_prefix(
        session,
        {
            "cidr": "10.10.30.0/24",
            "vlan_id": user_vlan.id,
            "gateway": "10.10.30.1",
            "site_id": site_id,
            "description": "Пользовательский сегмент",
        },
    )
    await ipam_service.create_address(
        session,
        {
            "address": "10.10.20.10",
            "interface_id": ports[(server_id, "Gi1")],
            "ci_id": server_id,
            "dns_name": "srv-01.office.local",
            "role": IpRole.PRIMARY,
        },
    )
    await ipam_service.create_address(
        session,
        {
            "address": "10.10.10.2",
            "ci_id": switch_id,
            "dns_name": "sw-core-1.office.local",
            "role": IpRole.MANAGEMENT,
        },
    )
    await ipam_service.create_address(
        session,
        {
            "address": "10.10.10.31",
            "interface_id": ports[(access_point.id, "eth1")],
            "ci_id": access_point.id,
            "dns_name": "ap-201.office.local",
            "role": IpRole.MANAGEMENT,
        },
    )
    await network_service.update_interface(
        session,
        ports[(server_id, "Gi1")],
        {"vlans": [{"vlan_id": server_vlan.id, "mode": VlanMode.ACCESS}]},
    )
    await network_service.update_interface(
        session,
        ports[(switch_id, "ether1")],
        {
            "vlans": [
                {"vlan_id": mgmt_vlan.id, "mode": VlanMode.NATIVE},
                {"vlan_id": user_vlan.id, "mode": VlanMode.TAGGED},
            ]
        },
    )


async def _port_index(
    session: AsyncSession, ci_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], uuid.UUID]:
    rows = await session.execute(
        select(Interface.ci_id, Interface.name, Interface.id).where(Interface.ci_id.in_(ci_ids))
    )
    return {(ci_id, name): interface_id for ci_id, name, interface_id in rows}


async def cleanup_sessions() -> None:
    async with session_scope() as session:
        removed = await auth_service.cleanup_sessions(session)
    print(f"Удалено истёкших сессий: {removed}")


COMMANDS = {
    "bootstrap": bootstrap,
    "seed-demo": seed_demo,
    "cleanup-sessions": cleanup_sessions,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(USAGE)
        return 1
    command = COMMANDS[sys.argv[1]]

    async def runner() -> None:
        try:
            await command()
        finally:
            await dispose_engine()

    asyncio.run(runner())
    return 0


if __name__ == "__main__":
    print(f"База данных: {settings.database_url.split('@')[-1]}")
    raise SystemExit(main())
