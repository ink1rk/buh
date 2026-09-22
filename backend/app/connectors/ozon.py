"""Ozon Bank connector.

Ozon Bank has no public API for personal accounts — the Bank of Russia Open API
standard for individuals only takes effect on 2026-10-01, and access to it
requires registration as a СПУ. So the working path today is the statement the
user exports from the Ozon Bank app, and `OpenBankingClient` sits behind
`mode="api"` for the day the bank opens up.
"""

from __future__ import annotations

from datetime import date

from app.connectors.base import (
    ApiCredentials,
    BankConnector,
    ParsedStatement,
    StatementParseError,
)
from app.connectors.open_banking import (
    OpenBankingClient,
    statement_from_transactions,
)
from app.connectors.pdf_statement import parse_pdf_statement
from app.connectors.tabular import read_csv_rows, read_xlsx_rows, rows_to_statement

# Ozon pays part of its cashback in bonus points. Those are not rubles and must
# never reach the ledger, or net worth silently inflates.
BONUS_MARKERS = ("балл", "бонус", "point", "ozon бал")

INSTRUCTIONS = (
    "Как получить выписку: приложение Ozon Банк → «Профиль» → «Выписки и справки» → "
    "выберите счёт и период → «Выписка по счёту». Форматы XLSX и CSV разбираются точнее всего, "
    "PDF — эвристически. Файл можно сразу загрузить сюда; повторная загрузка за "
    "пересекающийся период ничего не продублирует."
)


class OzonBankConnector(BankConnector):
    provider = "ozon"
    title = "Ozon Банк"
    account_name = "Ozon Банк"
    account_color = "#0069ff"
    supports_statement = True
    supports_api = True
    statement_formats = (".csv", ".xlsx", ".xls", ".pdf")
    instructions = INSTRUCTIONS

    def parse_statement(self, data: bytes, filename: str) -> ParsedStatement:
        if not data:
            raise StatementParseError("Файл выписки пустой")

        suffix = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if suffix == ".pdf" or data[:5] == b"%PDF-":
            statement = parse_pdf_statement(data)
        elif suffix in {".xlsx", ".xls"} or data[:2] == b"PK":
            statement = rows_to_statement(read_xlsx_rows(data))
        elif suffix in {".csv", ".txt", ""}:
            statement = rows_to_statement(read_csv_rows(data))
        else:
            raise StatementParseError(
                f"Формат «{suffix or filename}» не поддерживается. "
                f"Подойдут: {', '.join(self.statement_formats)}"
            )
        return _drop_bonus_operations(statement)

    async def fetch_operations(
        self,
        credentials: ApiCredentials,
        *,
        since: date,
        until: date,
    ) -> ParsedStatement:
        client = OpenBankingClient(credentials.base_url, credentials.access_token)
        account_id = credentials.external_account_id
        if not account_id:
            accounts = await client.list_accounts()
            if not accounts:
                raise StatementParseError("Банк не вернул ни одного счёта по выданному согласию")
            account_id = str(accounts[0].get("accountId") or "")

        transactions = await client.fetch_transactions(account_id, since=since, until=until)
        statement = statement_from_transactions(transactions)
        statement.account_hint = account_id
        statement.closing_balance = await client.fetch_balance(account_id)
        return _drop_bonus_operations(statement)


def _drop_bonus_operations(statement: ParsedStatement) -> ParsedStatement:
    """Remove loyalty-point operations, which are not money."""
    kept = []
    dropped = 0
    for operation in statement.operations:
        haystack = f"{operation.currency} {operation.description} {operation.bank_category}".lower()
        if any(marker in haystack for marker in BONUS_MARKERS):
            dropped += 1
            continue
        kept.append(operation)

    statement.operations = kept
    if dropped:
        statement.warnings.append(
            f"Пропущено операций в баллах Ozon (это не деньги): {dropped}"
        )
    return statement
