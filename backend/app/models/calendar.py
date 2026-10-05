from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(64), default="payment")
    # salary | credit | utilities | subscription | birthday | gift | travel | tax | fine | reminder
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    event_date: Mapped[date] = mapped_column(Date)
    recurrence: Mapped[str] = mapped_column(String(32), default="none")
    # none | weekly | monthly | yearly
    color: Mapped[str] = mapped_column(String(32), default="#a78bfa")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=3)
    source: Mapped[str] = mapped_column(String(32), default="")
    external_id: Mapped[str] = mapped_column(String(200), default="")
