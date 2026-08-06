from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AssetCreate(BaseModel):
    name: str
    asset_type: str = "other"
    value: float = 0.0
    icon: str = "box"
    color: str = "#94a3b8"
    notes: str = ""


class AssetOut(ORMModel):
    id: int
    name: str
    asset_type: str
    value: float
    currency: str
    icon: str
    color: str
    notes: str


class CapitalSlice(BaseModel):
    key: str
    label: str
    value: float
    color: str


class CapitalMap(BaseModel):
    total_capital: float
    net_capital: float
    slices: list[CapitalSlice]
    total_debts: float
    assets: list[AssetOut] = Field(default_factory=list)


class NetWorthDelta(BaseModel):
    today: float
    month: float
    year: float


class NetWorthPoint(BaseModel):
    date: str
    net_worth: float
    rating: str


class NetWorthOut(BaseModel):
    current: float
    delta: NetWorthDelta
    history: list[NetWorthPoint]
    capital_map: CapitalMap


class ContributionDay(BaseModel):
    date: str
    rating: str  # good | neutral | overspend | empty
    net: float
