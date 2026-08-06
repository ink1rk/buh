from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class InvestmentHolding(Base, TimestampMixin):
    __tablename__ = "investment_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str] = mapped_column(String(32), default="")
    asset_class: Mapped[str] = mapped_column(String(64), default="stocks")
    # stocks | bonds | etf | crypto | real_estate | cash | other
    value: Mapped[float] = mapped_column(Float, default=0.0)
    cost_basis: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    expected_return: Mapped[float] = mapped_column(Float, default=0.1)
    risk_score: Mapped[float] = mapped_column(Float, default=0.5)
    notes: Mapped[str] = mapped_column(Text, default="")
