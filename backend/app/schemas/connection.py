from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ProviderOut(BaseModel):
    provider: str
    title: str
    supports_statement: bool
    supports_api: bool
    statement_formats: list[str]
    instructions: str


class ConnectionCreate(BaseModel):
    provider: str = "ozon"
    label: str = ""
    account_id: int | None = None
    mode: str = "statement"  # statement | api
    api_base_url: str = ""
    access_token: str = ""
    external_account_id: str = ""


class ConnectionUpdate(BaseModel):
    label: str | None = None
    account_id: int | None = None
    is_active: bool | None = None
    mode: str | None = None
    api_base_url: str | None = None
    access_token: str | None = None
    external_account_id: str | None = None


class ConnectionOut(ORMModel):
    id: int
    provider: str
    title: str = ""
    label: str
    account_id: int | None
    account_name: str = ""
    account_balance: float | None = None
    mode: str
    status: str
    is_active: bool
    external_account_id: str
    last_synced_at: datetime | None
    last_operation_on: date | None
    last_error: str
    imported_total: int
    has_credentials: bool = False


class ImportOut(ORMModel):
    id: int
    connection_id: int
    source_name: str
    source_kind: str
    status: str
    parsed_count: int
    imported_count: int
    duplicate_count: int
    skipped_count: int
    period_from: date | None
    period_to: date | None
    closing_balance: float | None
    warnings: list[str] = Field(default_factory=list)
    error: str
    created_at: datetime | None = None


class SyncRequest(BaseModel):
    since: date | None = None
    until: date | None = None
