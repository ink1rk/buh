from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class BankConnection(Base, TimestampMixin):
    """A bank data source bound to a local account."""

    __tablename__ = "bank_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))  # ozon | ...
    label: Mapped[str] = mapped_column(String(120), default="")
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="statement")  # statement | api
    status: Mapped[str] = mapped_column(String(16), default="idle")  # idle | syncing | error
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Open-API mode only. Encrypted with ENCRYPTION_KEY, never returned by the API.
    credentials_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_base_url: Mapped[str] = mapped_column(String(300), default="")
    external_account_id: Mapped[str] = mapped_column(String(120), default="")

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_operation_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    imported_total: Mapped[int] = mapped_column(Integer, default=0)


class BankImport(Base, TimestampMixin):
    """One ingest run — a parsed statement file or an API fetch window."""

    __tablename__ = "bank_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(Integer, index=True)
    source_name: Mapped[str] = mapped_column(String(300), default="")
    source_kind: Mapped[str] = mapped_column(String(16), default="statement")  # statement | api
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")


class BankOperation(Base, TimestampMixin):
    """A bank-side operation already ingested, keyed by a stable fingerprint.

    Keeping this separate from `transactions` means re-importing an overlapping
    statement never duplicates anything, and the bank's own record stays
    auditable even after the user edits the resulting transaction.
    """

    __tablename__ = "bank_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(Integer, index=True)
    import_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    external_id: Mapped[str] = mapped_column(String(120), default="")
    occurred_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    description: Mapped[str] = mapped_column(String(500), default="")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
