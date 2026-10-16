"""Calendar and mail side effects go through an idempotent broker."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contracts.models import AuditEvent, Base, ToolCall
from orchestrator.service import Office, TransitionError
from security.policy import authorize_tool


class SideEffect:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def perform(self, tool: str, payload: dict) -> dict:
        self.calls.append({"tool": tool, "payload": payload})
        return {"ok": True, "echo": payload}


class Broker:
    def __init__(self, office: Office, effects: SideEffect | None = None):
        self.office = office
        self.effects = effects or SideEffect()

    def call(
        self,
        *,
        task_id: str,
        owner_id: str,
        tool: str,
        payload: dict,
        idempotency_key: str,
        approval_token: str | None = None,
        untrusted_text: str | None = None,
    ) -> dict:
        with self.office.session() as db:
            existing = db.scalar(select(ToolCall).where(ToolCall.idempotency_key == idempotency_key))
            if existing is not None:
                return existing.result
        decision = authorize_tool(
            tool,
            has_approval=approval_token is not None,
            untrusted_text=untrusted_text,
        )
        if not decision.allowed:
            self._audit(owner_id, tool, task_id, "denied", decision.reason)
            raise TransitionError(decision.reason)
        if approval_token:
            self.office.consume_approval(
                approval_token,
                owner_id=owner_id,
                task_id=task_id,
                action=tool,
                payload=payload,
            )
        with self.office.session() as db:
            result = self.effects.perform(tool, payload)
            task_correlation = task_id
            db.add(
                ToolCall(
                    owner_id=owner_id,
                    task_id=task_id,
                    correlation_id=task_correlation,
                    tool=tool,
                    state="succeeded",
                    idempotency_key=idempotency_key,
                    request={"tool": tool},
                    result=result,
                    acl={"owner": "read"},
                )
            )
            db.add(
                AuditEvent(
                    owner_id=owner_id,
                    actor="tool-broker",
                    action=tool,
                    resource=f"task:{task_id}",
                    correlation_id=task_correlation,
                    result="ok",
                    detail={"idempotency_key": idempotency_key},
                )
            )
            db.commit()
            return result

    def read_calendar(self, *, task_id: str, owner_id: str, idempotency_key: str) -> dict:
        return self.call(
            task_id=task_id,
            owner_id=owner_id,
            tool="calendar.read",
            payload={"mode": "read"},
            idempotency_key=idempotency_key,
        )

    def _audit(self, owner_id: str, tool: str, task_id: str, result: str, reason: str) -> None:
        with self.office.session() as db:
            db.add(
                AuditEvent(
                    owner_id=owner_id,
                    actor="tool-broker",
                    action=tool,
                    resource=f"task:{task_id}",
                    correlation_id=task_id,
                    result=result,
                    detail={"reason": reason},
                )
            )
            db.commit()


def session_factory_from(office: Office) -> sessionmaker[Session]:
    return office.sessions


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)
