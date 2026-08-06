from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class PurchaseRating(Base, TimestampMixin):
    """Purchase Happiness Index: rate a buy now, get asked again later, AI learns regret patterns."""

    __tablename__ = "purchase_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item: Mapped[str] = mapped_column(String(200))
    price: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[str] = mapped_column(String(64), default="other")
    initial_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followup_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    followed_up: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
