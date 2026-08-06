from pydantic import BaseModel


class HabitScore(BaseModel):
    key: str
    label: str
    score: float
    explanation: str


class HabitsProfile(BaseModel):
    scores: list[HabitScore]
    overall: float
    archetype: str
    summary: str


class RiskItem(BaseModel):
    key: str
    label: str
    level: float  # 0-100, higher = riskier
    status: str  # low | medium | high
    explanation: str


class RisksProfile(BaseModel):
    items: list[RiskItem]
    overall_risk: float
    summary: str
