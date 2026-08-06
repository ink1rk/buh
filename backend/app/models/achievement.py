from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Achievement(Base, TimestampMixin):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(48), default="trophy")
    category: Mapped[str] = mapped_column(String(64), default="general")
    points: Mapped[int] = mapped_column(Integer, default=10)


class UserAchievement(Base, TimestampMixin):
    __tablename__ = "user_achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    achievement_id: Mapped[int] = mapped_column(Integer)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_new: Mapped[bool] = mapped_column(Boolean, default=True)
