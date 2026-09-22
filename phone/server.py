#!/usr/bin/env python3
"""HTTP-лицо моста.

Два входа с разными задачами и разными клиентами:

* `/v1/*` — приём данных с телефона. Ярлыки iOS умеют только обычный HTTP,
  поэтому здесь простые POST с токеном устройства в заголовке.
* `/mcp` — выдача данных наружу по Model Context Protocol. Сюда ходит ядро
  Джарвиса, Cursor или шлюз MCP; модель видит инструменты, а не таблицы.

Сервис слушает 127.0.0.1: наружу его выставляет nginx, который и отвечает
за TLS и за то, чтобы в мир смотрел только `/v1`.
"""
import hmac
import threading
import time

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse, Response

from . import ingest, insights, store, tools
from .config import config

PRUNE_INTERVAL = 6 * 3600


def create_app(testing=False):
    store.migrate()
    app = FastAPI(title="JARVIS phone bridge", version=tools.VERSION,
                  docs_url="/docs", redoc_url=None)
    if not testing:
        _start_housekeeping()

    # -- доступ ----------------------------------------------------------
    def bearer(request):
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.headers.get("x-assistant-token", "").strip()

    def allowed(request, expected):
        """Токен спрашивается всегда, откуда бы запрос ни пришёл.

        Поблажки «с самой машины можно без токена» здесь быть не может. Мост
        слушает только loopback, а наружу его выставляет обратный прокси —
        значит запрос с улицы приходит к нам с адресом 127.0.0.1 и поблажку
        получал бы даром, вместе со здоровьем и геопозицией владельца.

        Пустой токен в настройках поэтому закрывает вход, а не открывает.
        """
        if not expected:
            return False
        return hmac.compare_digest(bearer(request), expected)

    def device_of(request):
        token = (request.headers.get("x-device-token")
                 or bearer(request) or "").strip()
        return store.device_by_token(token)

    def deny(message, status=401):
        return JSONResponse({"error": message}, status_code=status)

    # -- здоровье --------------------------------------------------------
    @app.get("/health")
    def health():
        state = insights.bridge_state()
        return {"status": "degraded" if state["silent"] else "ok",
                "service": "jarvis-phone", "version": tools.VERSION,
                "devices": len(state["devices"]),
                "last_sync_at": state["last_sync_at"],
                "pending_outbox": state["pending_outbox"]}

    # -- устройства ------------------------------------------------------
    @app.post("/v1/devices/register")
    def register_device(request: Request, payload: dict = Body(default={})):
        """Токен устройства выдаётся один раз и больше нигде не показывается."""
        if not allowed(request, config.enroll_token):
            return deny("нужен PHONE_ENROLL_TOKEN")
        name = (payload.get("name") or "").strip()
        if not name:
            return deny("нужно имя устройства", 400)
        device, token = store.register_device(
            name=name, kind=(payload.get("kind") or "iphone").strip().lower(),
            model=payload.get("model") or "", os_version=payload.get("os_version") or "")
        return {"device": device, "token": token}

    @app.get("/v1/devices")
    def list_devices(request: Request):
        if not allowed(request, config.mcp_token):
            return deny("нужен токен")
        return insights.bridge_state()

    @app.post("/v1/devices/{device_id}/revoke")
    def revoke_device(device_id: str, request: Request):
        if not allowed(request, config.enroll_token):
            return deny("нужен PHONE_ENROLL_TOKEN")
        return {"revoked": store.revoke_device(device_id)}

    # -- приём данных ----------------------------------------------------
    def accept(request, handler, payload):
        device = device_of(request)
        if device is None:
            return deny("неизвестный токен устройства")
        result = handler(payload, device["id"])
        store.touch_device(device["id"])
        return result

    @app.post("/v1/sync")
    def sync(request: Request, payload: dict = Body(default={})):
        """Главный вход для ярлыка: всё накопившееся одним запросом.

        В ответе сразу уезжает очередь заданий — телефону не нужно ходить
        второй раз, а ярлыку не нужен второй шаг.
        """
        device = device_of(request)
        if device is None:
            return deny("неизвестный токен устройства")
        result = ingest.ingest_batch(payload, device["id"])
        result["outbox"] = store.take_outbox(limit=10, target=device["id"])
        return result

    @app.post("/v1/calls")
    def post_calls(request: Request, payload: dict = Body(default={})):
        return accept(request, lambda data, device_id: ingest.ingest_calls(
            data.get("calls", data.get("items", [])), device_id), payload)

    @app.post("/v1/messages")
    def post_messages(request: Request, payload: dict = Body(default={})):
        return accept(request, lambda data, device_id: ingest.ingest_messages(
            data.get("messages", data.get("items", [])), device_id), payload)

    @app.post("/v1/samples")
    def post_samples(request: Request, payload: dict = Body(default={})):
        return accept(request, lambda data, device_id: ingest.ingest_health(
            data.get("health", data), device_id), payload)

    @app.post("/v1/workouts")
    def post_workouts(request: Request, payload: dict = Body(default={})):
        return accept(request, lambda data, device_id: ingest.ingest_workouts(
            data.get("workouts", data.get("items", [])), device_id), payload)

    @app.post("/v1/state")
    def post_state(request: Request, payload: dict = Body(default={})):
        return accept(request, lambda data, device_id: ingest.ingest_state(
            data.get("state", data), device_id), payload)

    # -- задания для телефона --------------------------------------------
    @app.get("/v1/outbox")
    def get_outbox(request: Request, limit: int = 10):
        device = device_of(request)
        if device is None:
            return deny("неизвестный токен устройства")
        store.touch_device(device["id"])
        return {"items": store.take_outbox(limit=limit, target=device["id"])}

    @app.post("/v1/outbox/ack")
    def ack_outbox(request: Request, payload: dict = Body(default={})):
        if device_of(request) is None:
            return deny("неизвестный токен устройства")
        return {"done": store.ack_outbox(payload.get("ids") or [],
                                         payload.get("results") or {})}

    @app.get("/v1/summary")
    def summary(request: Request, day: str = None):
        """То же, что видит модель, но глазами — для отладки ярлыков."""
        if not allowed(request, config.mcp_token):
            return deny("нужен токен")
        return insights.today(day)

    # -- MCP --------------------------------------------------------------
    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        origin = request.headers.get("origin")
        if origin and origin not in config.allowed_origins:
            # Защита от DNS rebinding: браузер со случайной страницы не должен
            # уметь читать здоровье владельца.
            return JSONResponse({"error": "origin не разрешён"}, status_code=403)
        if not allowed(request, config.mcp_token):
            return deny("нужен токен MCP")
        try:
            message = await request.json()
        except ValueError:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "не разобрать JSON"}},
                status_code=400)
        reply = tools.server.handle(message, headers=dict(request.headers),
                                    transport="http")
        if reply.body is None:
            return Response(status_code=reply.status)
        return JSONResponse(reply.body, status_code=reply.status)

    @app.get("/mcp")
    @app.delete("/mcp")
    def mcp_legacy_transport():
        """Ни потока событий, ни сессий: протокол 2026-07-28 их отменил."""
        return JSONResponse({"error": "только POST"}, status_code=405)

    return app


def _start_housekeeping():
    def loop():
        while True:
            time.sleep(PRUNE_INTERVAL)
            try:
                store.prune()
            except Exception as e:                  # noqa: BLE001
                print("prune failed:", e)

    threading.Thread(target=loop, daemon=True, name="phone-prune").start()
