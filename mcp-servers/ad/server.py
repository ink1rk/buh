from mcp.server.mcpserver import MCPServer

from ad.client import ADClient
from mcp_common.runtime import READ, WRITE, build_server, require_write, tool_result

_INSTRUCTIONS = (
    "Каталог Active Directory через сервисную учётную запись. "
    "Ищи людей, группы и компьютеры по короткому фрагменту имени, не выгружай домен целиком. "
    "Изменяющие инструменты работают только при MCP_ENABLE_WRITES=true. "
    "Встроенные администраторы и группы вроде Domain Admins этим сервером не меняются. "
    "Пароли и хэши не запрашиваются и не возвращаются: новый пароль в ответ не повторяй."
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

    @server.tool(annotations=WRITE)
    def ad_unlock_user(identity: str) -> str:
        """Снять блокировку входа (lockoutTime=0). Запись, не для привилегированных учёток."""
        require_write()
        return tool_result(lambda: ad.unlock_user(identity))

    @server.tool(annotations=WRITE)
    def ad_set_user_enabled(identity: str, enabled: bool) -> str:
        """Включить или отключить учётную запись. Запись, не для привилегированных учёток."""
        require_write()
        return tool_result(lambda: ad.set_user_enabled(identity, enabled))

    @server.tool(annotations=WRITE)
    def ad_add_group_member(user_identity: str, group_identity: str) -> str:
        """Добавить пользователя в обычную группу. Привилегированные группы запрещены."""
        require_write()
        return tool_result(lambda: ad.add_group_member(user_identity, group_identity))

    @server.tool(annotations=WRITE)
    def ad_remove_group_member(user_identity: str, group_identity: str) -> str:
        """Убрать пользователя из обычной группы. Привилегированные группы запрещены."""
        require_write()
        return tool_result(lambda: ad.remove_group_member(user_identity, group_identity))

    @server.tool(annotations=WRITE)
    def ad_reset_password(identity: str, new_password: str, must_change: bool = True) -> str:
        """Сбросить пароль по LDAPS. Пароль в ответе не возвращается и его не нужно повторять."""
        require_write()
        return tool_result(lambda: ad.reset_password(identity, new_password, must_change))

    return server
