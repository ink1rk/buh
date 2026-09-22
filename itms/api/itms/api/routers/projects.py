from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.projects import (
    CheckCreate,
    CheckUpdate,
    CiLink,
    CommentCreate,
    DependencyCreate,
    InboxItem,
    MemberWrite,
    MilestoneCreate,
    MilestoneUpdate,
    PhaseCreate,
    PhaseUpdate,
    ProjectCreate,
    ProjectSummary,
    ProjectUpdate,
    ProjectView,
    ScheduleView,
    TaskCiLink,
    TaskCreate,
    TaskUpdate,
    TaskWork,
    TimeEntryCreate,
)
from itms.api.schemas.transition import SnapshotCreate, SnapshotRead, TransitionView
from itms.domain.permissions import Permission
from itms.services import project_service, transition_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary], dependencies=[requires(Permission.CI_READ)])
async def list_projects(session: SessionDep) -> list[ProjectSummary]:
    rows = await project_service.list_projects(session)
    return [ProjectSummary.model_validate(row) for row in rows]


@router.get("/inbox", response_model=list[InboxItem], dependencies=[requires(Permission.CI_READ)])
async def inbox(session: SessionDep) -> list[InboxItem]:
    rows = await project_service.inbox(session)
    return [InboxItem.model_validate(row) for row in rows]


@router.post(
    "", response_model=ProjectView, status_code=201, dependencies=[requires(Permission.CI_WRITE)]
)
async def create_project(payload: ProjectCreate, session: SessionDep) -> ProjectView:
    view = await project_service.create_project(session, payload.model_dump())
    return ProjectView.model_validate(view)


@router.get(
    "/{project_id}", response_model=ProjectView, dependencies=[requires(Permission.CI_READ)]
)
async def get_project(project_id: uuid.UUID, session: SessionDep) -> ProjectView:
    return ProjectView.model_validate(await project_service.project_view(session, project_id))


@router.get(
    "/{project_id}/schedule",
    response_model=ScheduleView,
    dependencies=[requires(Permission.CI_READ)],
)
async def get_schedule(project_id: uuid.UUID, session: SessionDep) -> ScheduleView:
    return ScheduleView.model_validate(await project_service.schedule(session, project_id))


@router.patch(
    "/{project_id}", response_model=ProjectView, dependencies=[requires(Permission.CI_WRITE)]
)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, session: SessionDep
) -> ProjectView:
    view = await project_service.update_project(
        session, project_id, payload.model_dump(exclude_unset=True)
    )
    return ProjectView.model_validate(view)


