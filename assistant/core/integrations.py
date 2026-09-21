#!/usr/bin/env python3
"""Integration registry and health.

Every external system the assistant talks to registers here. The core asks an
integration whether it is alive; it never learns how that system works. When
one goes down the rest keeps running, the dashboard shows ERROR, and agents can
see that a capability is currently unavailable.
"""
import time
from enum import Enum

import httpx

from . import db
from .config import config
from .events import E


class Status(str, Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DISABLED = "DISABLED"


class Integration:
    name = "base"
    type = "service"
    required = False

    def configured(self):
        return True

    def health_check(self):
        """Return (Status, detail)."""
        raise NotImplementedError

    def connect(self):
        return True

    def disconnect(self):
        return True


class HttpIntegration(Integration):
    """Most integrations are just an HTTP endpoint that must answer."""
    url = ""
    method = "GET"
    timeout = 10
    use_proxy = False

    def health_check(self):
        if not self.configured():
            return Status.NOT_CONFIGURED, "нет настроек"
        try:
            kwargs = {"timeout": self.timeout, "trust_env": False}
            if self.use_proxy and config.telegram.proxy:
                kwargs["proxy"] = config.telegram.proxy
            with httpx.Client(**kwargs) as client:
                response = client.request(self.method, self.url)
            if response.status_code >= 500:
                return Status.ERROR, f"HTTP {response.status_code}"
            if response.status_code >= 400:
                return Status.DEGRADED, f"HTTP {response.status_code}"
            return Status.CONNECTED, "ok"
        except Exception as e:
            return Status.ERROR, f"{type(e).__name__}: {e}"


class DatabaseIntegration(Integration):
    name = "database"
    type = "storage"
    required = True

    def health_check(self):
        try:
            db.one("SELECT 1")
            counts = {
                "actions": db.one("SELECT COUNT(*) c FROM actions")["c"],
                "memories": db.one("SELECT COUNT(*) c FROM memories")["c"],
                "contacts": db.one("SELECT COUNT(*) c FROM contacts")["c"],
            }
            return Status.CONNECTED, ", ".join(f"{k}: {v}" for k, v in counts.items())
        except Exception as e:
            return Status.ERROR, str(e)


class LocalLLMIntegration(Integration):
    name = "llm.local"
    type = "llm"
    required = True

    def __init__(self, provider):
        self.provider = provider

    def health_check(self):
        try:
            info = self.provider.health()
            return Status.CONNECTED, f"{info.get('model')}"
        except Exception as e:
            return Status.ERROR, f"{type(e).__name__}: {e}"


class GatewayLLMIntegration(LocalLLMIntegration):
    name = "llm.gateway"

    def configured(self):
        return bool(config.llm.gateway_key)

    def health_check(self):
        if not self.configured():
            return Status.NOT_CONFIGURED, "нет GATEWAY_KEY"
        return super().health_check()


class TelegramBotIntegration(HttpIntegration):
    name = "telegram.bot"
    type = "messaging"
    use_proxy = True
    required = True

    def configured(self):
        return bool(config.telegram.bot_token)

    @property
    def url(self):
        return f"https://api.telegram.org/bot{config.telegram.bot_token}/getMe"


class TelegramUserIntegration(HttpIntegration):
    name = "telegram.user"
    type = "messaging"

    @property
    def url(self):
        return f"{config.telegram.user_service_url}/health"

    def health_check(self):
        status, detail = super().health_check()
        if status is not Status.CONNECTED:
            return status, detail
        try:
            with httpx.Client(timeout=10, trust_env=False) as client:
                data = client.get(self.url).json()
            if not data.get("authorized"):
                return Status.DEGRADED, "сессия не авторизована"
            return Status.CONNECTED, "авторизован"
        except Exception as e:
            return Status.ERROR, str(e)


class FinanceIntegration(HttpIntegration):
    name = "finance"
    type = "finance"

    @property
    def url(self):
        return f"{config.finance_api}/networth"


class IntegrationRegistry:
    def __init__(self, bus=None, integrations=None):
        self.bus = bus
        self.integrations = list(integrations or [])
        self._last: dict = {}

    def register(self, integration):
        self.integrations.append(integration)
        return integration

    def check(self, name=None):
        results = []
        for integration in self.integrations:
            if name and integration.name != name:
                continue
            try:
                status, detail = integration.health_check()
            except Exception as e:
                status, detail = Status.ERROR, str(e)
            results.append({"name": integration.name, "type": integration.type,
                            "status": status.value, "detail": detail,
                            "checked_at": time.time(), "required": integration.required})
            self._persist(integration, status, detail)
        return results

    def _persist(self, integration, status, detail):
        previous = self._last.get(integration.name)
        self._last[integration.name] = status.value
        db.execute(
            "INSERT INTO integrations(name, type, status, detail, checked_at, enabled)"
            " VALUES(?,?,?,?,?,1) ON CONFLICT(name) DO UPDATE SET status=excluded.status,"
            " detail=excluded.detail, checked_at=excluded.checked_at",
            (integration.name, integration.type, status.value, str(detail)[:500],
             time.time()))
        if self.bus and previous and previous != status.value:
            self.bus.emit(E.INTEGRATION_STATUS_CHANGED,
                          {"integration": integration.name, "from": previous,
                           "to": status.value, "detail": str(detail)[:300]},
                          source="integrations")

    def status(self):
        rows = db.query("SELECT * FROM integrations ORDER BY name")
        return [dict(r) for r in rows] or self.check()

    def available(self, name):
        row = db.one("SELECT status FROM integrations WHERE name=?", (name,))
        return bool(row and row["status"] == Status.CONNECTED.value)
