from datetime import date

from pydantic import BaseModel, Field

from app.schemas.account import DashboardBalances
from app.schemas.common import ORMModel


class HealthFactor(BaseModel):
    name: str
    score: float
    weight: float
    explanation: str


class FinancialHealth(BaseModel):
    score: int
    label: str
    factors: list[HealthFactor]
    summary: str


class DailyWidgetOut(ORMModel):
    id: int
    shown_on: date
    widget_type: str
    title: str
    body: str
    author: str
    source: str


class MotivationalQuote(BaseModel):
    text: str
    author: str
    theme: str


class Greeting(BaseModel):
    greeting: str
    subtitle: str
    user_name: str
    period: str  # morning | afternoon | evening | night


class RitualMorning(BaseModel):
    greeting: Greeting
    balance: float
    main_goal: dict | None
    advice: DailyWidgetOut
    focus: str
    attention: list[str]
    quote: MotivationalQuote
    day_forecast: str


class RitualEvening(BaseModel):
    praise: str
    saved_today: float
    days_to_goal: int | None
    prompt_add_expenses: bool
    summary_points: list[str]


class LivingScreenLine(BaseModel):
    icon: str
    text: str
    tone: str = "neutral"  # positive | neutral | warning


class DashboardOut(BaseModel):
    greeting: Greeting
    quote: MotivationalQuote
    widget: DailyWidgetOut
    health: FinancialHealth
    balances: DashboardBalances
    insights: list[dict] = Field(default_factory=list)
    focus_of_day: str = ""
    net_worth: float = 0
    net_worth_delta_today: float = 0
    net_worth_delta_month: float = 0
    net_worth_delta_year: float = 0
    streak_days: int = 0
    living_screen: list[LivingScreenLine] = Field(default_factory=list)
    daily_challenge: dict | None = None
    proactive_alerts: list[dict] = Field(default_factory=list)
