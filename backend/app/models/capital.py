from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Asset(Base, TimestampMixin):
    """Non-liquid assets that make up real net worth: property, car, gold, gadgets."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_type: Mapped[str] = mapped_column(String(32), default="other")
    # real_estate | car | gold | tech | other
    value: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    icon: Mapped[str] = mapped_column(String(48), default="box")
    color: Mapped[str] = mapped_column(String(32), default="#94a3b8")
    notes: Mapped[str] = mapped_column(Text, default="")


class NetWorthSnapshot(Base, TimestampMixin):
    """Daily snapshot of net worth so we can chart trend + deltas + contribution graph."""

    __tablename__ = "net_worth_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True)
    net_worth: Mapped[float] = mapped_column(Float)
    total_liquid: Mapped[float] = mapped_column(Float, default=0.0)
    total_assets: Mapped[float] = mapped_column(Float, default=0.0)
    total_investments: Mapped[float] = mapped_column(Float, default=0.0)
    total_debts: Mapped[float] = mapped_column(Float, default=0.0)
    day_expense: Mapped[float] = mapped_column(Float, default=0.0)
    day_income: Mapped[float] = mapped_column(Float, default=0.0)
    day_rating: Mapped[str] = mapped_column(String(16), default="neutral")
    # good | neutral | overspend — powers the GitHub-style contribution graph
