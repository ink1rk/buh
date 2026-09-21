"""Best-effort reader for PDF statements.

Ozon Bank (like most Russian banks) mails statements as PDF, so this is often
the only file a user actually has. PDFs carry no table structure, so we work
line by line: strip trailing money amounts off each line, and whatever starts
with a date is an operation.

This is deliberately conservative — anything ambiguous is reported as a warning
rather than guessed at, and CSV/XLSX is always the better input when available.
"""

from __future__ import annotations

import re

from app.connectors.base import (
    ParsedStatement,
    RawOperation,
    StatementParseError,
    parse_money,
    parse_statement_date,
)

_DATE_PREFIX = re.compile(r"^\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})\s*(?:\d{2}:\d{2}(?::\d{2})?)?\s*")
_TRAILING_AMOUNT = re.compile(
    r"(?P<amount>[+\-\u2212\u2013]?\s?\d[\d\s\u00a0\u202f\u2009]*(?:[.,]\d{1,2})?)"
    r"\s*(?:₽|руб\.?|RUB|Р)\s*$",
    re.IGNORECASE,
)
_SIGNED = re.compile(r"^[+\-\u2212\u2013]")
_PERIOD = re.compile(
    r"(?:с|за период с|период)\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})\s*(?:по|-|—)\s*(\d{2}[.\-/]\d{2}[.\-/]\d{4})",
    re.IGNORECASE,
)


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - pypdf is a hard dependency
        raise StatementParseError(
            "Для чтения PDF-выписок нужен пакет pypdf. Либо выгрузите выписку в CSV/XLSX."
        ) from exc

    import io

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except StatementParseError:
        raise
    except Exception as exc:
        raise StatementParseError(f"Не удалось прочитать PDF: {exc}") from exc


def parse_pdf_statement(data: bytes) -> ParsedStatement:
    text = extract_pdf_text(data)
    if not text.strip():
        raise StatementParseError(
            "В PDF нет текстового слоя — похоже, это скан. "
            "Выгрузите выписку в CSV/XLSX или загрузите страницы через распознавание чеков."
        )

    statement = ParsedStatement()
    unsigned = 0

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        date_match = _DATE_PREFIX.match(line)
        if not date_match:
            continue
        occurred_on = parse_statement_date(date_match.group(1))
        if occurred_on is None:
            continue

        body = line[date_match.end() :].strip()
        amounts: list[str] = []
        while len(amounts) < 2:
            amount_match = _TRAILING_AMOUNT.search(body)
            if not amount_match:
                break
            amounts.insert(0, amount_match.group("amount").strip())
            body = body[: amount_match.start()].strip()
        if not amounts:
            continue

        # With two trailing amounts the rightmost one is the running balance.
        raw_amount = amounts[0]
        amount = parse_money(raw_amount)
        if amount is None or amount == 0:
            continue
        if not _SIGNED.match(raw_amount):
            unsigned += 1
            amount = -abs(amount)

        description = re.sub(r"\s{2,}", " ", body).strip(" ·|-—")
        statement.operations.append(
            RawOperation(
                occurred_on=occurred_on,
                amount=amount,
                description=description,
                merchant=description[:200],
                raw={"line": line},
            )
        )

    if not statement.operations:
        raise StatementParseError(
            "В PDF не нашлось строк вида «дата — описание — сумма». "
            "Попробуйте выгрузить выписку в CSV или XLSX."
        )

    dates = [op.occurred_on for op in statement.operations]
    statement.period_from = min(dates)
    statement.period_to = max(dates)

    period = _PERIOD.search(text)
    if period:
        statement.period_from = parse_statement_date(period.group(1)) or statement.period_from
        statement.period_to = parse_statement_date(period.group(2)) or statement.period_to

    if unsigned:
        statement.warnings.append(
            f"У {unsigned} операций в PDF не было знака — они записаны как расходы. "
            "Проверьте их на странице «Банки»."
        )
    statement.warnings.append("PDF разобран эвристически; CSV или XLSX точнее.")
    return statement
