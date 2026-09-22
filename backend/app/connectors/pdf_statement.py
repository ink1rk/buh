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

from datetime import date

from app.connectors.base import (
    ParsedStatement,
    RawOperation,
    StatementParseError,
    check_against_stated,
    parse_money,
    parse_statement_date,
    stated_totals,
)

_DATE_PREFIX = re.compile(r"^\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})\s*(?:\d{2}:\d{2}(?::\d{2})?)?\s*")
# Знак валюты в выписке обычно стоит один раз — в шапке колонки, а не в каждой
# строке. Пока он требовался, почти все операции молча отбрасывались, и до
# импорта доходили только те немногие строки, где банк валюту всё же напечатал.
_SPACE = r"[\s\u00a0\u202f\u2009]"
_SIGN = r"[+\-\u2212\u2013]?\s?"
# Раньше границей числа служил знак валюты. Без него пробел внутри числа
# перестаёт отличаться от пробела между числами, и «-1 234,56 48 765,44»
# читается одной суммой в пять миллионов. Поэтому разряды описаны как
# разряды: группы ровно по три цифры.
_TRAILING_AMOUNT = re.compile(
    rf"(?:^|(?<={_SPACE})|(?<=[|·]))"
    rf"(?P<amount>{_SIGN}\d{{1,3}}(?:{_SPACE}\d{{3}})+(?:[.,]\d{{1,2}})?"
    rf"|{_SIGN}\d+(?:[.,]\d{{1,2}})?)"
    rf"\s*(?P<currency>₽|руб\.?|RUB|Р)?\s*$",
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


# Номер документа стоит в строке сразу после даты и времени, а описание
# начинается со следующей строки — поэтому голое одиннадцатизначное число
# запросто оказывается концом строки с датой. Приняв его за сумму, разбор
# заводил операции на миллиард рублей.
_REFERENCE_DIGITS = 8


def _is_money(raw: str, currency: str | None) -> bool:
    """Похоже ли хвостовое число на сумму, если валюту банк не напечатал.

    Без якоря валюты концом строки легко оказывается номер документа, страницы
    или сноска. Деньги себя выдают: знак, копейки, разряды или величина,
    которая ещё похожа на деньги.
    """
    if currency:
        return True
    raw = raw.strip()
    if re.search(r"[.,]\d{1,2}$", raw) or _SIGNED.match(raw):
        return True
    if re.search(rf"\d{_SPACE}\d", raw):
        return True
    return 3 <= len(re.sub(r"[^\d]", "", raw)) < _REFERENCE_DIGITS


# Одна операция — не одна строка. Извлечённый из PDF текст переносит
# назначение платежа как в вёрстке, а сумму печатает отдельной строкой уже
# после переноса:
#
#     21.09.2026 18:51:01 13619554740 Оплата товаров по
#     карте 4092 сумма 83.00
#     в Mos.Transport
#     - 83.00 ₽ - 83.00 ₽
#
# Пока сумма требовалась в строке с датой, из годовой выписки читалась
# горстка операций, а остальные молча пропадали.
_CURRENCY = r"(?:₽|руб\.?|RUB|Р)"
_MONEY_BODY = rf"{_SIGN}(?:\d{{1,3}}(?:{_SPACE}\d{{3}})+|\d+)(?:[.,]\d{{1,2}})?"
_MONEY_ONLY = re.compile(rf"^(?:{_MONEY_BODY}\s*{_CURRENCY}?\s*){{1,3}}$", re.IGNORECASE)
_FIRST_MONEY = re.compile(rf"^(?P<amount>{_MONEY_BODY})", re.IGNORECASE)
# Номер страницы — тоже строка из одних цифр. Деньги себя выдают копейками
# или знаком валюты, и без такого признака строка суммой не считается.
_MONEY_MARKS = re.compile(rf"[.,]\d{{1,2}}|{_CURRENCY}", re.IGNORECASE)
_PAGE_NUMBER = re.compile(r"^\d{1,4}$")
_HEADER_WORDS = (
    "дата операции", "документ", "назначение платежа", "сумма операции",
    "российские рубли", "валюта",
)


def _amount_of_money_line(line: str) -> str | None:
    """Сумма, если строка состоит только из сумм (левая — в валюте счёта)."""
    if not _MONEY_ONLY.match(line) or not _MONEY_MARKS.search(line):
        return None
    first = _FIRST_MONEY.match(line)
    return first.group("amount").strip() if first else None


def _is_furniture(line: str) -> bool:
    """Шапка колонок или номер страницы посреди операции."""
    if _PAGE_NUMBER.match(line):
        return True
    rest = line.lower()
    for word in _HEADER_WORDS:
        rest = rest.replace(word, " ")
    return not rest.strip()


def _trailing_amounts(body: str) -> tuple[list[str], str]:
    """Суммы, напечатанные в конце строки, и остаток строки без них."""
    amounts: list[str] = []
    while len(amounts) < 2:
        match = _TRAILING_AMOUNT.search(body)
        if not match:
            break
        if not _is_money(match.group("amount"), match.group("currency")):
            break
        amounts.insert(0, match.group("amount").strip())
        body = body[: match.start()].strip()
    return amounts, body


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
    totals = dated_without_amount = 0
    # Знаки приходится решать вторым проходом: означает ли отсутствие минуса
    # приход, видно только по файлу целиком.
    rows: list[tuple] = []

    # Операция, у которой сумма ещё не встретилась: ждёт своих строк переноса.
    started: tuple[date, list[str], str] | None = None

    def keep(occurred_on: date, raw_amount: str, body: str, source: str) -> None:
        amount = parse_money(raw_amount)
        if amount is None or amount == 0:
            return
        description = re.sub(r"\s{2,}", " ", body).strip(" ·|-—")
        rows.append((occurred_on, amount, bool(_SIGNED.match(raw_amount)),
                     description, source))

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        date_match = _DATE_PREFIX.match(line)
        occurred_on = parse_statement_date(date_match.group(1)) if date_match else None

        if occurred_on is not None:
            if started:
                # Предыдущая операция так и не дождалась суммы.
                dated_without_amount += 1
                started = None
            if _SUMMARY.search(line) or _PERIOD_LINE.match(line):
                totals += 1
                continue
            body = line[date_match.end() :].strip()
            # With two trailing amounts the rightmost one is the running balance.
            amounts, body = _trailing_amounts(body)
            if amounts:
                keep(occurred_on, amounts[0], body, line)
            else:
                started = (occurred_on, [body] if body else [], line)
            continue

        if not started:
            continue

        money = _amount_of_money_line(line)
        if money is not None:
            began, parts, source = started
            keep(began, money, " ".join(parts), source)
            started = None
        elif not _is_furniture(line):
            started[1].append(line)

    if started:
        dated_without_amount += 1

    # Если где-то в файле минусы есть, банк помечает ими списания — и строка
    # без знака означает приход. Иначе зарплата в такой выписке становится
    # тратой: одна строка ошибается на две своих суммы.
    signs_used = any(signed for _, _, signed, _, _ in rows)
    unsigned = guessed = 0

    for occurred_on, amount, signed, description, line in rows:
        if not signed:
            unsigned += 1
            direction = _direction(description)
            if direction == 0:
                direction = 1 if signs_used else 0
                guessed += not signs_used
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

    # Вёрстка у каждого банка своя, и если она не поддалась, разбор не падает
    # — он тихо выдаёт горстку случайных строк. Полгода трат превращаются в
    # две операции, и это выглядит как настоящая история. Молчать нельзя:
    # строк с датами в файле видно, и несоответствие само себя выдаёт.
    if dated_without_amount > max(5, len(statement.operations) * 3):
        raise StatementParseError(
            f"Разбор не понял вёрстку: строк с датами {dated_without_amount + len(statement.operations)}, "
            f"а операций распозналось всего {len(statement.operations)}. "
            "Загрузить такую выписку — значит завести неверную историю трат. "
            "Выгрузите выписку в CSV или XLSX: там колонки на месте."
        )

    if not signs_used and guessed * 2 > len(statement.operations):
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

    stated = stated_totals(text.splitlines())
    statement.closing_balance = stated.get("closing")
    check_against_stated(statement, stated)

    period = _PERIOD.search(text)
    if period:
        statement.period_from = parse_statement_date(period.group(1)) or statement.period_from
        statement.period_to = parse_statement_date(period.group(2)) or statement.period_to

    if totals:
        statement.warnings.append(
            f"Строк с итогами и остатками пропущено: {totals} (это не операции)."
        )
    if unsigned and signs_used:
        statement.warnings.append(
            f"У {unsigned} операций знака не было — в этой выписке минусом "
            "помечены списания, поэтому они прочитаны как приход. Проверьте их."
        )
    elif unsigned:
        statement.warnings.append(
            f"У {unsigned} операций в PDF не было знака — направление определено "
            f"по описанию, из них наугад: {guessed}. Проверьте их на странице «Банки»."
        )
    statement.warnings.append("PDF разобран эвристически; CSV или XLSX точнее.")
    return statement
