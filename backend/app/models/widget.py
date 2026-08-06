from datetime import date

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class DailyWidget(Base, TimestampMixin):
    __tablename__ = "daily_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shown_on: Mapped[date] = mapped_column(Date, unique=True)
    widget_type: Mapped[str] = mapped_column(String(64))
    # tip | thought | fact | bias | invest | save | negotiate | career | income
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
