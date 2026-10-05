"""Bank connector registry.

Adding a bank means writing one `BankConnector` subclass and listing it here.
"""

from __future__ import annotations

from app.connectors.base import (
    ApiCredentials,
    BankConnector,
    ParsedStatement,
    RawOperation,
    StatementParseError,
)
from app.connectors.ozon import OzonBankConnector

_CONNECTORS: dict[str, BankConnector] = {
    OzonBankConnector.provider: OzonBankConnector(),
}


def available_providers() -> list[BankConnector]:
    return list(_CONNECTORS.values())


def get_connector(provider: str) -> BankConnector:
    try:
        return _CONNECTORS[provider.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(_CONNECTORS)) or "—"
        raise StatementParseError(
            f"Банк «{provider}» не поддерживается. Доступные: {known}"
        ) from None


__all__ = [
    "ApiCredentials",
    "BankConnector",
    "ParsedStatement",
    "RawOperation",
    "StatementParseError",
    "available_providers",
    "get_connector",
]
