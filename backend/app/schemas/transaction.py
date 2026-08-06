from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TransactionCreate(BaseModel):
    amount: float
    category: str = "other"
    subcategory: str = ""
    description: str = ""
    merchant: str = ""
    account_id: int | None = None
    transaction_type: str = "expense"
    occurred_on: date | None = None
    tags: str = ""
    source: str = "manual"
    raw_input: str = ""
    currency: str = "RUB"


class TransactionUpdate(BaseModel):
    amount: float | None = None
    category: str | None = None
    description: str | None = None
    merchant: str | None = None
    account_id: int | None = None
    occurred_on: date | None = None
    tags: str | None = None


class TransactionOut(ORMModel):
    id: int
    amount: float
    currency: str
    category: str
    subcategory: str
    description: str
    merchant: str
    account_id: int | None
    transaction_type: str
    occurred_on: date
    tags: str
    source: str
    raw_input: str


class QuickInputRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class QuickInputResult(BaseModel):
    parsed: TransactionCreate
    confidence: float
    explanation: str
    transaction: TransactionOut | None = None
    needs_confirmation: bool = False
