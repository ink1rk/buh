"""Map bank-side operations onto the app's category / transaction_type vocabulary.

Precedence: explicit operation wording (cashback, transfer, ATM) → MCC code →
the bank's own category label → merchant name → fall back to the amount sign.
Wording wins over MCC because a cashback payout can carry the MCC of the shop
that triggered it.
"""

from __future__ import annotations

from app.connectors.base import RawOperation

# ISO 18245 merchant category codes, grouped onto the categories this app uses.
MCC_CATEGORIES: dict[str, str] = {
    # Groceries & food retail
    "5411": "groceries", "5412": "groceries", "5422": "groceries", "5441": "groceries",
    "5451": "groceries", "5462": "groceries", "5499": "groceries", "5921": "groceries",
    # Eating out
    "5812": "restaurants", "5813": "restaurants", "5814": "cafe",
    # Transport
    "4111": "transport", "4112": "transport", "4121": "transport", "4131": "transport",
    "4457": "transport", "5541": "transport", "5542": "transport", "7523": "transport",
    "5511": "transport", "5533": "transport", "7538": "transport", "7542": "transport",
    # Travel
    "3000": "travel", "4511": "travel", "4722": "travel", "7011": "travel", "7012": "travel",
    # Health
    "5912": "health", "5122": "health", "8011": "health", "8021": "health", "8031": "health",
    "8042": "health", "8049": "health", "8062": "health", "8071": "health", "8099": "health",
    "7997": "health", "7941": "health", "7991": "health",
    # Clothes
    "5611": "clothes", "5621": "clothes", "5631": "clothes", "5651": "clothes",
    "5661": "clothes", "5691": "clothes", "5699": "clothes", "5948": "clothes",
    "7296": "clothes",
    # Gadgets & electronics
    "5045": "gadgets", "5722": "gadgets", "5732": "gadgets", "5734": "gadgets", "5735": "gadgets",
    # Home
    "5200": "home", "5211": "home", "5231": "home", "5251": "home", "5261": "home",
    "5712": "home", "5713": "home", "5714": "home", "5718": "home", "5719": "home",
    # Utilities & telecom
    "4814": "utilities", "4812": "utilities", "4816": "subscriptions", "4821": "utilities",
    "4899": "utilities", "4900": "utilities",
    # Entertainment & subscriptions
    "5815": "subscriptions", "5816": "subscriptions", "5817": "subscriptions",
    "5818": "subscriptions", "7832": "entertainment", "7841": "entertainment",
    "7922": "entertainment", "7929": "entertainment", "7933": "entertainment",
    "7994": "entertainment", "7996": "entertainment", "7998": "entertainment",
    # Education
    "5942": "education", "5943": "education", "8211": "education", "8220": "education",
    "8241": "education", "8244": "education", "8249": "education", "8299": "education",
    # Beauty
    "5977": "beauty", "7230": "beauty", "7297": "beauty", "7298": "beauty",
    # Kids & pets
    "5641": "kids", "5945": "kids", "5995": "pets", "0742": "pets",
    # Cash & financial
    "6010": "cash", "6011": "cash", "6012": "transfers", "6051": "transfers",
    "6536": "transfers", "6537": "transfers", "6538": "transfers", "4829": "transfers",
    "6211": "investments", "6300": "insurance", "6381": "insurance",
    # Generic retail / marketplaces
    "5262": "shopping", "5310": "shopping", "5311": "shopping", "5399": "shopping",
    "5964": "shopping", "5965": "shopping", "5969": "shopping", "5999": "shopping",
    "7278": "services", "7299": "services", "7399": "services",
    # Government
    "9211": "taxes", "9222": "taxes", "9223": "taxes", "9311": "taxes", "9399": "taxes",
}

