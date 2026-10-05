import json

from mcp.server.mcpserver import MCPServer

from mcp_common.errors import IntegrationError
from mcp_common.runtime import READ, WRITE, build_server, require_write, tool_result
from onec.client import OneCClient

_INSTRUCTIONS = (
    "1С:Предприятие через OData опубликованной базы. "
    "Имена сущностей как в $metadata, например Catalog_Контрагенты или "
    "Document_РеализацияТоваровУслуг. Сначала посмотри список сущностей, "
    "потом читай с $top. Создание, изменение и проведение требуют MCP_ENABLE_WRITES=true."
)


def _object(payload_json: str) -> dict:
    if not payload_json.strip():
        raise IntegrationError("Нужен JSON-объект")
    try:
        data = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise IntegrationError("payload_json не является JSON") from exc
    if not isinstance(data, dict):
        raise IntegrationError("payload_json должен быть объектом")
    return data


def _query(query_json: str) -> dict:
    if not query_json.strip():
        return {}
    try:
        data = json.loads(query_json)
    except json.JSONDecodeError as exc:
        raise IntegrationError("query_json не является JSON") from exc
    if not isinstance(data, dict) or any(not isinstance(key, str) for key in data):
        raise IntegrationError("query_json должен быть объектом со строковыми ключами")
    return data


def create_server(client: OneCClient | None = None) -> MCPServer:
    onec = client or OneCClient.from_env()
    server = build_server("onec", "1C", _INSTRUCTIONS)

    @server.tool(annotations=READ)
    def onec_ping() -> str:
        """Проверить OData публикации 1С."""
        return tool_result(onec.ping)

    @server.tool(annotations=READ)
    def onec_list_entities() -> str:
        """Имена наборов OData: справочники, документы, регистры."""
        return tool_result(onec.list_entities)

    @server.tool(annotations=READ)
    def onec_list(
        entity: str,
        filter: str = "",
        select: str = "",
        orderby: str = "",
        top: int = 20,
        skip: int = 0,
        expand: str = "",
    ) -> str:
        """Выборка объектов. filter — выражение OData, например Description eq 'Ромашка'."""
        return tool_result(lambda: onec.list_objects(entity, filter, select, orderby, top, skip, expand))

    @server.tool(annotations=READ)
    def onec_get(entity: str, guid: str, select: str = "") -> str:
        """Один объект по GUID."""
        return tool_result(lambda: onec.get_object(entity, guid, select))

    @server.tool(annotations=READ)
    def onec_count(entity: str, filter: str = "") -> str:
        """Количество объектов, можно с $filter."""
        return tool_result(lambda: onec.count(entity, filter))

    @server.tool(annotations=WRITE)
    def onec_create(entity: str, payload_json: str) -> str:
        """Создать объект. payload_json — JSON с реквизитами и табличными частями."""
        require_write()
        return tool_result(lambda: onec.create(entity, _object(payload_json)))

    @server.tool(annotations=WRITE)
    def onec_update(entity: str, guid: str, payload_json: str) -> str:
        """Изменить реквизиты объекта по GUID."""
        require_write()
        return tool_result(lambda: onec.update(entity, guid, _object(payload_json)))

    @server.tool(annotations=WRITE)
    def onec_post_document(entity: str, guid: str) -> str:
        """Провести документ."""
        require_write()
        return tool_result(lambda: onec.post_document(entity, guid))

    @server.tool(annotations=WRITE)
    def onec_unpost_document(entity: str, guid: str) -> str:
        """Отменить проведение документа."""
        require_write()
        return tool_result(lambda: onec.unpost_document(entity, guid))

    @server.tool(annotations=WRITE)
    def onec_call_http(path: str, method: str = "GET", query_json: str = "", payload_json: str = "") -> str:
        """Вызвать опубликованный HTTP-сервис внутри ONEC_HTTP_SERVICE_URL.

        path относительный, например hs/exchange/status не нужен целиком:
        если база URL уже кончается на /hs/exchange, path — status.
        Методы кроме GET требуют MCP_ENABLE_WRITES=true.
        """
        if method.upper() != "GET":
            require_write()

        def run():
            payload = _object(payload_json) if payload_json.strip() else None
            return onec.call_http(path, method, _query(query_json), payload)

        return tool_result(run)

    return server
