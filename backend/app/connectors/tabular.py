"""Tolerant reader for tabular bank statements (CSV / XLSX).

Banks rename statement columns freely and ship them in CP1251, UTF-8 with a BOM
or UTF-16, with `;` or `,` as a delimiter and a few decorative rows above the
header. Rather than hardcoding one layout, this module scores every header cell
against a pattern table and picks the best column per field. That way a small
change in the bank's export keeps working.
"""

from __future__ import annotations

import codecs
import csv
import io
from datetime import date
from typing import Any

from app.connectors.base import (
    ParsedStatement,
    RawOperation,
    StatementParseError,
    parse_money,
    parse_statement_date,
)

# field -> ((header fragment, score), ...). Highest score wins the column.
FIELD_PATTERNS: dict[str, tuple[tuple[str, int], ...]] = {
    "occurred_on": (
        ("датаоперации", 100), ("датасовершения", 96), ("датаивремяоперации", 95),
        ("датапокупки", 92), ("дататранзакции", 90), ("датаивремя", 80),
        ("датаплатежа", 70), ("датадокумента", 60), ("датаобработки", 40),
        ("датасписания", 40), ("датапроведения", 40), ("дата", 30),
        ("date", 30), ("datetime", 25),
    ),
    "amount": (
        ("суммаоперацииввалютесчета", 100), ("суммаввалютесчета", 98),
        ("суммавалютесчета", 96), ("суммаврублях", 94), ("суммавруб", 92),
        ("суммаоперации", 85), ("суммаплатежа", 80), ("суммасучетомкомиссии", 78),
        ("сумма", 60), ("amount", 60),
    ),
    "credit": (
        ("приход", 100), ("зачисление", 96), ("поступление", 94), ("пополнение", 90),
        ("кредит", 70), ("credit", 70),
    ),
    "debit": (
        ("расход", 100), ("списание", 96), ("списано", 94), ("дебет", 70),
        ("debit", 70), ("выдача", 60),
    ),
    "direction": (
        ("типоперации", 100), ("направление", 92), ("видоперации", 85),
        ("приходрасход", 80), ("тип", 50),
    ),
    "description": (
        ("описаниеоперации", 100), ("назначениеплатежа", 96), ("описание", 94),
        ("назначение", 85), ("комментарий", 80), ("детали", 70),
        ("наименованиеоперации", 85), ("description", 90),
    ),
    "merchant": (
        ("контрагент", 100), ("торговаяточка", 96), ("мерчант", 95), ("merchant", 95),
        ("магазин", 90), ("местосовершения", 88), ("продавец", 85), ("получатель", 70),
        ("плательщик", 60),
    ),
    "bank_category": (("категорияоперации", 100), ("категория", 96), ("category", 90)),
    "mcc": (("mccкод", 100), ("mcc", 96), ("мсс", 90), ("кодкатегории", 80)),
    "currency": (
        ("валютасчета", 100), ("валютаоперации", 90), ("валюта", 85), ("currency", 85),
    ),
    "status": (("статусоперации", 100), ("статус", 96), ("status", 90)),
    "external_id": (
        ("номероперации", 100), ("идентификатороперации", 98), ("идентификатор", 90),
        ("референс", 85), ("reference", 85), ("номердокумента", 70), ("authcode", 60),
        ("id", 55),
    ),
    "balance": (
        ("остатокпослеоперации", 100), ("баланспослеоперации", 98), ("остаток", 90),
        ("balance", 85),
    ),
}

DECLINED_MARKERS = ("отклон", "отказ", "неуспеш", "не выполн", "cancel", "fail", "reject", "возврат платежа")
PENDING_MARKERS = ("обработ", "ожид", "hold", "pending", "авториз", "не подтвержд")
DEBIT_MARKERS = ("списание", "расход", "оплата", "покупка", "debit", "перевод со счета")
CREDIT_MARKERS = ("поступление", "приход", "зачисление", "пополнение", "credit", "внесение")

_LEGACY_ENCODINGS = ("cp1251", "cp866", "koi8-r")
_MAX_HEADER_SCAN = 30


def normalize_header(value: Any) -> str:
    text = str(value or "").lower().replace("ё", "е")
    return "".join(ch for ch in text if ch.isalnum())


def _score_column(field: str, header: str) -> int:
    best = 0
    for fragment, score in FIELD_PATTERNS[field]:
        if len(fragment) <= 3:
            if header == fragment:
                best = max(best, score)
        elif fragment in header:
            best = max(best, score)
    return best