# Bank-supplied category labels (Ozon and most Russian banks use similar wording).
BANK_CATEGORY_ALIASES: dict[str, str] = {
    "супермаркеты": "groceries", "продукты": "groceries", "продукты и супермаркеты": "groceries",
    "кафе и рестораны": "restaurants", "рестораны": "restaurants", "кафе": "cafe",
    "фастфуд": "cafe", "кофейни": "cafe",
    "транспорт": "transport", "такси": "transport", "автомобиль": "transport",
    "азс": "transport", "топливо": "transport", "каршеринг": "transport",
    "путешествия": "travel", "авиабилеты": "travel", "отели": "travel", "жд билеты": "travel",
    "здоровье": "health", "аптеки": "health", "медицина": "health", "спорт": "health",
    "фитнес": "health",
    "одежда и обувь": "clothes", "одежда": "clothes", "обувь": "clothes",
    "техника": "gadgets", "электроника": "gadgets", "цифровая техника": "gadgets",
    "дом и ремонт": "home", "дом": "home", "мебель": "home", "строительство": "home",
    "жкх": "utilities", "коммунальные платежи": "utilities", "связь": "utilities",
    "связь и интернет": "utilities", "интернет": "utilities", "мобильная связь": "utilities",
    "развлечения": "entertainment", "кино": "entertainment", "игры": "entertainment",
    "подписки": "subscriptions", "цифровые сервисы": "subscriptions",
    "образование": "education", "книги": "education", "курсы": "education",
    "красота": "beauty", "косметика": "beauty",
    "дети": "kids", "детские товары": "kids", "питомцы": "pets", "зоотовары": "pets",
    "наличные": "cash", "снятие наличных": "cash",
    "переводы": "transfers", "перевод": "transfers",
    "зарплата": "salary", "доход": "salary",
    "кэшбэк": "cashback", "кешбэк": "cashback", "бонусы": "cashback",
    "проценты": "interest", "проценты на остаток": "interest",
    "инвестиции": "investments", "страхование": "insurance",
    "налоги": "taxes", "налоги и сборы": "taxes", "штрафы": "taxes",
    "маркетплейсы": "shopping", "покупки": "shopping", "прочее": "other",
}

# Merchant name fragments → category. Checked as substrings, longest first.
MERCHANT_CATEGORIES: dict[str, str] = {
    "пятерочка": "groceries", "пятёрочка": "groceries", "перекресток": "groceries",
    "перекрёсток": "groceries", "магнит": "groceries", "вкусвилл": "groceries",
    "лента": "groceries", "ашан": "groceries", "дикси": "groceries", "метро cash": "groceries",
    "самокат": "groceries", "яндекс лавка": "groceries", "купер": "groceries",
    "окей": "groceries", "спар": "groceries", "азбука вкуса": "groceries",
    "яндекс еда": "cafe", "delivery": "cafe", "додо": "cafe", "kfc": "cafe",
    "вкусно и точка": "cafe", "бургер": "cafe", "шоколадница": "cafe", "старбакс": "cafe",
    "cofix": "cafe", "кофикс": "cafe", "one price coffee": "cafe", "surf coffee": "cafe",
    "яндекс go": "transport", "яндекс такси": "transport", "ситимобил": "transport",
    "uber": "transport", "метрополитен": "transport", "мосгортранс": "transport",
    "тройка": "transport", "ржд": "transport", "лукойл": "transport", "газпромнефть": "transport",
    "роснефть": "transport", "делимобиль": "transport", "белкакар": "transport",
    "аэрофлот": "travel", "победа": "travel", "s7": "travel", "booking": "travel",
    "островок": "travel", "ostrovok": "travel", "туту": "travel",
    "аптека": "health", "apteka": "health", "ригла": "health", "горздрав": "health",
    "здравсити": "health", "инвитро": "health", "сберздоровье": "health",
    "wildberries": "shopping", "вайлдберриз": "shopping", "ozon": "shopping",
    "озон": "shopping", "яндекс маркет": "shopping", "aliexpress": "shopping",
    "детский мир": "kids", "спортмастер": "clothes", "zara": "clothes", "uniqlo": "clothes",
    "gloria jeans": "clothes", "lamoda": "clothes", "ламода": "clothes",
    "dns": "gadgets", "днс": "gadgets", "мвидео": "gadgets", "м.видео": "gadgets",
    "эльдорадо": "gadgets", "citilink": "gadgets", "ситилинк": "gadgets", "re:store": "gadgets",
    "леруа": "home", "икеа": "home", "ikea": "home", "оби": "home", "петрович": "home",
    "hoff": "home", "вседоммебель": "home", "максидом": "home",
    "netflix": "subscriptions", "spotify": "subscriptions", "яндекс плюс": "subscriptions",
    "кинопоиск": "subscriptions", "vk музыка": "subscriptions", "youtube": "subscriptions",
    "apple": "subscriptions", "google": "subscriptions", "steam": "entertainment",
    "мтс": "utilities", "билайн": "utilities", "мегафон": "utilities", "теле2": "utilities",
    "tele2": "utilities", "ростелеком": "utilities", "мосэнерго": "utilities",
    "водоканал": "utilities", "жкх": "utilities", "мосводоканал": "utilities",
    "литрес": "education", "читай-город": "education", "skillbox": "education",
    "нетология": "education", "coursera": "education", "яндекс практикум": "education",
    "летуаль": "beauty", "рив гош": "beauty", "золотое яблоко": "beauty",
    "фнс": "taxes", "налог": "taxes", "гибдд": "taxes", "госуслуги": "taxes",
    "тинькофф инвестиции": "investments", "бкс": "investments", "втб инвестиции": "investments",
}

