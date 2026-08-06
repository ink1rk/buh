from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount: Mapped[float] = mapped_column(Float)  # positive for income, negative for expense
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    category: Mapped[str] = mapped_column(String(64), default="other")
    subcategory: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(String(500), default="")
    merchant: Mapped[str] = mapped_column(String(200), default="")
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(32), default="expense")
    # income | expense | transfer | investment | debt | savings
    occurred_on: Mapped[date] = mapped_column(Date)
    tags: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    source: Mapped[str] = mapped_column(String(32), default="manual")
    # manual | quick_input | ocr | import | ai
    raw_input: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    receipt_path: Mapped[str] = mapped_column(String(500), default="")
