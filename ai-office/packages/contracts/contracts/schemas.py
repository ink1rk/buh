"""Pydantic contracts shared by gateway, orchestrator, and workers."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    created = "created"
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    waiting_external = "waiting_external"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class Actor(str, Enum):
    owner = "owner"
    gateway = "gateway"
    orchestrator = "orchestrator"
    worker = "worker"
    launcher = "launcher"
    system = "system"


class LogicalModel(str, Enum):
    assistant_fast = "assistant-fast"
    reasoning_strong = "reasoning-strong"
    research_long = "research-long"
    code_strong = "code-strong"
    critic_independent = "critic-independent"


class TelegramUpdate(BaseModel):
    update_id: int
    owner_external_id: str
    chat_id: str
    text: str = ""
    received_at: datetime | None = None


class TaskView(BaseModel):
    id: str
    owner_id: str
    state: TaskState
    title: str
    correlation_id: str
    schema_version: int = 1
    version: int
    idempotency_key: str | None = None


class ApprovalRequest(BaseModel):
    task_id: str
    owner_id: str
    action: str
    payload: dict[str, Any]
    ttl_seconds: int = Field(default=900, ge=30, le=86400)


class ToolRequest(BaseModel):
    task_id: str
    owner_id: str
    tool: str
    payload: dict[str, Any]
    idempotency_key: str
    approval_token: str | None = None
    untrusted_text: str | None = None
