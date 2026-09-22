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
# Statement furniture: totals, carried-over balances, page headers. These lines
# can begin with a date — a period reads as one ("01.09.2026 — 30.09.2026
# Поступления 50 000 ₽") — and taken for operations they invent money that was
# never spent, twice over: once in the ledger, once in the balance.
_SUMMARY = re.compile(
    r"(итого|всего|входящ\w*\s+остат\w*|исходящ\w*\s+остат\w*|остаток\s+на|"
    r"оборот\w*|сумма\s+(?:пополнен|списан|операц)\w*|поступлени\w*\s+за|"
    r"списани\w*\s+за|продолжение|перенос\w*\s+с\s+предыдущ\w*|"
    r"balance\s+(?:brought|carried)|total)",
    re.IGNORECASE,
)
_PERIOD_LINE = re.compile(
    r"^\s*\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\s*(?:—|–|-|по)\s*\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"
)
# A PDF loses the debit/credit columns, so an unsigned amount says nothing about
# direction on its own. The wording usually does.
_INCOME_WORDS = (
    "зачислен",
    "поступлен",
    "пополнен",
    "возврат",
    "кэшбэк",
    "кешбэк",
    "зарплат",
    "аванс",
    "процент",
    "депозит",
    "внесен",
    "перевод от",
    "credit",
    "refund",
    "salary",
)
_EXPENSE_WORDS = (
    "оплата",
    "покупка",
    "списан",
    "перевод на",
    "снятие",
    "комисси",
    "платеж",
    "штраф",
    "подписка",
    "debit",
    "payment",
    "purchase",
)
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


def _direction(description: str) -> int:
    """+1 income, -1 expense, 0 — the wording gives nothing away."""
    text = description.lower().replace("ё", "е")
    if any(word in text for word in _INCOME_WORDS):
        return 1
    if any(word in text for word in _EXPENSE_WORDS):
        return -1
    return 0


def parse_pdf_statement(data: bytes) -> ParsedStatement:
    text = extract_pdf_text(data)
    if not text.strip():
        raise StatementParseError(
            "В PDF нет текстового слоя — похоже, это скан. "
            "Выгрузите выписку в CSV/XLSX или загрузите страницы через распознавание чеков."
        )

    statement = ParsedStatement()
    unsigned = guessed = totals = 0
    any_signed = False

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
        if _SUMMARY.search(line) or _PERIOD_LINE.match(line):
            totals += 1
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

        description = re.sub(r"\s{2,}", " ", body).strip(" ·|-—")
        if _SIGNED.match(raw_amount):
            any_signed = True
        else:
            unsigned += 1
            direction = _direction(description)
            if direction == 0:
                guessed += 1
            amount = abs(amount) * (1 if direction > 0 else -1)

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

    if not any_signed and guessed * 2 > len(statement.operations):
        # Ни знаков, ни понятных формулировок: такой файл банк печатал в две
        # колонки, и в тексте от них ничего не осталось. Записать всё расходом
        # — значит испортить и историю, и капитал.
        raise StatementParseError(
            f"В этом PDF у операций нет ни знака, ни понятного описания "
            f"({guessed} из {len(statement.operations)}), поэтому непонятно, "
            "где приход, а где расход. Выгрузите выписку в CSV или XLSX."
        )

    dates = [op.occurred_on for op in statement.operations]
    statement.period_from = min(dates)
    statement.period_to = max(dates)

    period = _PERIOD.search(text)
    if period:
        statement.period_from = parse_statement_date(period.group(1)) or statement.period_from
        statement.period_to = parse_statement_date(period.group(2)) or statement.period_to

    if totals:
        statement.warnings.append(
            f"Строк с итогами и остатками пропущено: {totals} (это не операции)."
        )
    if unsigned:
        statement.warnings.append(
            f"У {unsigned} операций в PDF не было знака — направление определено "
            f"по описанию, из них наугад: {guessed}. Проверьте их на странице «Банки»."
        )
    statement.warnings.append("PDF разобран эвристически; CSV или XLSX точнее.")
    return statement
