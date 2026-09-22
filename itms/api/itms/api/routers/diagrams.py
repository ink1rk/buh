from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok
from itms.api.schemas.diagrams import (
    DiagramCreate,
    DiagramEdgeRead,
    DiagramFull,
    DiagramNodeRead,
    DiagramRead,
    DiagramUpdate,
    LayoutWrite,
    NodeCreate,
)
from itms.domain.permissions import Permission
from itms.services import diagram_service

router = APIRouter(prefix="/diagrams", tags=["diagrams"])


@router.get("", response_model=list[DiagramRead], dependencies=[requires(Permission.CI_READ)])
async def list_diagrams(session: SessionDep) -> list[DiagramRead]:
    rows = await diagram_service.list_diagrams(session)
    return [DiagramRead.model_validate(item) for item in rows]


@router.post("", response_model=DiagramRead, status_code=201,
             dependencies=[requires(Permission.CI_WRITE)])
async def create_diagram(payload: DiagramCreate, session: SessionDep) -> DiagramRead:
    diagram = await diagram_service.create_diagram(session, payload.model_dump())
    return DiagramRead.model_validate(diagram)


@router.get("/{diagram_id}", response_model=DiagramFull,
            dependencies=[requires(Permission.CI_READ)])
async def get_diagram(diagram_id: uuid.UUID, session: SessionDep) -> DiagramFull:
    """Узлы, рёбра и актуальные свойства объектов одним ответом."""
    payload = await diagram_service.full_diagram(session, diagram_id)
    return DiagramFull(
        diagram=DiagramRead.model_validate(payload["diagram"]),
        nodes=[DiagramNodeRead.model_validate(node) for node in payload["nodes"]],
        edges=[DiagramEdgeRead.model_validate(edge) for edge in payload["edges"]],
    )


@router.patch("/{diagram_id}", response_model=DiagramRead,
              dependencies=[requires(Permission.CI_WRITE)])
async def update_diagram(
    diagram_id: uuid.UUID, payload: DiagramUpdate, session: SessionDep
) -> DiagramRead:
    diagram = await diagram_service.update_diagram(
        session, diagram_id, payload.model_dump(exclude_unset=True)
    )
    return DiagramRead.model_validate(diagram)


@router.delete("/{diagram_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)])
async def delete_diagram(diagram_id: uuid.UUID, session: SessionDep) -> Ok:
    await diagram_service.delete_diagram(session, diagram_id)
    return Ok()


@router.patch("/{diagram_id}/layout", response_model=DiagramRead,
              dependencies=[requires(Permission.CI_WRITE)])
async def save_layout(
    diagram_id: uuid.UUID, payload: LayoutWrite, session: SessionDep
) -> DiagramRead:
    diagram = await diagram_service.save_layout(
        session,
        diagram_id,
        payload.version,
        [node.model_dump() for node in payload.nodes],
        payload.viewport,
    )
    return DiagramRead.model_validate(diagram)


@router.post("/{diagram_id}/nodes", response_model=DiagramNodeRead, status_code=201,
             dependencies=[requires(Permission.CI_WRITE)])
async def add_node(
    diagram_id: uuid.UUID, payload: NodeCreate, session: SessionDep
) -> DiagramNodeRead:
    await diagram_service.add_node(session, diagram_id, payload.ci_id)
    full = await diagram_service.full_diagram(session, diagram_id)
    match = next(node for node in full["nodes"] if node["ci_id"] == payload.ci_id)
    return DiagramNodeRead.model_validate(match)


@router.delete("/nodes/{node_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)])
async def remove_node(node_id: uuid.UUID, session: SessionDep) -> Ok:
    await diagram_service.remove_node(session, node_id)
    return Ok()


@router.post("/{diagram_id}/sync", response_model=DiagramFull,
             dependencies=[requires(Permission.CI_WRITE)])
async def sync_edges(diagram_id: uuid.UUID, session: SessionDep) -> DiagramFull:
    """Подтягивает новые кабели и связи между объектами, которые уже на схеме."""
    diagram = await diagram_service.get_diagram(session, diagram_id)
    await diagram_service.sync_edges(session, diagram)
    payload = await diagram_service.full_diagram(session, diagram_id)
    return DiagramFull(
        diagram=DiagramRead.model_validate(payload["diagram"]),
        nodes=[DiagramNodeRead.model_validate(node) for node in payload["nodes"]],
        edges=[DiagramEdgeRead.model_validate(edge) for edge in payload["edges"]],
    )


@router.post("/{diagram_id}/autolayout", response_model=DiagramFull,
             dependencies=[requires(Permission.CI_WRITE)])
async def autolayout(diagram_id: uuid.UUID, session: SessionDep) -> DiagramFull:
    diagram = await diagram_service.get_diagram(session, diagram_id)
    await diagram_service.autolayout(session, diagram)
    payload = await diagram_service.full_diagram(session, diagram_id)
    return DiagramFull(
        diagram=DiagramRead.model_validate(payload["diagram"]),
        nodes=[DiagramNodeRead.model_validate(node) for node in payload["nodes"]],
        edges=[DiagramEdgeRead.model_validate(edge) for edge in payload["edges"]],
    )
