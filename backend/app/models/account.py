from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(32))
    # cash | card | bank | investment | crypto | savings | reserve | debt
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    color: Mapped[str] = mapped_column(String(32), default="#34d399")
    icon: Mapped[str] = mapped_column(String(48), default="wallet")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
