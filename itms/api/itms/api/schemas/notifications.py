from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationItem(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationItem]
