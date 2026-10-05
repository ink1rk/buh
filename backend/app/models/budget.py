from sqlalchemy import Boolean, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class BudgetEnvelope(Base, TimestampMixin):
    """Месячный лимит по категории. План, а не факт из выписки."""

    __tablename__ = "budget_envelopes"
    __table_args__ = (UniqueConstraint("category", name="uq_budget_envelope_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(64))
    monthly_limit: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
