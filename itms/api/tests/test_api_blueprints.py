"""Шаблоны платформ не расширяют перечень типов и не делают vCenter хостом."""

from __future__ import annotations

from httpx import AsyncClient

from itms.domain.platform_blueprints import LINKS, NODES


async def test_platform_blueprints_are_idempotent(client: AsyncClient, api: str) -> None:
    first = await client.post(f"{api}/catalog/blueprints")
    assert first.status_code == 200, first.text
    created = first.json()
    assert created["nodes_created"] == len(NODES)
    assert created["links_created"] == len(LINKS)

    vcenter = await client.get(f"{api}/ci", params={"q": "TPL-VCENTER", "limit": 5})
    assert vcenter.status_code == 200, vcenter.text
    item = vcenter.json()["items"][0]
    assert item["ci_type"] == "APPLICATION"
    assert item["code"] == "TPL-VCENTER"
    assert item["status"] == "PLANNED"
    related = await client.get(f"{api}/ci/{item['id']}/related")
    assert related.status_code == 200, related.text
    manages = [
        row
        for group in related.json().values()
        if isinstance(group, list)
        for row in group
        if isinstance(row, dict)
        and row.get("rel_type") == "MANAGES"
        and row.get("direction") == "outgoing"
    ]
    assert manages and manages[0]["ci"]["code"] == "TPL-ESXI"

    hosts = await client.get(f"{api}/virtualization")
    assert hosts.status_code == 200, hosts.text
    assert hosts.json()["hosts"] == []

    second = await client.post(f"{api}/catalog/blueprints")
    assert second.status_code == 200, second.text
    again = second.json()
    assert again["nodes_created"] == 0
    assert again["links_created"] == 0
    assert again["nodes_skipped"] == len(NODES)
    assert again["links_skipped"] == len(LINKS)