@router.post(
    "/{project_id}/phases",
    response_model=ProjectView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_phase(
    project_id: uuid.UUID, payload: PhaseCreate, session: SessionDep
) -> ProjectView:
    view = await project_service.add_phase(session, project_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.patch(
    "/{project_id}/phases/{phase_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_phase(
    project_id: uuid.UUID, phase_id: uuid.UUID, payload: PhaseUpdate, session: SessionDep
) -> ProjectView:
    view = await project_service.update_phase(
        session, project_id, phase_id, payload.model_dump(exclude_unset=True)
    )
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/phases/{phase_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def delete_phase(
    project_id: uuid.UUID, phase_id: uuid.UUID, session: SessionDep
) -> ProjectView:
    return ProjectView.model_validate(
        await project_service.delete_phase(session, project_id, phase_id)
    )


@router.post(
    "/{project_id}/milestones",
    response_model=ProjectView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_milestone(
    project_id: uuid.UUID, payload: MilestoneCreate, session: SessionDep
) -> ProjectView:
    view = await project_service.add_milestone(session, project_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.patch(
    "/{project_id}/milestones/{milestone_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
    session: SessionDep,
) -> ProjectView:
    view = await project_service.update_milestone(
        session, project_id, milestone_id, payload.model_dump(exclude_unset=True)
    )
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/milestones/{milestone_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def delete_milestone(
    project_id: uuid.UUID, milestone_id: uuid.UUID, session: SessionDep
) -> ProjectView:
    return ProjectView.model_validate(
        await project_service.delete_milestone(session, project_id, milestone_id)
    )


@router.post(
    "/{project_id}/tasks",
    response_model=ProjectView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_task(project_id: uuid.UUID, payload: TaskCreate, session: SessionDep) -> ProjectView:
    view = await project_service.add_task(session, project_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.get(
    "/{project_id}/tasks/{task_id}/work",
    response_model=TaskWork,
    dependencies=[requires(Permission.CI_READ)],
)
async def task_work(project_id: uuid.UUID, task_id: uuid.UUID, session: SessionDep) -> TaskWork:
    return TaskWork.model_validate(await project_service.task_work(session, project_id, task_id))


@router.post(
    "/{project_id}/tasks/{task_id}/comments",
    response_model=TaskWork,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_comment(
    project_id: uuid.UUID, task_id: uuid.UUID, payload: CommentCreate, session: SessionDep
) -> TaskWork:
    view = await project_service.add_comment(session, project_id, task_id, payload.body)
    return TaskWork.model_validate(view)


@router.post(
    "/{project_id}/tasks/{task_id}/checks",
    response_model=TaskWork,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_check(
    project_id: uuid.UUID, task_id: uuid.UUID, payload: CheckCreate, session: SessionDep
) -> TaskWork:
    view = await project_service.add_check(session, project_id, task_id, payload.title)
    return TaskWork.model_validate(view)


@router.patch(
    "/{project_id}/tasks/{task_id}/checks/{check_id}",
    response_model=TaskWork,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_check(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    check_id: uuid.UUID,
    payload: CheckUpdate,
    session: SessionDep,
) -> TaskWork:
    view = await project_service.update_check(session, project_id, task_id, check_id, payload.done)
    return TaskWork.model_validate(view)


@router.patch(
    "/{project_id}/tasks/{task_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_task(
    project_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdate, session: SessionDep
) -> ProjectView:
    view = await project_service.update_task(
        session, project_id, task_id, payload.model_dump(exclude_unset=True)
    )
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/tasks/{task_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def delete_task(
    project_id: uuid.UUID, task_id: uuid.UUID, session: SessionDep
) -> ProjectView:
    return ProjectView.model_validate(
        await project_service.delete_task(session, project_id, task_id)
    )


@router.post(
    "/{project_id}/dependencies",
    response_model=ProjectView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_dependency(
    project_id: uuid.UUID, payload: DependencyCreate, session: SessionDep
) -> ProjectView:
    view = await project_service.add_dependency(session, project_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/dependencies/{dependency_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def delete_dependency(
    project_id: uuid.UUID, dependency_id: uuid.UUID, session: SessionDep
) -> ProjectView:
    return ProjectView.model_validate(
        await project_service.delete_dependency(session, project_id, dependency_id)
    )


@router.post(
    "/{project_id}/ci", response_model=ProjectView, dependencies=[requires(Permission.CI_WRITE)]
)
async def link_ci(project_id: uuid.UUID, payload: CiLink, session: SessionDep) -> ProjectView:
    view = await project_service.link_ci(session, project_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/ci/{ci_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def unlink_ci(project_id: uuid.UUID, ci_id: uuid.UUID, session: SessionDep) -> ProjectView:
    return ProjectView.model_validate(await project_service.unlink_ci(session, project_id, ci_id))


@router.post(
    "/{project_id}/tasks/{task_id}/ci",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def link_task_ci(
    project_id: uuid.UUID, task_id: uuid.UUID, payload: TaskCiLink, session: SessionDep
) -> ProjectView:
    view = await project_service.link_task_ci(session, project_id, task_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/tasks/{task_id}/ci/{ci_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def unlink_task_ci(
    project_id: uuid.UUID, task_id: uuid.UUID, ci_id: uuid.UUID, session: SessionDep
) -> ProjectView:
    return ProjectView.model_validate(
        await project_service.unlink_task_ci(session, project_id, task_id, ci_id)
    )


@router.post(
    "/{project_id}/members",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_member(
    project_id: uuid.UUID, payload: MemberWrite, session: SessionDep
) -> ProjectView:
    view = await project_service.add_member(session, project_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.delete(
    "/{project_id}/members/{employee_id}",
    response_model=ProjectView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def remove_member(
    project_id: uuid.UUID, employee_id: uuid.UUID, session: SessionDep
) -> ProjectView:
    return ProjectView.model_validate(
        await project_service.remove_member(session, project_id, employee_id)
    )


@router.post(
    "/{project_id}/tasks/{task_id}/time",
    response_model=ProjectView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def add_time(
    project_id: uuid.UUID, task_id: uuid.UUID, payload: TimeEntryCreate, session: SessionDep
) -> ProjectView:
    view = await project_service.add_time(session, project_id, task_id, payload.model_dump())
    return ProjectView.model_validate(view)


@router.get(
    "/{project_id}/transition",
    response_model=TransitionView,
    dependencies=[requires(Permission.CI_READ)],
)
async def get_transition(project_id: uuid.UUID, session: SessionDep) -> TransitionView:
    return TransitionView.model_validate(await transition_service.view(session, project_id))


@router.post(
    "/{project_id}/snapshots",
    response_model=SnapshotRead,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def take_snapshot(
    project_id: uuid.UUID, payload: SnapshotCreate, session: SessionDep
) -> SnapshotRead:
    row = await transition_service.take_snapshot(session, project_id, payload.name)
    return SnapshotRead.model_validate(row)


@router.post(
    "/{project_id}/plans",
    response_model=TransitionView,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def build_plan(project_id: uuid.UUID, session: SessionDep) -> TransitionView:
    return TransitionView.model_validate(await transition_service.build_plan(session, project_id))


@router.post(
    "/{project_id}/plans/{plan_id}/apply",
    response_model=TransitionView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def apply_plan(
    project_id: uuid.UUID, plan_id: uuid.UUID, session: SessionDep
) -> TransitionView:
    return TransitionView.model_validate(
        await transition_service.apply_plan(session, project_id, plan_id)
    )


@router.post(
    "/{project_id}/plans/{plan_id}/rollback",
    response_model=TransitionView,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def rollback_plan(
    project_id: uuid.UUID, plan_id: uuid.UUID, session: SessionDep
) -> TransitionView:
    return TransitionView.model_validate(
        await transition_service.rollback_plan(session, project_id, plan_id)
    )
