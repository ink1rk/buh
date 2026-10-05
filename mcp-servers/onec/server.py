import json

from mcp.server.mcpserver import MCPServer

from mcp_common.errors import IntegrationError
from mcp_common.runtime import READ, build_server, tool_result
from onec.client import OneCClient

_INSTRUCTIONS = (
    "1С:Предприятие только на чтение, через OData опубликованной базы. "
    "Имена сущностей как в $metadata, например Catalog_Контрагенты или "
    "Document_РеализацияТоваровУслуг. Сначала посмотри список сущностей, "
    "потом читай с $top. Объекты не создаются, не меняются и не проводятся."
)


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

    @server.tool(annotations=READ)
    def onec_call_http(path: str, query_json: str = "") -> str:
        """GET опубликованного HTTP-сервиса внутри ONEC_HTTP_SERVICE_URL.

        path относительный: если базовый URL уже кончается на /hs/exchange, path — status.
        """
        return tool_result(lambda: onec.call_http(path, _query(query_json)))

    return server
