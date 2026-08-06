from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class AIMemory(Base, TimestampMixin):
    __tablename__ = "ai_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    memory_type: Mapped[str] = mapped_column(String(64), default="preference")
    # preference | goal | habit | fear | fact | conversation
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    embedding_id: Mapped[str] = mapped_column(String(120), default="")
    tags: Mapped[str] = mapped_column(String(500), default="")
