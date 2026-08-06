from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    target_amount: Mapped[float] = mapped_column(Float)
    current_amount: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_contribution: Mapped[float] = mapped_column(Float, default=0.0)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    icon: Mapped[str] = mapped_column(String(48), default="target")
    color: Mapped[str] = mapped_column(String(32), default="#60a5fa")
    category: Mapped[str] = mapped_column(String(64), default="other")
    # travel | apartment | car | emergency | retirement | gadget | other
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    probability: Mapped[float] = mapped_column(Float, default=0.5)
