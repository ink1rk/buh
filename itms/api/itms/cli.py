"""Служебные команды: python -m itms.cli <команда>."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from itms.core.config import settings
from itms.core.context import ActorKind, RequestContext, use_context
from itms.core.db import dispose_engine, session_scope
from itms.domain.audit_rules import configure_audit
from itms.models.directory import Organization
from itms.models.enums import CiStatus, CiType, Criticality, LocationType, SupportLine
from itms.services import auth_service, ci_service, directory_service, location_service

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
    print("Демонстрационные данные добавлены")


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
