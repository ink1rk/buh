from pydantic import BaseModel, Field


class BudgetEnvelopeIn(BaseModel):
    category: str
    monthly_limit: float = Field(ge=0)


class BudgetEnvelopeOut(BaseModel):
    id: int | None = None
    category: str
    name: str
    color: str
    monthly_limit: float
    spent_this_month: float
    average_last_12m: float
    remaining: float
    pace_pct: float = 0


class BudgetSuggestion(BaseModel):
    category: str
    name: str
    color: str
    average_last_12m: float
    proposed_limit: float
    spent_this_month: float


class BudgetTotals(BaseModel):
    planned: float
    spent: float
    remaining: float
    unallocated: float


class BudgetPlan(BaseModel):
    monthly_income: float
    suggested_income: float
    months_observed: int
    has_plan: bool
    envelopes: list[BudgetEnvelopeOut]
    suggestions: list[BudgetSuggestion]
    totals: BudgetTotals


class BudgetPut(BaseModel):
    monthly_income: float | None = Field(default=None, ge=0)
    envelopes: list[BudgetEnvelopeIn]


class BudgetGlance(BaseModel):
    has_plan: bool = False
    planned: float = 0
    spent: float = 0
    remaining: float = 0
    monthly_income: float = 0
