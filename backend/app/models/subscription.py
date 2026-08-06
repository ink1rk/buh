from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    billing_cycle: Mapped[str] = mapped_column(String(16), default="monthly")
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="entertainment")
    icon: Mapped[str] = mapped_column(String(48), default="repeat")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    unused_days_threshold: Mapped[int] = mapped_column(Integer, default=60)
    notes: Mapped[str] = mapped_column(Text, default="")
