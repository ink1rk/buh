"""Демо-набор должен поднимать живую топологию и не ломаться при повторном запуске."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from itms.cli import seed_demo
from itms.core.db import session_scope
from itms.models.catalog import DeviceModel, Manufacturer
from itms.models.diagram import Diagram
from itms.models.network import Connection, Device, Interface, Prefix
from itms.services import network_service

pytestmark = pytest.mark.anyio


async def test_seed_demo_builds_network_topology() -> None:
    await seed_demo()
    await seed_demo()

    async with session_scope() as session:
        async def count(model: type) -> int:
            return (await session.execute(select(func.count()).select_from(model))).scalar_one()

        assert await count(Manufacturer) == 3
        assert await count(DeviceModel) == 3
        assert await count(Device) == 4
        assert await count(Connection) == 4
        assert await count(Prefix) == 3
        assert await count(Diagram) == 1

        start = (
            await session.execute(
                select(Interface.id).where(Interface.name == "eth1")
            )
        ).scalar_one()
        path = await network_service.trace(session, start)
        assert path["passed_through"]
        assert path["endpoint"] is not None
        assert path["endpoint"]["interface_name"] == "ether1"
