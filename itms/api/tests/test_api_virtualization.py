from __future__ import annotations

from urllib.parse import quote

from httpx import AsyncClient


async def _host(client: AsyncClient, api: str, **extra: object) -> dict:
    body = {
        "name": "pve-1",
        "code": "PVE-1",
        "ci_type": "CLUSTER",
        "platform": "PROXMOX",
        "cpu_cores": 8,
        "memory_mb": 16384,
        "storage_gb": 500,
    }
    body.update(extra)
    response = await client.post(f"{api}/virtualization/hosts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _by_code(rows: list[dict], code: str) -> dict:
    return next(row for row in rows if row["code"] == code)


async def test_vm_resources_and_overcommit(client: AsyncClient, api: str) -> None:
    created = await _host(client, api)
    host_id = _by_code(created["hosts"], "PVE-1")["id"]

    running = await client.post(
        f"{api}/virtualization/vms",
        json={
            "name": "app",
            "code": "VM-APP",
            "host_id": host_id,
            "vcpu": 4,
            "memory_mb": 8192,
            "disk_gb": 100,
            "guest_os": "Ubuntu 24.04",
            "power_state": "RUNNING",
        },
    )
    assert running.status_code == 201, running.text
    stopped = await client.post(
        f"{api}/virtualization/vms",
        json={
            "name": "cold",
            "code": "VM-COLD",
            "host_id": host_id,
            "vcpu": 8,
            "memory_mb": 16384,
            "disk_gb": 200,
            "power_state": "STOPPED",
        },
    )
    assert stopped.status_code == 201, stopped.text
    payload = stopped.json()
    host = _by_code(payload["hosts"], "PVE-1")
    assert host["vcpu_running"] == 4
    assert host["memory_running_mb"] == 8192
    assert host["vcpu_allocated"] == 12
    assert host["disk_allocated_gb"] == 300
    assert host["vm_count"] == 2
    assert host["vm_running"] == 1
    assert payload["totals"]["disk_allocated_gb"] == 300

    vm_id = _by_code(payload["vms"], "VM-APP")["id"]
    silent = await client.patch(f"{api}/virtualization/vms/{vm_id}", json={"vcpu": 16})
    assert silent.status_code == 422
    assert silent.json()["error"]["code"] == "provenance_required"

    grown = await client.patch(
        f"{api}/virtualization/vms/{vm_id}",
        json={"vcpu": 16},
        headers={"X-Reason": quote("гостю нужно больше ядер")},
    )
    assert grown.status_code == 200, grown.text
    host = _by_code(grown.json()["hosts"], "PVE-1")
    assert host["vcpu_running"] == 16
    assert host["cpu_cores"] == 8

    related = await client.get(f"{api}/ci/{vm_id}/related")
    hosting = related.json()["hosting"]
    assert hosting[0]["rel_type"] == "RUNS_ON"
    assert hosting[0]["direction"] == "outgoing"
    assert hosting[0]["ci"]["id"] == host_id


async def test_host_move_clears_previous_relation(client: AsyncClient, api: str) -> None:
    first = await _host(client, api, name="узел а", code="H-A")
    second = await _host(client, api, name="узел б", code="H-B", cpu_cores=4)
    left = _by_code(first["hosts"], "H-A")["id"]
    right = _by_code(second["hosts"], "H-B")["id"]
    created = await client.post(
        f"{api}/virtualization/vms",
        json={"name": "guest", "code": "VM-MOVE", "host_id": left, "vcpu": 1, "memory_mb": 512},
    )
    vm_id = _by_code(created.json()["vms"], "VM-MOVE")["id"]
    moved = await client.patch(
        f"{api}/virtualization/vms/{vm_id}",
        json={"host_id": right},
        headers={"X-Reason": quote("перенос на другой узел")},
    )
    assert moved.status_code == 200, moved.text
    assert _by_code(moved.json()["vms"], "VM-MOVE")["host_id"] == right
    related = await client.get(f"{api}/ci/{vm_id}/related")
    targets = [item["ci"]["id"] for item in related.json()["hosting"]]
    assert targets == [right]

    cleared = await client.patch(
        f"{api}/virtualization/vms/{vm_id}",
        json={"host_id": None},
        headers={"X-Reason": quote("снята с хоста")},
    )
    assert cleared.status_code == 200, cleared.text
    assert _by_code(cleared.json()["vms"], "VM-MOVE")["host_id"] is None
    assert (await client.get(f"{api}/ci/{vm_id}/related")).json().get("hosting", []) == []


async def test_host_profile_rules(client: AsyncClient, api: str) -> None:
    service = await client.post(f"{api}/ci", json={"ci_type": "SERVICE", "name": "биллинг"})
    rejected = await client.post(
        f"{api}/virtualization/hosts",
        json={
            "ci_id": service.json()["id"],
            "cpu_cores": 2,
            "memory_mb": 1024,
            "storage_gb": 10,
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"]["code_hint"] == "not_a_host"

    device = await client.post(
        f"{api}/ci", json={"ci_type": "DEVICE", "name": "SRV-HV", "code": "SRV-HV"}
    )
    attached = await client.post(
        f"{api}/virtualization/hosts",
        json={
            "ci_id": device.json()["id"],
            "platform": "KVM",
            "cpu_cores": 16,
            "memory_mb": 65536,
            "storage_gb": 2000,
        },
    )
    assert attached.status_code == 201, attached.text
    host = _by_code(attached.json()["hosts"], "SRV-HV")
    assert host["platform"] == "KVM"
    assert host["ci_type"] == "DEVICE"
    again = await client.post(
        f"{api}/virtualization/hosts",
        json={"ci_id": device.json()["id"], "cpu_cores": 1, "memory_mb": 1, "storage_gb": 1},
    )
    assert again.status_code == 409


async def test_archived_vm_drops_out_of_usage(client: AsyncClient, api: str) -> None:
    created = await _host(
        client, api, name="полка", code="H-ARC", cpu_cores=4, memory_mb=4096, storage_gb=100
    )
    host_id = _by_code(created["hosts"], "H-ARC")["id"]
    vm = await client.post(
        f"{api}/virtualization/vms",
        json={
            "name": "временная",
            "code": "VM-ARC",
            "host_id": host_id,
            "vcpu": 2,
            "memory_mb": 2048,
            "disk_gb": 40,
        },
    )
    vm_id = _by_code(vm.json()["vms"], "VM-ARC")["id"]
    archived = await client.post(f"{api}/ci/{vm_id}/archive")
    assert archived.status_code == 200, archived.text
    overview = await client.get(f"{api}/virtualization")
    assert overview.status_code == 200
    body = overview.json()
    assert all(row["code"] != "VM-ARC" for row in body["vms"])
    host = _by_code(body["hosts"], "H-ARC")
    assert host["vm_count"] == 0
    assert host["disk_allocated_gb"] == 0
