from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMModel


class GoalCreate(BaseModel):
    title: str
    description: str = ""
    target_amount: float
    current_amount: float = 0.0
    monthly_contribution: float = 0.0
    deadline: date | None = None
    icon: str = "target"
    color: str = "#60a5fa"
    category: str = "other"
    priority: int = 1


class GoalUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    target_amount: float | None = None
    current_amount: float | None = None
    monthly_contribution: float | None = None
    deadline: date | None = None
    icon: str | None = None
    color: str | None = None
    is_active: bool | None = None
    priority: int | None = None


class GoalOut(ORMModel):
    id: int
    title: str
    description: str
    target_amount: float
    current_amount: float
    monthly_contribution: float
    deadline: date | None
    icon: str
    color: str
    category: str
    priority: int
    is_active: bool
    probability: float
    remaining: float = 0
    progress_pct: float = 0
    months_left: float | None = None
