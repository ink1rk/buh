#!/usr/bin/env python3
"""Wiring.

One place builds the object graph — bus, permissions, actions, notifications,
LLM registry, agents, context resolver, integrations — and hands it to whoever
needs it. Interfaces (HTTP API, Telegram) import the container, never each
other's internals.
"""
import threading
import time

from agents.communication import CommunicationAgent
from agents.personal import PersonalAgent
from domain.enrichment import Enricher
from providers.telegram import TelegramActionProvider

from . import audit, db
from .actions import ActionEngine
from .agents import AgentRegistry
from .config import config
from .context import ContextResolver
from .events import EventBus
from .integrations import (DatabaseIntegration, FinanceIntegration,
                           GatewayLLMIntegration, IntegrationRegistry,
                           LocalLLMIntegration, TelegramBotIntegration,
                           TelegramUserIntegration)
from .llm import GatewayProvider, LLMRegistry, LocalProvider
from .notifications import NotificationEngine
from .permissions import PermissionEngine


class Core:
    """The assembled system. Built once per process."""

    def __init__(self, skills=None, start_workers=True):
        db.migrate()

        self.bus = EventBus()
        audit.subscribe(self.bus)

        self.llm = LLMRegistry()
        self.permissions = PermissionEngine()
        self.notifications = NotificationEngine(self.bus)
        self.actions = ActionEngine(self.bus, self.permissions,
                                    providers=[TelegramActionProvider()],
                                    notifier=self.notifications)
        self.resolver = ContextResolver(permissions=self.permissions)
        self.enricher = Enricher(self.llm, self.bus)

        self.agents = AgentRegistry()
        self.communication = CommunicationAgent(self.llm, self.resolver)
        self.agents.register(self.communication)
        self.personal = None
        if skills is not None:
            self.personal = PersonalAgent(self.llm, skills)
            self.agents.register(self.personal, fallback=True)

        local, gateway = LocalProvider(), GatewayProvider()
        self.integrations = IntegrationRegistry(self.bus, [
            DatabaseIntegration(), LocalLLMIntegration(local),
            GatewayLLMIntegration(gateway), TelegramBotIntegration(),
            TelegramUserIntegration(), FinanceIntegration()])

        self._stop = threading.Event()
        if start_workers:
            self._start_workers()

    def attach_skills(self, skills):
        """Legacy skills arrive after import; register the generalist then."""
        self.personal = PersonalAgent(self.llm, skills)
        self.agents.register(self.personal, fallback=True)
        return self.personal

    # -- background housekeeping ----------------------------------------
    def _start_workers(self):
        threading.Thread(target=self._housekeeping, daemon=True,
                         name="core-housekeeping").start()

    def _housekeeping(self):
        from domain import commitments as commitments_mod
        while not self._stop.wait(60):
            try:
                self.actions.expire_stale()
                commitments_mod.mark_overdue(self.bus)
            except Exception as e:
                print("housekeeping failed:", e)
            try:
                if int(time.time()) % 300 < 60:
                    self.integrations.check()
            except Exception as e:
                print("integration check failed:", e)

    def health(self):
        checks = self.integrations.check()
        broken = [c for c in checks if c["status"] in ("ERROR",) and c["required"]]
        return {"status": "degraded" if broken else "ok",
                "integrations": checks,
                "agents": self.agents.describe(),
                "response_mode": config.response_mode,
                "assistant": config.assistant_name}

    def stop(self):
        self._stop.set()
        self.bus.stop()


_core = None
_lock = threading.Lock()


def get_core(skills=None):
    global _core
    if _core is None:
        with _lock:
            if _core is None:
                _core = Core(skills=skills)
    elif skills is not None and _core.personal is None:
        _core.attach_skills(skills)
    return _core
