"""Разбор выписки: средние по полным месяцам и советы с цифрами.

Текущий месяц в середине ещё не месяц, и первый оборванный кусок выписки
тоже. Считать «норму» по ним — значит принять обрывок за характер трат.
Переводы себе в траты не входят: это не жизнь, а движение между счетами.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from app.connectors.base import RawOperation
from app.connectors.categorize import classify
from app.schemas.analytics import ReviewNote, ReviewPlace, ReviewSlice, StatementReview
from app.services.categories import category_color, category_name
from app.services.ledger import is_income, is_spending

MONTHS_NOM = (
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)
MONTHS_PREP = (
    "", "январе", "феврале", "марте", "апреле", "мае", "июне",
    "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
)

# Эквайринг пишет одно и то же место десятком строк. Для разбора это один
# контрагент, иначе «Делимобиль» распадается на терминалы и пропадает из совета.
PLACES = (
    ("delimobil", "Делимобиль"),
    ("citydrive", "Ситидрайв"),
    ("belkacar", "Белкакар"),
    ("mos.transport", "Московский транспорт"),
    ("mosgortrans", "Московский транспорт"),
    ("vkusvill", "ВкусВилл"),
    ("magnoliya", "Магнолия"),
    ("winelab", "Винлаб"),
    ("epgu", "Госуслуги"),
    ("платформе ozon", "Ozon"),
    ("ozon", "Ozon"),
)

_CITIES = {
    "moscow", "moskva", "moskow", "sochi", "odinczovo", "odintsovo",
    "ryazan", "konakovo", "domodedovo", "nemchinovka", "vniissok",
    "stupino", "rybnoe", "ekaterinovka", "n.novgorod",
}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def rub(value: float) -> str:
    return f"{abs(value):,.0f} ₽".replace(",", " ")


def _pct(share: float) -> str:
    return f"{share * 100:.0f}%"


def _month_phrase(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        word = "месяц"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "месяца"
    else:
        word = "месяцев"
    return f"{n} {word}"


def _looks_like_vkusvill(text: str) -> bool:
    compact = text.lower().replace(" ", "")
    return compact.startswith("vv_") or " vv_" in f" {text.lower()}"


def place_name(merchant: str, description: str = "") -> str:
    text = f"{merchant or ''} {description or ''}".lower()
    if _looks_like_vkusvill(text):
        return "ВкусВилл"
    for needle, name in PLACES:
        if needle in text:
            return name
    raw = (merchant or description or "").strip()
    raw = re.sub(r"\s+(RU|RUS)$", "", raw, flags=re.I)
    parts = raw.split()
    while len(parts) >= 2 and parts[-1].lower().strip(".") in _CITIES:
        parts.pop()
    tidy = re.sub(r"[_.]+", " ", " ".join(parts))
    tidy = re.sub(r"\s+\d+$", "", re.sub(r"\s+", " ", tidy)).strip()
    return (tidy or "без названия")[:60]


def effective_category(category: str, merchant: str, description: str, amount: float) -> str:
    """Известное место не оставляем в «прочем», даже если банк так подписал."""
    stored = (category or "other").strip().lower() or "other"
    if stored not in {"other", ""}:
        return stored
    op = RawOperation(
        occurred_on=date.today(),
        amount=amount if amount < 0 else -abs(amount or 1),
        merchant=merchant or "",
        description=description or "",
    )
    guessed, _tx_type = classify(op)
    return guessed if guessed and guessed != "other" else "other"


def _complete_months(dates: list[date], today: date) -> list[tuple[int, int]]:
    if not dates:
        return []
    first = min(dates)
    keys = sorted({(d.year, d.month) for d in dates})
    # Текущий месяц ещё не кончился. Первый месяц выписки, если файл
    # начинается после 7-го числа, тоже обрывок — в среднее его не берём.
    # Последний прошедший месяц оставляем, даже если покупка была в начале:
    # тихий конец месяца и оборванный файл по дате не отличить, а выкидывать
    # целый месяц из-за этого нельзя.
    keys = [key for key in keys if key != (today.year, today.month)]
    if keys and (first.year, first.month) == keys[0] and first.day > 7:
        keys = keys[1:]
    return keys


def _period_label(keys: list[tuple[int, int]]) -> str:
    start, end = keys[0], keys[-1]
    left = f"{MONTHS_NOM[start[1]]} {start[0]}"
    right = f"{MONTHS_NOM[end[1]]} {end[0]}"
    return left if start == end else f"{left} — {right}"


def build_review(transactions, today: date | None = None) -> StatementReview:
    today = today or date.today()
    rows = list(transactions)
    if not rows:
        return StatementReview(
            headline="Выписка ещё не загружена — разбирать нечего.",
        )

    dates = [t.occurred_on for t in rows]
    keys = _complete_months(dates, today)
    if len(keys) < 2:
        return StatementReview(
            headline="В выписке меньше двух полных месяцев. "
            "Разбор появится, когда будет с чем сравнить средние.",
        )

    keyset = set(keys)
    n = len(keys)
    earned = refunds = spent = transfers = 0.0
    by_cat: dict[str, float] = defaultdict(float)
    by_place: dict[str, float] = defaultdict(float)
    place_months: dict[str, set[tuple[int, int]]] = defaultdict(set)
    place_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    month_spent: dict[tuple[int, int], float] = defaultdict(float)
    seen_from: date | None = None
    seen_to: date | None = None

    for t in rows:
        key = (t.occurred_on.year, t.occurred_on.month)
        if key not in keyset:
            continue
        seen_from = t.occurred_on if seen_from is None or t.occurred_on < seen_from else seen_from
        seen_to = t.occurred_on if seen_to is None or t.occurred_on > seen_to else seen_to
        if is_income(t):
            if (t.category or "") == "refunds":
                refunds += t.amount
            else:
                earned += t.amount
            continue
        if t.transaction_type == "transfer":
            transfers += abs(t.amount)
            continue
        if not is_spending(t):
            continue
        amount = abs(t.amount)
        spent += amount
        month_spent[key] += amount
        category = effective_category(t.category, getattr(t, "merchant", ""), t.description, t.amount)
        by_cat[category] += amount
        place = place_name(getattr(t, "merchant", "") or "", t.description or "")
        by_place[place] += amount
        place_months[place].add(key)
        place_cat[place][category] += amount

    net_spent = max(spent - refunds, 0.0)
    left = earned - net_spent
    rate = (left / earned) if earned > 0 else None

    categories = []
    for category, amount in sorted(by_cat.items(), key=lambda item: -item[1]):
        if amount <= 0:
            continue
        categories.append(
            ReviewSlice(
                category=category,
                name=category_name(category),
                amount=round(amount, 2),
                per_month=round(amount / n, 2),
                share=round(amount / spent, 4) if spent else 0,
                color=category_color(category),
            )
        )
    categories = [item for item in categories if item.share >= 0.01][:8]

    places = []
    for name, amount in sorted(by_place.items(), key=lambda item: -item[1]):
        cats = place_cat[name]
        main = max(cats, key=cats.get) if cats else "other"
        places.append(
            ReviewPlace(
                name=name,
                amount=round(amount, 2),
                per_month=round(amount / n, 2),
                share=round(amount / spent, 4) if spent else 0,
                months=len(place_months[name]),
                category=main,
            )
        )
    other_names = [place.name for place in places if place.category == "other"][:3]
    places = places[:8]

    advice = _advice(
        n=n,
        keys=keys,
        earned=earned / n,
        spent=net_spent / n,
        left=left / n,
        rate=rate,
        transfers=transfers / n,
        categories=categories,
        places=places,
        other_names=other_names,
        month_spent=month_spent,
    )
    tone = "warning" if rate is not None and rate < 0.1 else (
        "positive" if rate is not None and rate >= 0.2 else "neutral"
    )
    headline = advice[0].title if advice else ""
    if advice:
        advice[0] = advice[0].model_copy(update={"tone": tone})

    return StatementReview(
        ready=True,
        headline=headline,
        period_from=seen_from.isoformat() if seen_from else None,
        period_to=seen_to.isoformat() if seen_to else None,
        months=n,
        earned_month=round(earned / n, 2),
        spent_month=round(net_spent / n, 2),
        refunds_month=round(refunds / n, 2),
        left_month=round(left / n, 2),
        savings_rate=round(rate, 4) if rate is not None else None,
        transfers_month=round(transfers / n, 2),
        categories=categories,
        counterparties=places,
        advice=advice,
    )


def _advice(
    n: int,
    keys: list[tuple[int, int]],
    earned: float,
    spent: float,
    left: float,
    rate: float | None,
    transfers: float,
    categories: list[ReviewSlice],
    places: list[ReviewPlace],
    other_names: list[str],
    month_spent: dict[tuple[int, int], float],
) -> list[ReviewNote]:
    notes: list[ReviewNote] = []
    window = _period_label(keys)
    if left >= 0:
        title = f"В среднем остаётся {rub(left)} в месяц"
    else:
        title = f"В среднем траты выше дохода на {rub(left)}"
    rate_txt = _pct(rate) if rate is not None else "доход не виден"
    notes.append(
        ReviewNote(
            title=title,
            body=(
                f"По {_month_phrase(n)} ({window}): приходит {rub(earned)}, "
                f"на жизнь уходит {rub(spent)}. Это {rate_txt} дохода."
            ),
        )
    )

    if transfers >= 15_000 and (left <= 0 or transfers >= left * 0.6):
        notes.append(
            ReviewNote(
                title=f"Переводы забирают {rub(transfers)} в месяц",
                body=(
                    "Со счёта уходит ещё эта сумма переводами. В расходах на жизнь её нет. "
                    "Если это копилка — заведите её целью, иначе эти деньги пропадают из картины."
                ),
                tone="warning",
            )
        )

    top = categories[0] if categories else None
    top_place = places[0] if places else None
    mentioned_place = ""
    if top and top.share >= 0.18:
        body = f"В среднем {rub(top.per_month)} в месяц, {_pct(top.share)} всех трат."
        if (
            top_place
            and top_place.category == top.category
            and top.amount > 0
            and top_place.amount >= top.amount * 0.5
        ):
            body += (
                f" Большая часть — {top_place.name}: {rub(top_place.per_month)} в месяц."
            )
            mentioned_place = top_place.name
        body += " Смотреть на экономию стоит отсюда."
        notes.append(
            ReviewNote(
                title=f"«{_cap(top.name)}» — {_pct(top.share)} трат",
                body=body,
                tone="warning" if top.share >= 0.3 else "neutral",
            )
        )

    if top_place and top_place.name != mentioned_place and top_place.share >= 0.12:
        notes.append(
            ReviewNote(
                title=f"{top_place.name}: {rub(top_place.per_month)} в месяц",
                body=(
                    f"{_pct(top_place.share)} всех трат, "
                    f"в {top_place.months} из {_month_phrase(n)}."
                ),
                tone="warning" if top_place.share >= 0.2 else "neutral",
            )
        )

    other = next((item for item in categories if item.category == "other"), None)
    if other and other.share >= 0.15:
        body = f"Это {rub(other.per_month)} в месяц без категории."
        if other_names:
            body += f" Крупнейшее: {', '.join(other_names)}."
        notes.append(
            ReviewNote(
                title=f"«Прочее» всё ещё {_pct(other.share)}",
                body=body,
                tone="neutral",
            )
        )

    last = keys[-1]
    last_spent = month_spent.get(last, 0.0)
    if spent > 0 and last_spent >= spent * 1.25:
        notes.append(
            ReviewNote(
                title=f"В {MONTHS_PREP[last[1]]} {last[0]} траты выше обычных",
                body=(
                    f"{rub(last_spent)} против средних {rub(spent)} "
                    f"— на {(last_spent / spent - 1) * 100:.0f}%."
                ),
                tone="warning",
            )
        )
    elif spent > 0 and 0 < last_spent <= spent * 0.75:
        notes.append(
            ReviewNote(
                title=f"В {MONTHS_PREP[last[1]]} {last[0]} траты ниже обычных",
                body=f"{rub(last_spent)} против средних {rub(spent)}.",
                tone="positive",
            )
        )

    return notes[:6]


def reclassify_unclear(sync_conn) -> int:
    """Уже загруженным операциям проставить категорию известного места.

    Банк подписал кассу как «прочее». Повторно выписку не грузим: правим
    только строки, которые и так ничего не значили.
    """
    try:
        rows = sync_conn.exec_driver_sql(
            "SELECT id, amount, merchant, description FROM transactions "
            "WHERE lower(coalesce(category, '')) IN ('other', '') AND amount < 0"
        ).fetchall()
    except Exception:
        return 0
    changed = 0
    for row_id, amount, merchant, description in rows:
        category = effective_category("other", merchant or "", description or "", float(amount))
        if category and category != "other":
            sync_conn.exec_driver_sql(
                "UPDATE transactions SET category = ? WHERE id = ?",
                (category, row_id),
            )
            changed += 1
    return changed
