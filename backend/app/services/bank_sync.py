"""Ingest pipeline shared by every bank connector.

Parsing is the connector's job; everything here is provider-agnostic:
deduplicate against what we already stored, categorise, write transactions and
reconcile the account balance.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import ApiCredentials, StatementParseError, get_connector
from app.connectors.base import ParsedStatement, RawOperation
from app.connectors.categorize import classify
from app.core.security import decrypt_text, encrypt_text
from app.models.account import Account
from app.models.connection import BankConnection, BankImport, BankOperation
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

DEFAULT_SYNC_WINDOW_DAYS = 90
_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower().replace("ё", "е"))


def _base_fingerprint(provider: str, operation: RawOperation) -> str:
    """Stable identity for an operation, independent of import order."""
    if operation.external_id:
        payload = f"{provider}|id|{operation.external_id}"
        return hashlib.sha256(payload.encode()).hexdigest()[:40]

    payload = "|".join(
        [
            provider,
            operation.occurred_on.isoformat(),
            str(round(operation.amount * 100)),
            operation.currency.upper(),
            _normalize(operation.description or operation.merchant),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:40]


def _fingerprints(provider: str, operations: list[RawOperation]) -> list[str]:
    """Suffix repeated identities with an occurrence index.

    Two identical coffees on the same day are two real operations, but the same
    file imported twice is not. Numbering occurrences in statement order keeps
    both cases right.
    """
    seen: dict[str, int] = {}
    result = []
    for operation in operations:
        base = _base_fingerprint(provider, operation)
        index = seen.get(base, 0)
        seen[base] = index + 1
        result.append(f"{base}#{index}")
    return result


def credentials_for(connection: BankConnection) -> ApiCredentials:
    token = decrypt_text(connection.credentials_encrypted) if connection.credentials_encrypted else ""
    return ApiCredentials(
        access_token=token,
        base_url=connection.api_base_url,
        external_account_id=connection.external_account_id,
    )


def store_credentials(connection: BankConnection, access_token: str) -> None:
    connection.credentials_encrypted = encrypt_text(access_token) if access_token else ""


async def ingest_statement(
    db: AsyncSession,
    connection: BankConnection,
    statement: ParsedStatement,
    *,
    source_name: str,
    source_kind: str = "statement",
) -> BankImport:
    """Write new operations from `statement` into the ledger."""
    account = await db.get(Account, connection.account_id) if connection.account_id else None
    warnings = list(statement.warnings)

    fingerprints = _fingerprints(connection.provider, statement.operations)
    existing = set()
    if fingerprints:
        rows = await db.execute(
            select(BankOperation.fingerprint).where(BankOperation.fingerprint.in_(fingerprints))
        )
        existing = set(rows.scalars())

    run = BankImport(
        connection_id=connection.id,
        source_name=source_name[:300],
        source_kind=source_kind,
        parsed_count=len(statement.operations),
        period_from=statement.period_from,
        period_to=statement.period_to,
        closing_balance=statement.closing_balance,
    )
    db.add(run)
    await db.flush()

    imported = duplicates = skipped = 0
    net_amount = 0.0
    foreign_currency = set()

    for operation, fingerprint in zip(statement.operations, fingerprints, strict=True):
        if fingerprint in existing:
            duplicates += 1
            continue
        if operation.is_pending:
            skipped += 1
            continue

        category, transaction_type = classify(operation)
        if account and operation.currency.upper() != account.currency.upper():
            foreign_currency.add(operation.currency.upper())

        transaction = Transaction(
            amount=operation.amount,
            currency=operation.currency,
            category=category,
            description=(operation.description or operation.merchant)[:500],
            merchant=operation.merchant[:200],
            account_id=connection.account_id,
            transaction_type=transaction_type,
            occurred_on=operation.occurred_on,
            tags=f"bank,{connection.provider}",
            source="import",
            raw_input=(operation.description or operation.merchant)[:500],
            meta_json=json.dumps(
                {
                    "provider": connection.provider,
                    "connection_id": connection.id,
                    "import_id": run.id,
                    "fingerprint": fingerprint,
                    "external_id": operation.external_id,
                    "mcc": operation.mcc,
                    "bank_category": operation.bank_category,
                },
                ensure_ascii=False,
            ),
        )
        db.add(transaction)
        await db.flush()

        db.add(
            BankOperation(
                connection_id=connection.id,
                import_id=run.id,
                transaction_id=transaction.id,
                fingerprint=fingerprint,
                external_id=operation.external_id[:120],
                occurred_on=operation.occurred_on,
                amount=operation.amount,
                currency=operation.currency,
                description=(operation.description or operation.merchant)[:500],
                raw_json=json.dumps(operation.raw, ensure_ascii=False, default=str)[:20000],
            )
        )
        existing.add(fingerprint)
        imported += 1
        net_amount += operation.amount

    if foreign_currency:
        warnings.append(
            "Операции в другой валюте записаны как есть: " + ", ".join(sorted(foreign_currency))
        )

    if account:
        # The bank's own closing balance beats our arithmetic whenever we have it.
        if statement.closing_balance is not None:
            account.balance = statement.closing_balance
        elif net_amount:
            account.balance += net_amount

    run.imported_count = imported
    run.duplicate_count = duplicates
    run.skipped_count = skipped
    run.warnings_json = json.dumps(warnings, ensure_ascii=False)
    run.status = "ok"

    connection.status = "idle"
    connection.last_error = ""
    connection.last_synced_at = datetime.now()
    connection.imported_total += imported
    if statement.period_to and (
        connection.last_operation_on is None or statement.period_to > connection.last_operation_on
    ):
        connection.last_operation_on = statement.period_to
    if statement.account_hint and not connection.external_account_id:
        connection.external_account_id = statement.account_hint[:120]

    await db.flush()
    return run


async def import_statement_file(
    db: AsyncSession,
    connection: BankConnection,
    data: bytes,
    filename: str,
) -> BankImport:
    connector = get_connector(connection.provider)
    try:
        statement = connector.parse_statement(data, filename)
    except StatementParseError as exc:
        await _record_failure(db, connection, source_name=filename, error=str(exc))
        raise
    return await ingest_statement(db, connection, statement, source_name=filename)


async def sync_via_api(
    db: AsyncSession,
    connection: BankConnection,
    *,
    since: date | None = None,
    until: date | None = None,
) -> BankImport:
    connector = get_connector(connection.provider)
    if not connector.supports_api:
        raise StatementParseError(f"{connector.title}: прямое подключение по API недоступно")

    until = until or date.today()
    since = since or (
        connection.last_operation_on - timedelta(days=3)
        if connection.last_operation_on
        else until - timedelta(days=DEFAULT_SYNC_WINDOW_DAYS)
    )
    try:
        statement = await connector.fetch_operations(
            credentials_for(connection), since=since, until=until
        )
    except Exception as exc:
        logger.warning("API sync failed for connection %s: %s", connection.id, exc)
        await _record_failure(db, connection, source_name="api", error=str(exc))
        raise
    return await ingest_statement(
        db,
        connection,
        statement,
        source_name=f"API {since.isoformat()}…{until.isoformat()}",
        source_kind="api",
    )


async def _record_failure(
    db: AsyncSession,
    connection: BankConnection,
    *,
    source_name: str,
    error: str,
) -> None:
    db.add(
        BankImport(
            connection_id=connection.id,
            source_name=source_name[:300],
            status="error",
            error=error[:2000],
        )
    )
    connection.status = "error"
    connection.last_error = error[:2000]
    # Commit now: the caller re-raises, and the whole point of this record is to
    # survive the failed request so the user can see what went wrong.
    await db.commit()


async def ensure_account(db: AsyncSession, connection: BankConnection, label: str) -> Account:
    """Attach a local account to the connection, creating one if needed."""
    if connection.account_id:
        account = await db.get(Account, connection.account_id)
        if account:
            return account

    connector = get_connector(connection.provider)
    account = Account(
        name=label or connector.account_name or connector.title,
        account_type="bank",
        balance=0.0,
        color=connector.account_color,
        icon="landmark",
        notes=f"Подключён коннектор «{connector.title}»",
    )
    db.add(account)
    await db.flush()
    connection.account_id = account.id
    return account
