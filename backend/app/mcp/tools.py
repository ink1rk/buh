"""Tool surface exposed over MCP.

Kept free of any MCP SDK import so the contract and the handlers can be tested
directly; `server.py` is only a transport adapter over this module.

Handlers aggregate before returning. An assistant asking "сколько я потратил на
кофе" should get a total and a category breakdown, not 500 raw rows to add up.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.mcp.client import FinanceApiClient, FinanceApiError

MAX_STATEMENT_BYTES = 15 * 1024 * 1024
MAX_ROWS_RETURNED = 50


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[FinanceApiClient, dict[str, Any]], Awaitable[Any]]
    # Читающий по умолчанию неверно: забытая пометка на пишущем инструменте
    # молча открыла бы ему путь чтения, минуя подтверждение у вызывающего.
    writes: bool = False


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# --- handlers ---------------------------------------------------------------


async def _overview(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    dashboard = await client.get("/dashboard")
    if not isinstance(dashboard, dict):
        return dashboard
    balances = dashboard.get("balances") or {}
    return {
        "balances": balances,
        "health_score": dashboard.get("health_score"),
        "net_worth": dashboard.get("net_worth"),
        "insights": dashboard.get("insights"),
        "streak_days": dashboard.get("streak_days"),
        "profile": dashboard.get("profile"),
    }


async def _accounts(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    accounts = await client.get("/accounts")
    if not isinstance(accounts, list):
        return accounts
    return {
        "total": _money(sum(_money(a.get("balance")) for a in accounts)),
        "accounts": [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "type": a.get("account_type"),
                "balance": _money(a.get("balance")),
                "currency": a.get("currency"),
            }
            for a in accounts
        ],
    }


async def _search_transactions(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    rows = await client.get("/transactions", {"limit": 500})
    if not isinstance(rows, list):
        return rows

    query = str(args.get("query") or "").strip().lower()
    category = str(args.get("category") or "").strip().lower()
    tx_type = str(args.get("transaction_type") or "").strip().lower()
    since = _parse_date(args.get("since"))
    until = _parse_date(args.get("until"))
    min_amount = args.get("min_amount")
    max_amount = args.get("max_amount")

    matched = []
    for row in rows:
        occurred_on = _parse_date(row.get("occurred_on"))
        if since and (occurred_on is None or occurred_on < since):
            continue
        if until and (occurred_on is None or occurred_on > until):
            continue
        if category and category not in str(row.get("category", "")).lower():
            continue
        if tx_type and tx_type != str(row.get("transaction_type", "")).lower():
            continue
        if query:
            haystack = " ".join(
                str(row.get(field, "")) for field in ("description", "merchant", "category", "tags")
            ).lower()
            if query not in haystack:
                continue
        amount = _money(row.get("amount"))
        if min_amount is not None and abs(amount) < abs(float(min_amount)):
            continue
        if max_amount is not None and abs(amount) > abs(float(max_amount)):
            continue
        matched.append(row)

    spent = _money(sum(-_money(r.get("amount")) for r in matched if _money(r.get("amount")) < 0))
    earned = _money(sum(_money(r.get("amount")) for r in matched if _money(r.get("amount")) > 0))
    by_category: dict[str, float] = {}
    for row in matched:
        amount = _money(row.get("amount"))
        if amount < 0:
            key = str(row.get("category") or "other")
            by_category[key] = _money(by_category.get(key, 0.0) + -amount)

    limit = int(args.get("limit") or MAX_ROWS_RETURNED)
    limit = max(1, min(limit, MAX_ROWS_RETURNED))
    return {
        "count": len(matched),
        "total_spent": spent,
        "total_received": earned,
        "net": _money(earned - spent),
        "spent_by_category": dict(
            sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        ),
        "transactions": [
            {
                "id": r.get("id"),
                "date": r.get("occurred_on"),
                "amount": _money(r.get("amount")),
                "category": r.get("category"),
                "description": r.get("description"),
                "merchant": r.get("merchant"),
                "type": r.get("transaction_type"),
                "source": r.get("source"),
            }
            for r in matched[:limit]
        ],
        "truncated": len(matched) > limit,
    }


async def _add_transaction(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    text = str(args.get("text") or "").strip()
    if not text:
        raise FinanceApiError("Нужен текст операции, например «-450 кофе»")
    return await client.post("/transactions/quick", {"text": text})


async def _analytics(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    days = int(args.get("days") or 90)
    days = max(7, min(days, 365))
    return await client.get("/analytics/bundle", {"days": days})


async def _forecast(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/analytics/forecast")


async def _review(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/analytics/review")


async def _net_worth(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/networth")


async def _goals(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/goals")


async def _budget(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/budget")


async def _calendar(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/calendar")


async def _analyze_purchase(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    item = str(args.get("item") or "").strip()
    price = args.get("price")
    if not item or price is None:
        raise FinanceApiError("Нужны название покупки и цена")
    return await client.post("/ai/purchase/analyze", {"item": item, "price": float(price)})


async def _bank_connections(client: FinanceApiClient, _args: dict[str, Any]) -> Any:
    return await client.get("/connections")


async def _bank_imports(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    connection_id = int(args["connection_id"])
    return await client.get(f"/connections/{connection_id}/imports")


async def _import_statement(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    connection_id = int(args["connection_id"])
    raw_path = str(args.get("file_path") or "").strip()
    if not raw_path:
        raise FinanceApiError("Укажите путь к файлу выписки")

    path = Path(os.path.expanduser(raw_path)).resolve()
    if not path.is_file():
        raise FinanceApiError(f"Файл не найден: {path}")
    size = path.stat().st_size
    if size > MAX_STATEMENT_BYTES:
        raise FinanceApiError(f"Файл слишком большой ({size // 1024 // 1024} МБ), максимум 15 МБ")

    return await client.upload(
        f"/connections/{connection_id}/statement", path.name, path.read_bytes()
    )


async def _sync_connection(client: FinanceApiClient, args: dict[str, Any]) -> Any:
    connection_id = int(args["connection_id"])
    payload: dict[str, Any] = {}
    since = _parse_date(args.get("since"))
    until = _parse_date(args.get("until"))
    if since:
        payload["since"] = since.isoformat()
    if until:
        payload["until"] = until.isoformat()
    if not payload:
        payload["since"] = (date.today() - timedelta(days=90)).isoformat()
    return await client.post(f"/connections/{connection_id}/sync", payload)


# --- registry ---------------------------------------------------------------

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_financial_overview",
        description=(
            "Сводка финансов: балансы по счётам, доходы и расходы месяца, "
            "Financial Health Score, капитал и проактивные инсайты. "
            "Начинайте с этого инструмента, когда нужен общий контекст."
        ),
        input_schema=_schema({}),
        handler=_overview,
    ),
    ToolSpec(
        name="list_accounts",
        description="Список счетов с балансами и суммарным остатком.",
        input_schema=_schema({}),
        handler=_accounts,
    ),
    ToolSpec(
        name="search_transactions",
        description=(
            "Поиск операций с агрегатами: сколько потрачено и получено, разбивка по "
            "категориям и сами операции. Фильтры: текст, категория, тип, период, "
            "диапазон суммы. Используйте для вопросов вида «сколько ушло на кофе "
            "в этом месяце»."
        ),
        input_schema=_schema(
            {
                "query": {"type": "string", "description": "Текст в описании, мерчанте или тегах"},
                "category": {"type": "string", "description": "Категория, например groceries"},
                "transaction_type": {
                    "type": "string",
                    "enum": ["income", "expense", "transfer", "investment", "debt", "savings"],
                },
                "since": {"type": "string", "description": "Дата начала, YYYY-MM-DD"},
                "until": {"type": "string", "description": "Дата конца, YYYY-MM-DD"},
                "min_amount": {"type": "number", "description": "Минимальная сумма по модулю"},
                "max_amount": {"type": "number", "description": "Максимальная сумма по модулю"},
                "limit": {
                    "type": "integer",
                    "description": f"Сколько операций вернуть, максимум {MAX_ROWS_RETURNED}",
                },
            }
        ),
        handler=_search_transactions,
    ),
    ToolSpec(
        name="add_transaction",
        description=(
            "Записать операцию обычным текстом: «-450 кофе», «+180000 зарплата». "
            "Парсер сам определит сумму, категорию и тип. Если уверенность низкая, "
            "операция вернётся как черновик с needs_confirmation."
        ),
        input_schema=_schema(
            {"text": {"type": "string", "description": "Например «-1200 пятерочка»"}},
            ["text"],
        ),
        handler=_add_transaction,
        writes=True,
    ),
    ToolSpec(
        name="get_spending_analytics",
        description="Аналитика за период: категории, тренды, денежный поток.",
        input_schema=_schema(
            {"days": {"type": "integer", "description": "Глубина периода, 7–365, по умолчанию 90"}}
        ),
        handler=_analytics,
    ),
    ToolSpec(
        name="get_forecast",
        description="Прогноз по среднему полных месяцев выписки.",
        input_schema=_schema({}),
        handler=_forecast,
    ),
    ToolSpec(
        name="get_financial_review",
        description=(
            "Разбор выписки: средний доход и траты по полным месяцам, "
            "крупные категории и места, советы с цифрами."
        ),
        input_schema=_schema({}),
        handler=_review,
    ),
    ToolSpec(
        name="get_net_worth",
        description="Чистый капитал: активы, обязательства, динамика.",
        input_schema=_schema({}),
        handler=_net_worth,
    ),
    ToolSpec(
        name="list_goals",
        description="Финансовые цели с прогрессом и вероятностью достижения.",
        input_schema=_schema({}),
        handler=_goals,
    ),
    ToolSpec(
        name="get_budget",
        description="Месячный план расходов: конверты, факт, остаток.",
        input_schema=_schema({}),
        handler=_budget,
    ),
    ToolSpec(
        name="list_calendar",
        description="Финансовый календарь: платежи, зарплата, счета из писем.",
        input_schema=_schema({}),
        handler=_calendar,
    ),
    ToolSpec(
        name="analyze_purchase",
        description=(
            "Оценить покупку: доля капитала, часы работы, влияние на цели. "
            "Отвечает, стоит ли покупать."
        ),
        input_schema=_schema(
            {
                "item": {"type": "string", "description": "Что покупаем"},
                "price": {"type": "number", "description": "Цена в рублях"},
            },
            ["item", "price"],
        ),
        handler=_analyze_purchase,
    ),
    ToolSpec(
        name="list_bank_connections",
        description=(
            "Подключённые банки: статус, привязанный счёт, дата последней синхронизации "
            "и число загруженных операций."
        ),
        input_schema=_schema({}),
        handler=_bank_connections,
    ),
    ToolSpec(
        name="import_bank_statement",
        description=(
            "Загрузить файл выписки банка (CSV, XLSX или PDF) в подключение. "
            "Повторная загрузка за пересекающийся период не создаёт дублей."
        ),
        input_schema=_schema(
            {
                "connection_id": {"type": "integer", "description": "ID подключения"},
                "file_path": {
                    "type": "string",
                    "description": "Путь к файлу выписки на этой машине",
                },
            },
            ["connection_id", "file_path"],
        ),
        handler=_import_statement,
        writes=True,
    ),
    ToolSpec(
        name="sync_bank_connection",
        description=(
            "Синхронизировать подключение через Открытое API банка. "
            "Работает только если банк выдал доступ; иначе используйте import_bank_statement."
        ),
        input_schema=_schema(
            {
                "connection_id": {"type": "integer"},
                "since": {"type": "string", "description": "YYYY-MM-DD"},
                "until": {"type": "string", "description": "YYYY-MM-DD"},
            },
            ["connection_id"],
        ),
        handler=_sync_connection,
        writes=True,
    ),
    ToolSpec(
        name="list_bank_imports",
        description="История импортов по подключению: что загрузилось, что задублировалось.",
        input_schema=_schema({"connection_id": {"type": "integer"}}, ["connection_id"]),
        handler=_bank_imports,
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {tool.name: tool for tool in TOOLS}


async def call_tool(
    client: FinanceApiClient,
    name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        known = ", ".join(sorted(TOOLS_BY_NAME))
        raise FinanceApiError(f"Неизвестный инструмент «{name}». Доступны: {known}")
    return await tool.handler(client, arguments or {})
