"""Демо-набор должен поднимать живую топологию и не ломаться при повторном запуске."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from itms.cli import seed_demo
from itms.core.db import session_scope
from itms.models.catalog import DeviceModel, Manufacturer
from itms.models.datacenter import Rack, RackMount
from itms.models.diagram import Diagram
from itms.models.floorplan import Floorplan, FloorplanItem
from itms.models.network import Connection, Device, Interface, Prefix
from itms.models.power import (
    PowerFeed,
    PowerLink,
    PowerNode,
    PowerScenario,
    PowerScenarioItem,
)
from itms.models.projects import Project, Task, TaskDependency
from itms.models.transition import ChangeItem, PlannedChange, StateSnapshot
from itms.services import diagram_service, network_service, power_service, project_service

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
        assert await count(Diagram) == 2
        assert await count(Floorplan) == 1
        assert await count(FloorplanItem) == 2
        power_diagram = (
            await session.execute(select(Diagram).where(Diagram.name == "Питание серверной"))
        ).scalar_one()
        drawn = await diagram_service.full_diagram(session, power_diagram.id)
        inlet_node = next(node for node in drawn["nodes"] if node["code"] == "IN-1")
        load_node = next(node for node in drawn["nodes"] if node["code"] == "GL-1")
        assert inlet_node["y"] < load_node["y"]
        assert inlet_node["inlet_w"] > 16800
        assert any(edge["power_link_id"] for edge in drawn["edges"])
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
        assert await count(StateSnapshot) == 1
        assert await count(PlannedChange) == 1
        assert await count(ChangeItem) == 8

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

        project = (await session.execute(select(Project).where(Project.key == "PWR"))).scalar_one()
        passport = await project_service.project_view(session, project.id)
        assert passport["health"]["status"] == "AT_RISK"
        assert any(item["rule"] == "power_deficit" for item in passport["health"]["findings"])
        plan = (
            await session.execute(
                select(PlannedChange).where(PlannedChange.project_id == project.id)
            )
        ).scalar_one()
        assert plan.status == "DRAFT"

        start = (
            await session.execute(select(Interface.id).where(Interface.name == "eth1"))
        ).scalar_one()
        path = await network_service.trace(session, start)
        assert path["passed_through"]
        assert path["endpoint"] is not None
        assert path["endpoint"]["interface_name"] == "ether1"
