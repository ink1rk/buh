from datetime import date

from sqlalchemy import Boolean, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Insight(Base, TimestampMixin):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    insight_type: Mapped[str] = mapped_column(String(64), default="pattern")
    # pattern | alert | opportunity | praise | warning
    severity: Mapped[str] = mapped_column(String(16), default="info")
    category: Mapped[str] = mapped_column(String(64), default="general")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    shown_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
