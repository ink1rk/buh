#!/usr/bin/env python3
"""Кто имеет право спрашивать ядро.

В ядре лежит личная переписка, а слушает оно на всех интерфейсах, поэтому
данные закрываются токеном. Петля остаётся открытой: бот и tg-user живут на
той же машине и ходят по 127.0.0.1 — им токен не нужен и незачем его хранить.

Статика Web UI данных не содержит и отдаётся всем: она сама спросит токен и
проверит его обычным запросом к API.
"""
import hmac
import os

from fastapi.responses import JSONResponse

from .config import config

LOOPBACK = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}

# Пути без данных: оболочка интерфейса и описание API.
PUBLIC_PREFIXES = ("/ui", "/static", "/favicon", "/docs", "/redoc", "/openapi.json")

HEADER = "x-assistant-token"
COOKIE = "assistant_token"


def token():
    """Окружение важнее собранной конфигурации: так же читается путь к БД."""
    value = os.environ.get("ASSISTANT_WEB_TOKEN")
    return (value if value is not None else config.web_token).strip()


def is_loopback(request):
    client = getattr(request, "client", None)
    return client is not None and client.host in LOOPBACK


def is_public(path):
    return path == "/" or path.startswith(PUBLIC_PREFIXES)


def presented(request):
    """Токен из заголовка, cookie или строки запроса — в таком порядке."""
    return (request.headers.get(HEADER)
            or request.cookies.get(COOKIE)
            or request.query_params.get("token")
            or "")


def accepts(presented_token):
    expected = token()
    if not expected:
        return True
    return hmac.compare_digest(str(presented_token), expected)


def guard(request):
    """None — можно пропустить, иначе готовый отказ."""
    if not token():
        return None
    if is_public(request.url.path) or is_loopback(request):
        return None
    if accepts(presented(request)):
        return None
    return JSONResponse({"error": "нужен токен доступа"}, status_code=401)


def mode():
    """Как сейчас закрыт доступ — показывается в /api/health и в интерфейсе."""
    if token():
        return {"auth": "token", "warning": None}
    return {"auth": "open",
            "warning": "Доступ к API открыт всем в сети: задайте ASSISTANT_WEB_TOKEN"}
