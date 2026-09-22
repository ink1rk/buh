"""Демо-набор должен поднимать живую топологию и не ломаться при повторном запуске."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from itms.cli import seed_demo
from itms.core.db import session_scope
from itms.models.catalog import DeviceModel, Manufacturer
from itms.models.datacenter import Rack, RackMount
from itms.models.diagram import Diagram
from itms.models.network import Connection, Device, Interface, Prefix
from itms.models.power import (
    PowerFeed,
    PowerLink,
    PowerNode,
    PowerScenario,
    PowerScenarioItem,
)
from itms.models.projects import Project, Task, TaskDependency
from itms.services import network_service, power_service

pytestmark = pytest.mark.anyio


async def test_seed_demo_builds_network_topology() -> None:
    await seed_demo()
    await seed_demo()

    async with session_scope() as session:

        async def count(model: type) -> int:
            return (await session.execute(select(func.count()).select_from(model))).scalar_one()

        assert await count(Manufacturer) == 3
        assert await count(DeviceModel) == 3
        assert await count(Device) == 5
        assert await count(Connection) == 4
        assert await count(Prefix) == 3
        assert await count(Diagram) == 1
        assert await count(Rack) == 1
        assert await count(RackMount) == 4
        assert await count(Project) == 1
        assert await count(Task) == 6
        assert await count(TaskDependency) == 5
        assert await count(PowerNode) == 11
        assert await count(PowerLink) == 9
        assert await count(PowerFeed) == 2
        assert await count(PowerScenario) == 1
        assert await count(PowerScenarioItem) == 3

        view = await power_service.overview(session)
        inlet = next(row for row in view["nodes"] if row["code"] == "IN-1")
        assert inlet["inlet_w"] > 16800
        assert inlet["headroom_w"] is not None
        assert inlet["headroom_w"] > 0
        forecast = view["scenarios"][0]["forecast"]
        assert forecast["added_estimated_w"] == 3475
        assert forecast["ups_loss_w"] == 222
        assert forecast["target_estimated_w"] > 20000
        assert forecast["deficit_w"] > 0
        server_psu = next(row for row in view["nodes"] if row["code"] == "PSU-A")
        switch_psu = next(row for row in view["nodes"] if row["code"] == "PSU-SW")
        assert server_psu["failover"] == "RESILIENT"
        assert switch_psu["failover"] == "SINGLE_FEED"

        start = (
            await session.execute(select(Interface.id).where(Interface.name == "eth1"))
        ).scalar_one()
        path = await network_service.trace(session, start)
        assert path["passed_through"]
        assert path["endpoint"] is not None
        assert path["endpoint"]["interface_name"] == "ether1"
