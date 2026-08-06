from pydantic import BaseModel, Field


class TimeSeriesPoint(BaseModel):
    date: str
    income: float = 0
    expense: float = 0
    net: float = 0


class CategorySlice(BaseModel):
    name: str
    value: float
    color: str = "#60a5fa"


class HeatmapCell(BaseModel):
    date: str
    value: float
    weekday: int
    week: int


class CashFlowNode(BaseModel):
    id: str
    label: str
    amount: float
    color: str


class CashFlowLink(BaseModel):
    source: str
    target: str
    value: float


class CashFlowDiagram(BaseModel):
    nodes: list[CashFlowNode]
    links: list[CashFlowLink]


class ForecastPoint(BaseModel):
    date: str
    optimistic: float
    base: float
    stress: float


class ForecastResult(BaseModel):
    month_end_expense: float
    year_end_balance: float
    runway_days: int | None
    million_date: str | None
    retirement_date: str | None
    series: list[ForecastPoint] = Field(default_factory=list)
    narrative: str = ""


class ScenarioRequest(BaseModel):
    scenario: str
    params: dict = Field(default_factory=dict)
    months: int = 36


class ScenarioResult(BaseModel):
    scenario: str
    title: str
    optimistic: list[ForecastPoint]
    base: list[ForecastPoint]
    stress: list[ForecastPoint]
    summary: str
    recommendations: list[str]


class AnalyticsBundle(BaseModel):
    timeseries: list[TimeSeriesPoint]
    by_category: list[CategorySlice]
    heatmap: list[HeatmapCell]
    cashflow: CashFlowDiagram
    radar: list[dict]
    waterfall: list[dict]
    treemap: list[CategorySlice]