# Эквайринг присылает название места латиницей и без пробелов в привычных
# местах: «MAGNIT MM TYUSHINO MOSCOW RU», «Mos.Transport», «IMP_BELKACAR». По
# русскому списку выше такие строки не опознаются, и год трат оседал в
# «прочем»: каршеринг и продукты — это две самые большие статьи расходов.
LATIN_MERCHANT_CATEGORIES: dict[str, str] = {
    "magnit": "groceries", "magnoliya": "groceries", "pyaterochka": "groceries",
    "perekrestok": "groceries", "perekryostok": "groceries", "vkusvill": "groceries",
    "diksi": "groceries", "dixy": "groceries", "auchan": "groceries", "okey": "groceries",
    "azbuka vkusa": "groceries", "verniy": "groceries", "vernyj": "groceries",
    "krasnoe i beloe": "groceries", "bristol": "groceries", "samokat": "groceries",
    "lavka": "groceries", "kuper": "groceries", "globus": "groceries",
    "mos.transport": "transport", "mosgortrans": "transport", "metropoliten": "transport",
    "troika": "transport", "delimobil": "transport", "belkacar": "transport",
    "citydrive": "transport", "yandex.drive": "transport", "yandex drive": "transport",
    "yandex.taxi": "transport", "yandex go": "transport", "citymobil": "transport",
    "lukoil": "transport", "gazpromneft": "transport", "rosneft": "transport",
    "tatneft": "transport", "neftmagistral": "transport", "parkovka": "transport",
    "parking": "transport", "toll roads": "transport", "rzhd": "transport",
    "aeroflot": "travel", "pobeda": "travel", "utair": "travel", "ostrovok": "travel",
    "apteka": "health", "aptechn": "health", "rigla": "health", "gorzdrav": "health",
    "zdravcity": "health", "invitro": "health", "gemotest": "health",
    "cafe": "cafe", "kafe": "cafe", "coffee": "cafe", "kofe": "cafe", "kofejnya": "cafe",
    "pizza": "cafe", "pizzeria": "cafe", "sushi": "cafe", "shaurma": "cafe",
    "stolovaya": "cafe", "dodo": "cafe", "vkusno i tochka": "cafe", "tanuki": "restaurants",
    "restoran": "restaurants",
    "wildberries": "shopping", "aliexpress": "shopping", "megamarket": "shopping",
    "detmir": "kids", "detskij mir": "kids",
    "sportmaster": "clothes", "lamoda": "clothes", "gloria jeans": "clothes",
    "eldorado": "gadgets", "citilink": "gadgets", "mvideo": "gadgets",
    "leroy": "home", "petrovich": "home", "maksidom": "home", "vseinstrumenti": "home",
    "letual": "beauty", "letoile": "beauty", "rive gauche": "beauty",
    "zolotoe yabloko": "beauty",
    "beeline": "utilities", "megafon": "utilities", "tele2": "utilities",
    "rostelecom": "utilities", "mosenergo": "utilities", "mosvodokanal": "utilities",
    "fines pdd": "taxes", "gibdd": "taxes", "shtraf": "taxes", "nalog": "taxes",
    "litres": "education", "chitaj-gorod": "education", "skillbox": "education",
}

