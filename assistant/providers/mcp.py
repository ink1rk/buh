#!/usr/bin/env python3
"""Вызов инструмента MCP как действие.

Читать данные ядро может напрямую через реестр: спросить у моста, сколько
человек спал, — это не поступок. А вот отправить напоминание на телефон или
включить свет — поступок, и он идёт общим путём: проверка, разрешение,
подтверждение, журнал. Тем же путём пойдут все сервисы, которые подключатся
к шлюзу потом.
"""
from core.actions import ActionProvider, ProviderError, ValidationError
from core.mcp import McpError


class McpActionProvider(ActionProvider):
    name = "mcp"
    action_types = ("mcp.tool.call",)

    def __init__(self, registry):
        self.registry = registry

    def validate(self, action):
        params = action.parameters or {}
        if not (params.get("tool") or "").strip():
            raise ValidationError("нужно имя инструмента")
        if not self.registry.names():
            raise ValidationError("ни один сервер MCP не подключён")
        server = params.get("server")
        if server and server not in self.registry.names():
            raise ValidationError(f"сервера MCP {server!r} нет")

    def execute(self, action):
        params = action.parameters or {}
        tool = params["tool"].strip()
        arguments = params.get("arguments") or {}
        server = params.get("server")
        try:
            result = (self.registry.call(server, tool, arguments) if server
                      else self.registry.call_tool(tool, arguments))
        except McpError as e:
            raise ProviderError(str(e), retryable=e.retryable) from e
        if result["is_error"]:
            # Инструмент отказал осмысленно — повторять нечего.
            raise ProviderError(f"{tool}: {result['text']}", retryable=False)
        return result
