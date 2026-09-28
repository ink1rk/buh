from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from itms.api.schemas.common import ORMModel


class FinanceWrite(BaseModel):
    department_id: uuid.UUID | None = None
    kind: str
    direction: str
    period: date
    article: str = Field(min_length=1, max_length=255)
    planned: Decimal = Field(default=0)
    actual: Decimal = Field(default=0)
    notes: str | None = None


class FinanceUpdate(BaseModel):
    department_id: uuid.UUID | None = None
    kind: str | None = None
    direction: str | None = None
    period: date | None = None
    article: str | None = None
    planned: Decimal | None = None
    actual: Decimal | None = None
    notes: str | None = None


class FinanceRead(ORMModel):
    id: uuid.UUID
    department_id: uuid.UUID | None
    kind: str
    direction: str
    period: date
    article: str
    planned: Decimal
    actual: Decimal
    notes: str | None
