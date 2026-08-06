from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Debt(Base, TimestampMixin):
    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_name: Mapped[str] = mapped_column(String(200))
    direction: Mapped[str] = mapped_column(String(16))  # owed_to_me | i_owe
    amount: Mapped[float] = mapped_column(Float)
    remaining: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    return_probability: Mapped[float] = mapped_column(Float, default=0.8)
    notes: Mapped[str] = mapped_column(Text, default="")
    history: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of notes
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
