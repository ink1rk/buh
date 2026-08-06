from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AccountCreate(BaseModel):
    name: str
    account_type: str
    balance: float = 0.0
    currency: str = "RUB"
    color: str = "#34d399"
    icon: str = "wallet"
    notes: str = ""
    sort_order: int = 0


class AccountUpdate(BaseModel):
    name: str | None = None
    balance: float | None = None
    color: str | None = None
    icon: str | None = None
    is_active: bool | None = None
    notes: str | None = None
    sort_order: int | None = None


class AccountOut(ORMModel):
    id: int
    name: str
    account_type: str
    balance: float
    currency: str
    color: str
    icon: str
    is_active: bool
    notes: str
    sort_order: int


class DashboardBalances(BaseModel):
    total: float
    cash: float = 0
    cards: float = 0
    bank: float = 0
    investments: float = 0
    crypto: float = 0
    savings: float = 0
    reserve: float = 0
    debts_owed: float = 0
    debts_owing: float = 0
    income_month: float = 0
    expense_month: float = 0
    accounts: list[AccountOut] = Field(default_factory=list)
