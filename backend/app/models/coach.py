from datetime import date

from sqlalchemy import Boolean, Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class DailyChallenge(Base, TimestampMixin):
    """AI Coach: one small actionable task per day."""

    __tablename__ = "daily_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_date: Mapped[date] = mapped_column(Date, unique=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="save")
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
