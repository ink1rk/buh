"""Atomic task transitions, approvals, reminders, and spend limits."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contracts.models import (
    AgentProfile,
    Approval,
    AuditEvent,
    Base,
    Message,
    OAuthConnection,
    OutboxEvent,
    ScheduledTrigger,
    Task,
    TaskStep,
    TelegramUpdateRow,
    UsageCost,
    User,
    utcnow,
)
from contracts.schemas import Actor, TaskState
from security.policy import payload_hash, token_hash

ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.created: {TaskState.queued, TaskState.cancelled},
    TaskState.queued: {TaskState.running, TaskState.cancelled, TaskState.failed},
    TaskState.running: {
        TaskState.waiting_approval,
        TaskState.waiting_external,
        TaskState.succeeded,
        TaskState.failed,
        TaskState.cancelled,
    },
    TaskState.waiting_approval: {TaskState.running, TaskState.cancelled, TaskState.failed},
    TaskState.waiting_external: {
        TaskState.running,
        TaskState.succeeded,
        TaskState.failed,
        TaskState.cancelled,
    },
    TaskState.failed: {TaskState.queued},
    TaskState.succeeded: set(),
    TaskState.cancelled: set(),
}

ACTORS: dict[tuple[TaskState, TaskState], set[Actor]] = {
    (TaskState.created, TaskState.queued): {Actor.gateway, Actor.orchestrator, Actor.owner},
    (TaskState.queued, TaskState.running): {Actor.orchestrator, Actor.worker},
    (TaskState.running, TaskState.waiting_approval): {Actor.orchestrator, Actor.worker},
    (TaskState.running, TaskState.waiting_external): {Actor.orchestrator, Actor.worker},
    (TaskState.running, TaskState.succeeded): {Actor.orchestrator, Actor.worker},
    (TaskState.running, TaskState.failed): {Actor.orchestrator, Actor.worker, Actor.system},
    (TaskState.running, TaskState.cancelled): {Actor.owner, Actor.orchestrator},
    (TaskState.waiting_approval, TaskState.running): {Actor.owner, Actor.orchestrator},
    (TaskState.waiting_approval, TaskState.cancelled): {Actor.owner, Actor.orchestrator},
    (TaskState.waiting_external, TaskState.running): {Actor.orchestrator, Actor.system},
    (TaskState.waiting_external, TaskState.succeeded): {Actor.orchestrator, Actor.worker},
    (TaskState.waiting_external, TaskState.failed): {Actor.orchestrator, Actor.system},
    (TaskState.failed, TaskState.queued): {Actor.orchestrator, Actor.owner},
    (TaskState.created, TaskState.cancelled): {Actor.owner, Actor.orchestrator},
    (TaskState.queued, TaskState.cancelled): {Actor.owner, Actor.orchestrator},
    (TaskState.queued, TaskState.failed): {Actor.system, Actor.orchestrator},
}

DEFAULT_PROFILES = (
    ("assistant", "assistant-fast"),
    ("researcher", "research-long"),
    ("planner", "reasoning-strong"),
    ("developer", "code-strong"),
    ("technical_expert", "critic-independent"),
)


class TransitionError(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class LoopLimit(Exception):
    pass


class Office:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.sessions = session_factory

    @classmethod
    def memory(cls) -> Office:
        from sqlalchemy import create_engine

        engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(engine)
        return cls(sessionmaker(bind=engine, expire_on_commit=False, future=True))

    def session(self) -> Session:
        return self.sessions()

    def ensure_owner(self, external_id: str, timezone_name: str = "UTC") -> User:
        with self.session() as db:
            user = db.scalar(select(User).where(User.external_id == external_id))
            if user is None:
                user = User(external_id=external_id, timezone=timezone_name)
                db.add(user)
                db.flush()
                for name, model in DEFAULT_PROFILES:
                    db.add(AgentProfile(owner_id=user.id, name=name, logical_model=model))
            db.commit()
            db.refresh(user)
            return user

    def ingest_update(self, *, update_id: int, owner_external_id: str, text: str) -> Task:
        """Duplicate Telegram updates return the original task and do not add a message."""
        owner = self.ensure_owner(owner_external_id)
        with self.session() as db:
            seen = db.get(TelegramUpdateRow, update_id)
            if seen is not None:
                task = db.get(Task, seen.task_id) if seen.task_id else None
                if task is None:
                    raise TransitionError("update already stored without a task")
                return task
            task = Task(
                owner_id=owner.id,
                correlation_id=secrets.token_hex(8),
                title=text[:240],
                state=TaskState.created.value,
                acl={"owner": "read,write"},
                idempotency_key=f"tg:{update_id}",
                budget_micros=1_000_000,
            )
            db.add(task)
            db.flush()
            db.add(
                TelegramUpdateRow(update_id=update_id, owner_id=owner.id, task_id=task.id)
            )
            db.add(
                Message(
                    owner_id=owner.id,
                    task_id=task.id,
                    correlation_id=task.correlation_id,
                    channel="telegram",
                    external_id=str(update_id),
                    role="user",
                    body=text,
                    acl={"owner": "read"},
                )
            )
            self._audit(db, owner.id, Actor.gateway, "ingest", f"task:{task.id}", task.correlation_id, "ok")
            db.commit()
            db.refresh(task)
            return task

    def transition(self, task_id: str, actor: Actor, to_state: TaskState) -> Task:
        with self.session() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise TransitionError("task missing")
            owner = db.get(User, task.owner_id)
            current = TaskState(task.state)
            if owner and owner.paused and to_state == TaskState.running and current == TaskState.queued:
                raise TransitionError("paused: new work is not assigned")
            if to_state not in ALLOWED[current]:
                raise TransitionError(f"{current.value} -> {to_state.value} is closed")
            if actor not in ACTORS.get((current, to_state), set()):
                raise TransitionError(f"{actor.value} cannot move {current.value} -> {to_state.value}")
            expected = task.version
            task.version = expected + 1
            task.state = to_state.value
            task.updated_at = utcnow()
            db.add(
                TaskStep(
                    task_id=task.id,
                    owner_id=task.owner_id,
                    correlation_id=task.correlation_id,
                    state=to_state.value,
                    actor=actor.value,
                    version=task.version,
                    detail={"from": current.value},
                )
            )
            db.add(
                OutboxEvent(
                    owner_id=task.owner_id,
                    correlation_id=task.correlation_id,
                    topic="task.transition",
                    payload={"task_id": task.id, "to": to_state.value, "version": task.version},
                    idempotency_key=f"transition:{task.id}:{task.version}",
                )
            )
            db.commit()
            db.refresh(task)
            return task

    def issue_approval(self, task_id: str, action: str, payload: dict, ttl_seconds: int = 900) -> str:
        raw = secrets.token_urlsafe(24)
        with self.session() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise TransitionError("task missing")
            approval = Approval(
                owner_id=task.owner_id,
                task_id=task.id,
                correlation_id=task.correlation_id,
                action=action,
                payload_hash=payload_hash(payload),
                token_hash=token_hash(raw),
                expires_at=utcnow() + timedelta(seconds=ttl_seconds),
                acl={"owner": "consume"},
            )
            db.add(approval)
            db.commit()
        return raw

    def consume_approval(self, raw_token: str, *, owner_id: str, task_id: str, action: str, payload: dict) -> Approval:
        now = utcnow()
        with self.session() as db:
            approval = db.scalar(select(Approval).where(Approval.token_hash == token_hash(raw_token)))
            if approval is None:
                raise TransitionError("approval token unknown")
            if approval.state != "pending" or approval.consumed_at is not None:
                raise TransitionError("approval token already used")
            expires = approval.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                raise TransitionError("approval token expired")
            if approval.owner_id != owner_id or approval.task_id != task_id or approval.action != action:
                raise TransitionError("approval token is bound to another action")
            if approval.payload_hash != payload_hash(payload):
                raise TransitionError("approval payload mismatch")
            approval.state = "consumed"
            approval.consumed_at = now
            approval.version += 1
            self._audit(db, owner_id, Actor.owner, "approve", f"approval:{approval.id}", approval.correlation_id, "ok")
            db.commit()
            db.refresh(approval)
            return approval

    def charge(self, task_id: str, micros: int, logical_model: str, reason: str) -> Task:
        if micros < 0:
            raise TransitionError("negative spend")
        with self.session() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise TransitionError("task missing")
            if task.spent_micros + micros > task.budget_micros:
                task.state = TaskState.failed.value
                task.version += 1
                db.add(
                    UsageCost(
                        owner_id=task.owner_id,
                        task_id=task.id,
                        correlation_id=task.correlation_id,
                        logical_model=logical_model,
                        micros=0,
                        reason="budget-exceeded",
                    )
                )
                db.commit()
                raise BudgetExceeded(task.id)
            task.spent_micros += micros
            task.version += 1
            db.add(
                UsageCost(
                    owner_id=task.owner_id,
                    task_id=task.id,
                    correlation_id=task.correlation_id,
                    logical_model=logical_model,
                    micros=micros,
                    reason=reason,
                )
            )
            db.commit()
            db.refresh(task)
            return task

    def note_turn(self, task_id: str) -> Task:
        with self.session() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise TransitionError("task missing")
            task.turn_count += 1
            if task.turn_count > task.max_turns:
                task.state = TaskState.waiting_approval.value
                task.version += 1
                db.commit()
                raise LoopLimit(task.id)
            if task.deadline_at is not None:
                deadline = task.deadline_at
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                if utcnow() > deadline:
                    task.state = TaskState.failed.value
                    task.version += 1
                    db.commit()
                    raise LoopLimit(task.id)
            db.commit()
            db.refresh(task)
            return task

    def pause(self, owner_id: str) -> None:
        self._set_paused(owner_id, True)

    def resume(self, owner_id: str) -> None:
        self._set_paused(owner_id, False)

    def stop_all(self, owner_id: str) -> int:
        """Stop assigning work and cancel queued or running tasks. In-flight side effects may remain."""
        with self.session() as db:
            user = db.get(User, owner_id)
            if user is None:
                raise TransitionError("owner missing")
            user.paused = True
            tasks = db.scalars(select(Task).where(Task.owner_id == owner_id)).all()
            changed = 0
            for task in tasks:
                if task.state in {TaskState.queued.value, TaskState.running.value, TaskState.created.value}:
                    task.state = TaskState.cancelled.value
                    task.version += 1
                    changed += 1
            pending = db.scalars(
                select(Approval).where(Approval.owner_id == owner_id, Approval.state == "pending")
            ).all()
            for approval in pending:
                approval.state = "revoked"
                approval.version += 1
            db.commit()
            return changed

    def schedule_reminder(
        self,
        *,
        owner_id: str,
        local_date: str,
        local_time: str,
        timezone_name: str,
        dedupe_key: str,
    ) -> ScheduledTrigger:
        due = first_utc(local_date, local_time, timezone_name)
        with self.session() as db:
            existing = db.scalar(select(ScheduledTrigger).where(ScheduledTrigger.dedupe_key == dedupe_key))
            if existing is not None:
                return existing
            row = ScheduledTrigger(
                owner_id=owner_id,
                correlation_id=secrets.token_hex(8),
                timezone=timezone_name,
                local_date=local_date,
                local_time=local_time,
                due_at_utc=due,
                dedupe_key=dedupe_key,
                acl={"owner": "read"},
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

    def catch_up_reminders(self, now: datetime | None = None) -> list[str]:
        moment = now or utcnow()
        delivered: list[str] = []
        with self.session() as db:
            rows = db.scalars(
                select(ScheduledTrigger).where(ScheduledTrigger.state == "pending")
            ).all()
            for row in rows:
                due = row.due_at_utc
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if due <= moment:
                    row.state = "delivered"
                    row.attempts += 1
                    row.version += 1
                    delivered.append(row.id)
            db.commit()
        return delivered

    def store_refresh_token(self, owner_id: str, provider: str, ciphertext: str, scopes: list[str]) -> None:
        if not ciphertext.startswith("enc:v1:"):
            raise TransitionError("refresh token must already be encrypted")
        with self.session() as db:
            db.add(
                OAuthConnection(
                    owner_id=owner_id,
                    provider=provider,
                    scopes=scopes,
                    refresh_token_ciphertext=ciphertext,
                )
            )
            db.commit()

    def _set_paused(self, owner_id: str, paused: bool) -> None:
        with self.session() as db:
            user = db.get(User, owner_id)
            if user is None:
                raise TransitionError("owner missing")
            user.paused = paused
            db.commit()

    def _audit(self, db: Session, owner_id: str, actor: Actor, action: str, resource: str, correlation_id: str, result: str) -> None:
        db.add(
            AuditEvent(
                owner_id=owner_id,
                actor=actor.value,
                action=action,
                resource=resource,
                correlation_id=correlation_id,
                result=result,
                detail={},
            )
        )


def first_utc(local_date: str, local_time: str, timezone_name: str) -> datetime:
    """First real instant for a civil time. Missing DST hour shifts forward; the fold fires once."""
    zone = ZoneInfo(timezone_name)
    year, month, day = (int(part) for part in local_date.split("-"))
    hour, minute = (int(part) for part in local_time.split(":"))
    naive = datetime(year, month, day, hour, minute)
    first = naive.replace(tzinfo=zone, fold=0)
    # A spring-forward gap repeats the previous offset and compares unequal to the wall time.
    back = first.astimezone(timezone.utc).astimezone(zone)
    if (back.hour, back.minute) != (hour, minute):
        shifted = first + timedelta(hours=1)
        return shifted.astimezone(timezone.utc)
    return first.astimezone(timezone.utc)
