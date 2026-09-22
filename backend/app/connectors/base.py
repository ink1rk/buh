"""Provider-agnostic contract for bank data sources.

A connector turns whatever a bank gives us — an exported statement file or an
Open-API response — into a list of `RawOperation`. Everything downstream
(dedupe, categorisation, transaction creation) is shared, so adding a second
bank means implementing one class, not touching the ingest pipeline.
"""

from __future__ import annotations

import re
from abc import ABC
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, ClassVar

RUSSIAN_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}

# Statements arrive with unicode minus signs and every flavour of thin space.
_MINUS_CHARS = "-\u2212\u2012\u2013\u2014\u2015"
_SPACE_CHARS = " \u00a0\u202f\u2009\u2007\u2008\u200a\u2060"
_CURRENCY_TOKENS = ("₽", "руб.", "рубль", "рублей", "руб", "rub", "$", "€", "usd", "eur")


class StatementParseError(ValueError):
    """Raised when a statement file cannot be understood at all."""


def parse_money(raw: Any) -> float | None:
    """Parse an amount from a bank statement cell.

    Handles `-1 234,56 ₽`, `−1234.56`, `(1 234,56)`, `1.234,56` and `1,234.56`.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)

    text = str(raw).strip()
    if not text:
        return None

    lowered = text.lower()
    for token in _CURRENCY_TOKENS:
        lowered = lowered.replace(token, "")
    for ch in _SPACE_CHARS:
        lowered = lowered.replace(ch, "")

    negative = False
    if lowered.startswith("(") and lowered.endswith(")"):
        negative = True
        lowered = lowered[1:-1]
    while lowered and lowered[0] in _MINUS_CHARS + "+":
        if lowered[0] in _MINUS_CHARS:
            negative = True
        lowered = lowered[1:]
    while lowered and lowered[-1] in _MINUS_CHARS:
        negative = True
        lowered = lowered[:-1]

    if "," in lowered and "." in lowered:
        # Whichever separator comes last is the decimal one.
        if lowered.rfind(",") > lowered.rfind("."):
            lowered = lowered.replace(".", "").replace(",", ".")
        else:
            lowered = lowered.replace(",", "")
    elif "," in lowered:
        lowered = lowered.replace(",", ".")
    elif lowered.count(".") > 1:
        lowered = lowered.replace(".", "")

    lowered = re.sub(r"[^\d.]", "", lowered)
    if not lowered or lowered == ".":
        return None
    try:
        value = float(lowered)
    except ValueError:
        return None
    return -value if negative else value


def parse_statement_date(raw: Any) -> date | None:
    """Parse a date cell, tolerating time suffixes and Russian month names."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw

    text = str(raw).strip()
    if not text:
        return None
    for ch in _SPACE_CHARS[1:]:
        text = text.replace(ch, " ")

    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    numeric = re.match(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", text)
    if numeric:
        day, month, year = (int(g) for g in numeric.groups())
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)

    worded = re.match(r"(\d{1,2})\s+([А-Яа-яЁё]+)\.?\s*(\d{4})?", text)
    if worded:
        day = int(worded.group(1))
        month = RUSSIAN_MONTHS.get(worded.group(2).lower()[:3])
        year = int(worded.group(3)) if worded.group(3) else date.today().year
        if month:
            return _safe_date(year, month, day)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


# Номер операции годится в опознавательный знак, только если он достаточно
# длинный. Короткий — это счётчик внутри дня: в одной выписке «документ 1» и
# «документ 2», в следующей снова «1». По такому номеру сверка приняла бы
# разные операции за одну и потеряла бы вторую.
UNIQUE_REFERENCE_DIGITS = 7


def unique_reference(raw: Any) -> str:
    """Номер операции, если по нему её вообще можно узнать."""
    text = " ".join(str(raw or "").split())
    digits = sum(1 for ch in text if ch.isdigit())
    return text[:120] if digits >= UNIQUE_REFERENCE_DIGITS else ""


