import os

from mcp.server.mcpserver import MCPServer

from exchange.ews import EwsExchange
from exchange.graph import GraphExchange
from mcp_common.errors import IntegrationError
from mcp_common.runtime import READ, build_server, tool_result

_INSTRUCTIONS = (
    "Почта и календарь Exchange только на чтение. Ящик всегда указывай явно. "
    "По умолчанию возвращается тема и короткий preview, текст письма — только если его попросили. "
    "Письма не отправляются, встречи не создаются, правила пересылки не меняются."
)


def client_from_env() -> GraphExchange | EwsExchange:
    mode = os.environ.get("EXCHANGE_MODE", "graph").strip().lower()
    if mode == "graph":
        return GraphExchange.from_env()
    if mode == "ews":
        return EwsExchange.from_env()
    raise IntegrationError("EXCHANGE_MODE должен быть graph или ews")


def create_server(client: GraphExchange | EwsExchange | None = None) -> MCPServer:
    exo = client or client_from_env()
    server = build_server("exchange", "Exchange", _INSTRUCTIONS)

    @server.tool(annotations=READ)
    def exchange_ping() -> str:
        """Проверить доступ к Exchange."""
        return tool_result(exo.ping)

    @server.tool(annotations=READ)
    def exchange_find_users(query: str, limit: int = 20) -> str:
        """Найти людей по имени или почте. Письма этого вызова не читает."""
        return tool_result(lambda: exo.find_users(query, limit))

    @server.tool(annotations=READ)
    def exchange_list_folders(mailbox_id: str) -> str:
        """Папки ящика. mailbox_id — email или GUID пользователя."""
        return tool_result(lambda: exo.list_folders(mailbox_id))

    @server.tool(annotations=READ)
    def exchange_list_messages(mailbox_id: str, folder: str = "inbox", limit: int = 15, query: str = "") -> str:
        """Список писем: тема, отправитель, preview. Без тела письма."""
        return tool_result(lambda: exo.list_messages(mailbox_id, folder, limit, query))

    @server.tool(annotations=READ)
    def exchange_get_message(mailbox_id: str, message_id: str, include_body: bool = False) -> str:
        """Одно письмо. include_body=true добавляет текст, обрезанный по длине."""
        return tool_result(lambda: exo.get_message(mailbox_id, message_id, include_body))

    @server.tool(annotations=READ)
    def exchange_list_events(mailbox_id: str, start: str, end: str, limit: int = 20) -> str:
        """События календаря между start и end в ISO, например 2026-10-05T09:00:00."""
        return tool_result(lambda: exo.list_events(mailbox_id, start, end, limit))

    return server