def detect_columns(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    """Find the header row and map fields onto column indexes."""
    best_row, best_mapping, best_total = -1, {}, 0

    for row_index, row in enumerate(rows[:_MAX_HEADER_SCAN]):
        headers = [normalize_header(cell) for cell in row]
        if not any(headers):
            continue

        # Per field, remember the best-scoring column; per column, remember the
        # best-scoring field. A column may only serve one field.
        per_field: dict[str, tuple[int, int]] = {}
        for col_index, header in enumerate(headers):
            if not header:
                continue
            for field in FIELD_PATTERNS:
                score = _score_column(field, header)
                if score and score > per_field.get(field, (0, -1))[0]:
                    per_field[field] = (score, col_index)

        claimed: dict[int, tuple[str, int]] = {}
        for field, (score, col_index) in per_field.items():
            current = claimed.get(col_index)
            if current is None or score > current[1]:
                claimed[col_index] = (field, score)
        mapping = {field: col_index for col_index, (field, _) in claimed.items()}

        if "occurred_on" not in mapping or not {"amount", "credit", "debit"} & mapping.keys():
            continue
        total = sum(score for _, score in claimed.values())
        if total > best_total:
            best_row, best_mapping, best_total = row_index, mapping, total

    if best_row < 0:
        raise StatementParseError(
            "Не нашёл в файле строку заголовка с датой и суммой операции. "
            "Проверьте, что это выписка, а не справка или счёт."
        )
    return best_row, best_mapping


def read_csv_rows(data: bytes) -> list[list[str]]:
    text = _decode(data)
    sample = "\n".join(text.splitlines()[:20])
    delimiter = max(";,\t", key=sample.count) if sample else ","
    if sample.count(delimiter) == 0:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader]


def read_xlsx_rows(data: bytes) -> list[list[Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - openpyxl is a hard dependency
        raise StatementParseError("Для чтения XLSX нужен пакет openpyxl") from exc

    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _decode(data: bytes) -> str:
    """Decode statement bytes, honouring BOMs and falling back to CP1251.

    UTF-8 is self-validating, so a successful strict decode is trustworthy. The
    check has to come first: decoding UTF-8 Cyrillic as CP1251 always succeeds
    and yields twice as many "Cyrillic" characters, so any heuristic that just
    counts letters picks the mojibake.
    """
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for encoding in _LEGACY_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _cell(row: list[Any], mapping: dict[str, int], field: str) -> Any:
    index = mapping.get(field)
    if index is None or index >= len(row):
        return None
    return row[index]


def _text(row: list[Any], mapping: dict[str, int], field: str) -> str:
    value = _cell(row, mapping, field)
    return "" if value is None else str(value).strip()


def _closing_balance(
    balances: list[tuple[date, int, float]], dates: list[date]
) -> float | None:
    """The balance after the latest operation, not after the last row.

    Ozon and Tinkoff export newest first, so the bottom row of the file is the
    oldest operation — and its balance is weeks stale. Reading it as the closing
    balance overwrote the account with a number from the past.
    """
    if not balances:
        return None
    latest = max(day for day, _, _ in balances)
    newest_first = dates[0] > dates[-1]
    same_day = sorted(
        ((index, value) for day, index, value in balances if day == latest),
        reverse=not newest_first,
    )
    return same_day[0][1]


def rows_to_statement(rows: list[list[Any]]) -> ParsedStatement:
    """Turn spreadsheet rows into a `ParsedStatement`."""
    header_index, mapping = detect_columns(rows)
    statement = ParsedStatement()
    unreadable = 0
    balances: list[tuple[date, int, float]] = []

    for row in rows[header_index + 1 :]:
        if not any(str(cell).strip() for cell in row if cell is not None):
            continue

        occurred_on = parse_statement_date(_cell(row, mapping, "occurred_on"))
        amount = _row_amount(row, mapping)
        if occurred_on is None or amount is None or amount == 0:
            unreadable += 1
            continue

        status = _text(row, mapping, "status").lower()
        if any(marker in status for marker in DECLINED_MARKERS):
            continue

        description = _text(row, mapping, "description")
        merchant = _text(row, mapping, "merchant") or description[:200]
        currency = (_text(row, mapping, "currency") or "RUB").upper()[:8] or "RUB"
        mcc = "".join(ch for ch in _text(row, mapping, "mcc") if ch.isdigit())

        statement.operations.append(
            RawOperation(
                occurred_on=occurred_on,
                amount=amount,
                description=description or merchant,
                merchant=merchant,
                currency=currency,
                external_id=_text(row, mapping, "external_id"),
                mcc=mcc,
                bank_category=_text(row, mapping, "bank_category"),
                is_pending=any(marker in status for marker in PENDING_MARKERS),
                raw={"row": [str(cell) if cell is not None else "" for cell in row]},
            )
        )
        balance = parse_money(_cell(row, mapping, "balance"))
        if balance is not None:
            balances.append((occurred_on, len(statement.operations) - 1, balance))

    if not statement.operations:
        raise StatementParseError(
            "Заголовок выписки распознан, но ни одной операции прочитать не удалось."
        )

    dates = [op.occurred_on for op in statement.operations]
    statement.period_from = min(dates)
    statement.period_to = max(dates)
    statement.closing_balance = _closing_balance(balances, dates)
    if unreadable:
        statement.warnings.append(f"Пропущено нечитаемых строк: {unreadable}")
    return statement


def _row_amount(row: list[Any], mapping: dict[str, int]) -> float | None:
    """Resolve a signed amount from either one column or a debit/credit pair."""
    amount = parse_money(_cell(row, mapping, "amount"))

    if amount is None:
        credit = parse_money(_cell(row, mapping, "credit")) or 0.0
        debit = parse_money(_cell(row, mapping, "debit")) or 0.0
        if not credit and not debit:
            return None
        return abs(credit) - abs(debit)

    # Some exports keep the amount unsigned and state the direction separately.
    direction = _text(row, mapping, "direction").lower().replace("ё", "е")
    if direction:
        if any(marker in direction for marker in DEBIT_MARKERS):
            return -abs(amount)
        if any(marker in direction for marker in CREDIT_MARKERS):
            return abs(amount)
    return amount
