from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Кирилл")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    monthly_income: Mapped[float] = mapped_column(Float, default=0.0)
    theme: Mapped[str] = mapped_column(String(16), default="auto")  # auto | dark | light
    city: Mapped[str] = mapped_column(String(120), default="")
    dreams: Mapped[str] = mapped_column(Text, default="")
    fears: Mapped[str] = mapped_column(Text, default="")
    habits_notes: Mapped[str] = mapped_column(Text, default="")
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    avatar_emoji: Mapped[str] = mapped_column(String(8), default="✨")
