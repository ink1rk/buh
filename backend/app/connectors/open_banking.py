"""Client for the Bank of Russia Open API standard (СТО БР ОПИ v2.0.0).

Field names, endpoints and the `Data` / `Links` / `Meta` envelope follow the
published specification "Получение информации о банковских счетах Пользователя.
Методы для физических лиц" (Банк России, ред. 19.12.2025, в силе с 01.10.2026).

No Russian retail bank exposes this to individual developers yet — access
requires registration as a СПУ (сторонний поставщик услуг). The client is here
so that switching a connection from statement files to live sync is a config
change rather than a rewrite, and so the mapping is already tested.
"""

from __future__ import annotations

import ipaddress
import socket
import uuid
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.connectors.base import ParsedStatement, RawOperation, parse_money

COMPLETED_STATUSES = {"acceptedsettlementcompleted", "booked", "completed"}
MAX_PAGES = 50
DEFAULT_PORTS = {"http": 80, "https": 443}


class OpenBankingError(RuntimeError):
    """The bank rejected the request or returned something unusable."""


def ensure_public_url(url: str) -> str:
    """Refuse an address that points back inside our own network.

    The bank's API address is typed in by hand, and the client answers with the
    body of whatever it reached. Left unchecked, that turns a text field into a
    window onto everything running on the host — the assistant on :8800, the
    phone bridge with its health history on :8820, a cloud metadata service.
    """
    parts = urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS:
        raise OpenBankingError(
            f"Адрес Открытого API должен начинаться с http:// или https://, "
            f"а не с «{parts.scheme or url[:40]}»"
        )
    host = (parts.hostname or "").strip()
    if not host:
        raise OpenBankingError("В адресе Открытого API банка нет имени хоста")
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise OpenBankingError("Адрес localhost ведёт внутрь машины, а не в банк")
    for address in _resolve(host):
        if not address.is_global:
            raise OpenBankingError(
                f"Адрес {host} ведёт внутрь сети ({address}), а не в банк. "
                "Проверьте адрес Открытого API."
            )
    return url


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Имя не разрешается — запрос всё равно никуда не уйдёт.
        return []
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    return (
        parts.scheme,
        (parts.hostname or "").lower(),
        parts.port or DEFAULT_PORTS.get(parts.scheme, 0),
    )


class OpenBankingClient:
    """Read-only Account Information (AISP) client."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        *,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise OpenBankingError(
                "Не задан адрес Открытого API банка. "
                "Пока банк не открыл доступ, используйте импорт выписки."
            )
        if not access_token:
            raise OpenBankingError("Не задан токен доступа к Открытому API банка")
        self._base_url = ensure_public_url(base_url.rstrip("/"))
        self._access_token = access_token
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "x-fapi-interaction-id": str(uuid.uuid4()),
            "x-fapi-auth-date": datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %Z"),
        }

    async def _get_pages(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """GET a resource, following `Links.next` until the bank stops paging."""
        payloads: list[dict] = []
        url = f"{self._base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport
        ) as client:
            for _ in range(MAX_PAGES):
                response = await client.get(url, params=params, headers=self._headers())
                if response.status_code == 401:
                    raise OpenBankingError(
                        "Банк отклонил токен доступа (401). Переподключите согласие."
                    )
                if response.status_code == 403:
                    raise OpenBankingError(
                        "Согласие не даёт прав на чтение операций (403). "
                        "Нужны разрешения ReadAccounts и ReadTransactionsBasic."
                    )
                if response.status_code >= 400:
                    raise OpenBankingError(
                        f"Открытый API банка вернул {response.status_code}: {response.text[:200]}"
                    )
                payload = response.json()
                payloads.append(payload)
                next_url = (payload.get("Links") or {}).get("next")
                if not next_url:
                    break
                url, params = self._next_page(str(next_url)), None
        return payloads

    def _next_page(self, candidate: str) -> str:
        """Where the bank says the next page is — if it is still the bank.

        Every request carries the access token, so a `Links.next` pointing at
        another host would hand that token to whoever owns it.
        """
        url = urljoin(self._base_url + "/", candidate)
        if _origin(url) != _origin(self._base_url):
            raise OpenBankingError(
                "Банк увёл выгрузку на другой адрес — туда токен доступа не отправляем"
            )
        return url

    async def list_accounts(self) -> list[dict]:
        pages = await self._get_pages("accounts")
        return [
            account
            for page in pages
            for account in (page.get("Data") or {}).get("Account") or []
        ]

    async def fetch_balance(self, account_id: str) -> float | None:
        pages = await self._get_pages(f"accounts/{account_id}/balances")
        for page in pages:
            for balance in (page.get("Data") or {}).get("Balance") or []:
                amount = parse_money((balance.get("Amount") or {}).get("amount"))
                if amount is None:
                    continue
                if str(balance.get("creditDebitIndicator", "")).lower() == "debit":
                    amount = -amount
                return amount
        return None

    async def fetch_transactions(
        self,
        account_id: str,
        *,
        since: date,
        until: date,
    ) -> list[dict]:
        params = {
            "fromBookingDateTime": f"{since.isoformat()}T00:00:00Z",
            "toBookingDateTime": f"{until.isoformat()}T23:59:59Z",
        }
        pages = await self._get_pages(f"accounts/{account_id}/transactions", params)
        return [
            transaction
            for page in pages
            for transaction in (page.get("Data") or {}).get("Transaction") or []
        ]


def operation_from_transaction(transaction: dict[str, Any]) -> RawOperation | None:
    """Map one `TransactionHistory` object onto a `RawOperation`."""
    amount_block = transaction.get("Amount") or {}
    amount = parse_money(amount_block.get("amount"))
    booked = transaction.get("bookingDateTime") or transaction.get("valueDateTime")
    occurred_on = _parse_iso_date(booked)
    if amount is None or occurred_on is None:
        return None

    if str(transaction.get("creditDebitIndicator", "")).lower() == "debit":
        amount = -abs(amount)
    else:
        amount = abs(amount)

    merchant_info = transaction.get("MerchantInformation") or {}
    counterparty = transaction.get("Creditor") if amount < 0 else transaction.get("Debtor")
    merchant = str(
        (counterparty or {}).get("name")
        or merchant_info.get("merchantName")
        or merchant_info.get("merchantId")
        or ""
    ).strip()

    status = str(transaction.get("status", "")).lower()
    return RawOperation(
        occurred_on=occurred_on,
        amount=amount,
        description=str(transaction.get("transactionInformation") or merchant).strip(),
        merchant=merchant,
        currency=str(amount_block.get("currency") or "RUB").upper()[:8],
        external_id=str(transaction.get("transactionId") or "").strip(),
        mcc="".join(ch for ch in str(merchant_info.get("merchantCategoryCode") or "") if ch.isdigit()),
        is_pending=bool(status) and status not in COMPLETED_STATUSES,
        raw=transaction,
    )


def statement_from_transactions(transactions: list[dict[str, Any]]) -> ParsedStatement:
    statement = ParsedStatement()
    unreadable = 0
    for transaction in transactions:
        operation = operation_from_transaction(transaction)
        if operation is None:
            unreadable += 1
            continue
        statement.operations.append(operation)

    if statement.operations:
        dates = [op.occurred_on for op in statement.operations]
        statement.period_from = min(dates)
        statement.period_to = max(dates)
    if unreadable:
        statement.warnings.append(f"Банк вернул нечитаемых операций: {unreadable}")
    return statement


def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
