from mcp.server.mcpserver import MCPServer

from ad.client import ADClient
from mcp_common.runtime import READ, build_server, tool_result

_INSTRUCTIONS = (
    "Каталог Active Directory только на чтение. "
    "Ищи людей, группы и компьютеры по короткому фрагменту имени, не выгружай домен целиком. "
    "Пароли и хэши не запрашиваются и не возвращаются. Учётные записи этим сервером не меняются."
)


def create_server(client: ADClient | None = None) -> MCPServer:
    ad = client or ADClient.from_env()
    server = build_server("ad", "Active Directory", _INSTRUCTIONS)

    @server.tool(annotations=READ)
    def ad_ping() -> str:
        """Проверить bind к контроллеру домена."""
        return tool_result(ad.ping)

    @server.tool(annotations=READ)
    def ad_search_users(query: str, limit: int = 25, base_dn: str = "") -> str:
        """Найти пользователей по samAccountName, UPN, имени или почте.

        query — фрагмент от 2 символов. base_dn пустой означает AD_BASE_DN.
        """
        return tool_result(lambda: ad.search_users(query, limit, base_dn or None))

    @server.tool(annotations=READ)
    def ad_get_user(identity: str) -> str:
        """Карточка пользователя. identity — samAccountName, UPN или DN."""
        return tool_result(lambda: ad.get_user(identity))

    @server.tool(annotations=READ)
    def ad_search_groups(query: str, limit: int = 25, base_dn: str = "") -> str:
        """Найти группы по cn или samAccountName."""
        return tool_result(lambda: ad.search_groups(query, limit, base_dn or None))

    @server.tool(annotations=READ)
    def ad_group_members(identity: str, limit: int = 50) -> str:
        """Участники группы по memberOf. identity — имя группы или DN."""
        return tool_result(lambda: ad.group_members(identity, limit))

    @server.tool(annotations=READ)
    def ad_search_computers(query: str, limit: int = 25, base_dn: str = "") -> str:
        """Найти компьютеры по cn или DNS-имени."""
        return tool_result(lambda: ad.search_computers(query, limit, base_dn or None))

    @server.tool(annotations=READ)
    def ad_list_ous(limit: int = 50, base_dn: str = "") -> str:
        """Список подразделений (OU) под базой поиска."""
        return tool_result(lambda: ad.list_ous(limit, base_dn or None))

    return server
