from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class DebtCreate(BaseModel):
    person_name: str
    direction: str
    amount: float
    remaining: float | None = None
    due_date: date | None = None
    return_probability: float = 0.8
    notes: str = ""


class DebtOut(ORMModel):
    id: int
    person_name: str
    direction: str
    amount: float
    remaining: float
    currency: str
    due_date: date | None
    return_probability: float
    notes: str
    is_active: bool
    time_value_cost: float = 0


class DebtUpdate(BaseModel):
    person_name: str | None = None
    direction: str | None = None
    amount: float | None = None
    remaining: float | None = None
    due_date: date | None = None
    return_probability: float | None = None
    notes: str | None = None
    is_active: bool | None = None


class SubscriptionCreate(BaseModel):
    name: str
    amount: float
    billing_cycle: str = "monthly"
    next_billing_date: date | None = None
    category: str = "entertainment"
    icon: str = "repeat"
    last_used_date: date | None = None


class SubscriptionOut(ORMModel):
    id: int
    name: str
    amount: float
    currency: str
    billing_cycle: str
    next_billing_date: date | None
    category: str
    icon: str
    is_active: bool
    last_used_date: date | None
    unused_warning: bool = False
    unused_days: int = 0


class SubscriptionUpdate(BaseModel):
    name: str | None = None
    amount: float | None = None
    billing_cycle: str | None = None
    next_billing_date: date | None = None
    category: str | None = None
    icon: str | None = None
    last_used_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class CalendarEventCreate(BaseModel):
    title: str
    event_type: str = "payment"
    amount: float = 0
    event_date: date
    recurrence: str = "none"
    color: str = "#a78bfa"
    notes: str = ""
    reminder_days_before: int = 3
    source: str = ""
    external_id: str = ""


class CalendarEventOut(ORMModel):
    id: int
    title: str
    event_type: str
    amount: float
    event_date: date
    recurrence: str
    color: str
    notes: str
    is_completed: bool
    reminder_days_before: int
    source: str = ""
    external_id: str = ""


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    event_type: str | None = None
    amount: float | None = None
    event_date: date | None = None
    recurrence: str | None = None
    color: str | None = None
    notes: str | None = None
    is_completed: bool | None = None
    reminder_days_before: int | None = None


class InvestmentCreate(BaseModel):
    name: str
    ticker: str = ""
    asset_class: str = "stocks"
    value: float = 0
    cost_basis: float = 0
    expected_return: float = 0.1
    risk_score: float = 0.5
    notes: str = ""


class InvestmentOut(ORMModel):
    id: int
    name: str
    ticker: str
    asset_class: str
    value: float
    cost_basis: float
    currency: str
    expected_return: float
    risk_score: float
    notes: str
    gain_pct: float = 0


class InvestmentUpdate(BaseModel):
    name: str | None = None
    ticker: str | None = None
    asset_class: str | None = None
    value: float | None = None
    cost_basis: float | None = None
    expected_return: float | None = None
    risk_score: float | None = None
    notes: str | None = None


class PortfolioAdvice(BaseModel):
    allocation: list[dict]
    risk_level: str
    diversification_score: float
    rebalance_suggestions: list[str]
    emergency_fund_months: float
    inflation_note: str
    narrative: str


class AchievementOut(ORMModel):
    id: int
    code: str
    title: str
    description: str
    icon: str
    category: str
    points: int
    unlocked: bool = False
    unlocked_at: datetime | None = None


class UserProfileOut(ORMModel):
    id: int
    name: str
    currency: str
    monthly_income: float
    theme: str
    city: str
    dreams: str
    fears: str
    habits_notes: str
    onboarding_done: bool
    avatar_emoji: str


class UserProfileUpdate(BaseModel):
    name: str | None = None
    currency: str | None = None
    monthly_income: float | None = None
    theme: str | None = None
    city: str | None = None
    dreams: str | None = None
    fears: str | None = None
    habits_notes: str | None = None
    onboarding_done: bool | None = None
    avatar_emoji: str | None = None


class InsightOut(ORMModel):
    id: int
    title: str
    body: str
    insight_type: str
    severity: str
    category: str
    is_read: bool


class ExportRequest(BaseModel):
    format: str  # csv | excel | json | pdf
    include: list[str] = ["transactions", "accounts", "goals", "debts"]