MERCHANT_CATEGORIES.update(LATIN_MERCHANT_CATEGORIES)

# Wording that identifies the nature of the operation regardless of merchant.
# (fragment, category, transaction_type)
WORDING_RULES: tuple[tuple[str, str, str], ...] = (
    # Банк пишет и «кэшбэк», и «кешбек»: без второго написания выплата
    # лояльности числилась просто прочим доходом.
    ("кэшбэк", "cashback", "income"),
    ("кешбэк", "cashback", "income"),
    ("кешбек", "cashback", "income"),
    ("кэшбек", "cashback", "income"),
    ("cashback", "cashback", "income"),
    ("процент на остаток", "interest", "income"),
    ("проценты на остаток", "interest", "income"),
    ("выплата процентов", "interest", "income"),
    ("зарплата", "salary", "income"),
    ("заработная плата", "salary", "income"),
    ("аванс", "salary", "income"),
    ("премия", "salary", "income"),
    ("возврат покупки", "refunds", "income"),
    ("возврат товара", "refunds", "income"),
    ("возврат оплаты", "refunds", "income"),
    ("снятие наличных", "cash", "expense"),
    ("выдача наличных", "cash", "expense"),
    ("внесение наличных", "cash", "income"),
    ("пополнение вклада", "savings", "savings"),
    ("пополнение накопительного", "savings", "savings"),
    ("на накопительный счет", "savings", "savings"),
    ("перевод между своими", "transfers", "transfer"),
    ("между своими счетами", "transfers", "transfer"),
    ("перевод себе", "transfers", "transfer"),
    ("комиссия", "fees", "expense"),
    ("обслуживание карты", "fees", "expense"),
    ("штраф", "taxes", "expense"),
    ("налог", "taxes", "expense"),
)

def _haystack(op: RawOperation) -> str:
    return f"{op.description} {op.merchant} {op.bank_category}".lower().replace("ё", "е")


def classify(op: RawOperation) -> tuple[str, str]:
    """Return `(category, transaction_type)` for a bank operation."""
    text = _haystack(op)
    incoming = op.amount > 0

    for fragment, category, tx_type in WORDING_RULES:
        if fragment.replace("ё", "е") in text:
            # Keep the direction the money actually moved — a refund of a
            # cashback, for instance, is still an outgoing operation.
            if tx_type in {"income", "expense"}:
                tx_type = "income" if incoming else "expense"
            return category, tx_type

    category = MCC_CATEGORIES.get(op.mcc.strip().zfill(4)) if op.mcc else None

    if not category and op.bank_category:
        label = op.bank_category.strip().lower().replace("ё", "е")
        category = BANK_CATEGORY_ALIASES.get(label)
        if not category:
            category = next(
                (cat for name, cat in BANK_CATEGORY_ALIASES.items() if name in label),
                None,
            )

    if not category:
        for name in sorted(MERCHANT_CATEGORIES, key=len, reverse=True):
            if name in text:
                category = MERCHANT_CATEGORIES[name]
                break

    if "перевод" in text and (not category or category == "transfers"):
        return "transfers", "transfer"

    if not category:
        category = "other_income" if incoming else "other"

    return category, "income" if incoming else "expense"
