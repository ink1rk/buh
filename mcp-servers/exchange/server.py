import os

from mcp.server.mcpserver import MCPServer

from exchange.ews import EwsExchange
from exchange.graph import GraphExchange
from mcp_common.errors import IntegrationError
from mcp_common.runtime import READ, WRITE, build_server, require_write, tool_result

_INSTRUCTIONS = (
    "Почта и календарь Exchange. Ящик всегда указывай явно. "
    "По умолчанию возвращается тема и короткий preview, текст письма — только если его попросили. "
    "Отправка и создание встреч требуют MCP_ENABLE_WRITES=true. "
    "Не выгружай ящики пачкой и не создавай правила пересылки."
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

    @server.tool(annotations=WRITE)
    def exchange_send_mail(mailbox_id: str, to: list[str], subject: str, body: str) -> str:
        """Отправить письмо от указанного ящика. Нужны права Mail.Send или EWS."""
        require_write()
        return tool_result(lambda: exo.send_mail(mailbox_id, to, subject, body))

    @server.tool(annotations=READ)
    def exchange_list_events(mailbox_id: str, start: str, end: str, limit: int = 20) -> str:
        """События календаря между start и end в ISO, например 2026-10-05T09:00:00."""
        return tool_result(lambda: exo.list_events(mailbox_id, start, end, limit))

    @server.tool(annotations=WRITE)
    def exchange_create_event(
        mailbox_id: str,
        subject: str,
        start: str,
        end: str,
        body: str = "",
        timezone: str = "UTC",
    ) -> str:
        """Создать встречу. Для Москвы в Graph укажи timezone Russian Standard Time."""
        require_write()
        return tool_result(lambda: exo.create_event(mailbox_id, subject, start, end, body, timezone))

    return server