@dataclass(slots=True)
class RawOperation:
    """One bank-side operation, before it becomes a Transaction."""

    occurred_on: date
    amount: float  # signed in account currency: negative = money left the account
    description: str = ""
    merchant: str = ""
    currency: str = "RUB"
    external_id: str = ""
    mcc: str = ""
    bank_category: str = ""
    is_pending: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedStatement:
    """Result of reading a statement file or an API page."""

    operations: list[RawOperation] = field(default_factory=list)
    period_from: date | None = None
    period_to: date | None = None
    closing_balance: float | None = None
    account_hint: str = ""
    warnings: list[str] = field(default_factory=list)


# Выписка печатает свои итоги, и это единственный способ проверить разбор: если
# сумма прочитанных операций не сходится с оборотом, значит часть строк
# потерялась — а неполная выписка молча заводит неверную историю трат.
STATED_LINES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("credit", re.compile(r"итого\s+(?:зачислени|поступлени|приход)", re.IGNORECASE)),
    ("debit", re.compile(r"итого\s+(?:списани|расход)", re.IGNORECASE)),
    ("closing", re.compile(r"исходящ\w*\s+остат", re.IGNORECASE)),
)
# Отклонённые и ожидающие операции банк считает по-своему, поэтому мелкое
# расхождение — замечание, а не отказ.
STATED_TOLERANCE = 0.02
# Итог берётся с конца строки. Разбирать её целиком нельзя: в «31.03.2026
# Итого списаний 1 234,56 ₽» цифры даты слиплись бы с суммой в 310 миллиардов.
_STATED_AMOUNT = re.compile(
    r"(?P<amount>[-+\u2212]?\s?\d{1,3}(?:[\s\u00a0\u202f\u2009]\d{3})*(?:[.,]\d{1,2})?)"
    r"\s*(?:₽|руб\.?|RUB)?\.?$",
    re.IGNORECASE,
)


def stated_totals(texts: Any) -> dict[str, float]:
    """Обороты и исходящий остаток, напечатанные в самой выписке."""
    found: dict[str, float] = {}
    for raw in texts:
        text = " ".join(str(raw or "").split())
        if not text:
            continue
        for name, pattern in STATED_LINES:
            if name in found or not pattern.search(text):
                continue
            tail = _STATED_AMOUNT.search(text)
            money = parse_money(tail.group("amount")) if tail else None
            if money is not None:
                found[name] = money
    return found


def check_against_stated(statement: ParsedStatement, stated: dict[str, float]) -> None:
    read = {
        "credit": sum(op.amount for op in statement.operations if op.amount > 0),
        "debit": sum(-op.amount for op in statement.operations if op.amount < 0),
    }
    turnover = sum(stated.get(side, 0.0) for side in read)
    gap = sum(abs(stated[side] - read[side]) for side in read if side in stated)
    if not turnover or gap <= 1:
        return

    told = "; ".join(
        f"{'зачислений' if side == 'credit' else 'списаний'}: "
        f"в выписке {stated[side]:,.2f}, прочитано {read[side]:,.2f}".replace(",", " ")
        for side in read
        if side in stated
    )
    if gap > turnover * STATED_TOLERANCE:
        raise StatementParseError(
            f"Разбор не сходится с итогами самой выписки ({told}). Часть операций "
            "потерялась, а неполная выписка — это неверная история трат. "
            "Пришлите файл: нужно разобраться с его вёрсткой."
        )
    statement.warnings.append(f"Небольшое расхождение с итогами выписки ({told})")


@dataclass(slots=True)
class ApiCredentials:
    """Open-API credentials for a connection, decrypted for use."""

    access_token: str
    base_url: str = ""
    external_account_id: str = ""


class BankConnector(ABC):
    """Base class every provider implements."""

    provider: ClassVar[str]
    title: ClassVar[str]
    account_name: ClassVar[str] = ""
    account_color: ClassVar[str] = "#34d399"
    supports_statement: ClassVar[bool] = True
    supports_api: ClassVar[bool] = False
    statement_formats: ClassVar[tuple[str, ...]] = ()
    instructions: ClassVar[str] = ""

    def parse_statement(self, data: bytes, filename: str) -> ParsedStatement:
        raise StatementParseError(f"{self.title}: импорт выписок не поддерживается")

    async def fetch_operations(
        self,
        credentials: ApiCredentials,
        *,
        since: date,
        until: date,
    ) -> ParsedStatement:
        raise NotImplementedError(f"{self.title}: прямое подключение по API недоступно")
