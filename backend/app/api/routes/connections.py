import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import StatementParseError, available_providers, get_connector
from app.connectors.open_banking import OpenBankingError, ensure_public_url
from app.core.database import get_db
from app.core.security import EncryptionUnavailable
from app.models.account import Account
from app.models.connection import BankConnection, BankImport
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    ImportOut,
    ProviderOut,
    SyncRequest,
)
from app.services.bank_sync import (
    ensure_account,
    import_statement_file,
    store_credentials,
    sync_via_api,
)

router = APIRouter(prefix="/connections", tags=["connections"])

MAX_STATEMENT_BYTES = 15 * 1024 * 1024


async def _to_out(db: AsyncSession, connection: BankConnection) -> ConnectionOut:
    out = ConnectionOut.model_validate(connection)
    out.title = get_connector(connection.provider).title
    out.has_credentials = bool(connection.credentials_encrypted)
    if connection.account_id:
        account = await db.get(Account, connection.account_id)
        if account:
            out.account_name = account.name
            out.account_balance = account.balance
    return out


def _import_to_out(run: BankImport) -> ImportOut:
    out = ImportOut.model_validate(run)
    try:
        warnings = json.loads(run.warnings_json or "[]")
    except json.JSONDecodeError:
        warnings = []
    out.warnings = [str(w) for w in warnings]
    return out


async def _get_connection(db: AsyncSession, connection_id: int) -> BankConnection:
    connection = await db.get(BankConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Подключение не найдено")
    return connection


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers():
    return [
        ProviderOut(
            provider=connector.provider,
            title=connector.title,
            supports_statement=connector.supports_statement,
            supports_api=connector.supports_api,
            statement_formats=list(connector.statement_formats),
            instructions=connector.instructions,
        )
        for connector in available_providers()
    ]


@router.get("", response_model=list[ConnectionOut])
async def list_connections(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(BankConnection).order_by(BankConnection.id))
    ).scalars()
    return [await _to_out(db, row) for row in rows]


def _check_api_url(raw: str | None) -> None:
    """Отказать сразу, а не в момент первой синхронизации."""
    if not (raw or "").strip():
        return
    try:
        ensure_public_url(raw.strip())
    except OpenBankingError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("", response_model=ConnectionOut)
async def create_connection(payload: ConnectionCreate, db: AsyncSession = Depends(get_db)):
    try:
        connector = get_connector(payload.provider)
    except StatementParseError as exc:
        raise HTTPException(400, str(exc)) from exc

    if payload.mode == "api" and not connector.supports_api:
        raise HTTPException(400, f"{connector.title}: прямое подключение по API недоступно")

    _check_api_url(payload.api_base_url)
    connection = BankConnection(
        provider=connector.provider,
        label=payload.label or connector.title,
        account_id=payload.account_id,
        mode=payload.mode,
        api_base_url=payload.api_base_url.strip(),
        external_account_id=payload.external_account_id.strip(),
    )
    if payload.access_token:
        try:
            store_credentials(connection, payload.access_token)
        except EncryptionUnavailable as exc:
            raise HTTPException(400, str(exc)) from exc
    db.add(connection)
    await db.flush()
    await ensure_account(db, connection, payload.label)
    await db.flush()
    return await _to_out(db, connection)


@router.patch("/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, connection_id)
    data = payload.model_dump(exclude_unset=True)
    access_token = data.pop("access_token", None)
    _check_api_url(data.get("api_base_url"))
    for key, value in data.items():
        setattr(connection, key, value)
    if access_token is not None:
        try:
            store_credentials(connection, access_token)
        except EncryptionUnavailable as exc:
            raise HTTPException(400, str(exc)) from exc
    await db.flush()
    return await _to_out(db, connection)


@router.delete("/{connection_id}")
async def delete_connection(connection_id: int, db: AsyncSession = Depends(get_db)):
    connection = await _get_connection(db, connection_id)
    await db.delete(connection)
    await db.flush()
    # Imported transactions stay — they are part of the user's history now.
    return {"deleted": connection_id}


async def _read_within_limit(file: UploadFile) -> bytes:
    """Читать по частям: проверка после полного чтения ничего не ограничивает.

    Размер запроса стоит ограничить и на входе, в nginx; здесь — чтобы память
    не зависела от того, что прислали.
    """
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(256 * 1024):
        size += len(chunk)
        if size > MAX_STATEMENT_BYTES:
            raise HTTPException(
                413, "Файл больше 15 МБ — выгрузите выписку за меньший период"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/{connection_id}/statement", response_model=ImportOut)
async def upload_statement(
    connection_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, connection_id)
    data = await _read_within_limit(file)
    await ensure_account(db, connection, connection.label)
    try:
        run = await import_statement_file(db, connection, data, file.filename or "statement")
    except StatementParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _import_to_out(run)


@router.post("/{connection_id}/sync", response_model=ImportOut)
async def sync_connection(
    connection_id: int,
    payload: SyncRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, connection_id)
    await ensure_account(db, connection, connection.label)
    payload = payload or SyncRequest()
    try:
        run = await sync_via_api(db, connection, since=payload.since, until=payload.until)
    except StatementParseError as exc:
        raise HTTPException(400, str(exc)) from exc
    except EncryptionUnavailable as exc:
        # Иначе беда с ключом на нашей стороне выглядела бы как молчание банка.
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Банк недоступен: {exc}") from exc
    return _import_to_out(run)


@router.get("/{connection_id}/imports", response_model=list[ImportOut])
async def list_imports(connection_id: int, db: AsyncSession = Depends(get_db)):
    await _get_connection(db, connection_id)
    rows = (
        await db.execute(
            select(BankImport)
            .where(BankImport.connection_id == connection_id)
            .order_by(BankImport.id.desc())
            .limit(50)
        )
    ).scalars()
    return [_import_to_out(row) for row in rows]
