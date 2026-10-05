import anyio
import pytest

from ad.client import ADClient, ADSettings, public_user
from ad.server import create_server
from mcp_common.errors import IntegrationError

SETTINGS = ADSettings(
    server="dc.example.local",
    port=636,
    use_ssl=True,
    starttls=False,
    tls_verify=True,
    bind_user="EXAMPLE\\svc",
    bind_password="bind-secret",
    base_dn="DC=example,DC=local",
)


class Entry:
    def __init__(self, dn: str, **attrs):
        self.entry_dn = dn
        self.entry_attributes_as_dict = attrs


class ScriptedConn:
    def __init__(self, pages: list[list[Entry]]):
        self.pages = list(pages)
        self.entries: list[Entry] = []
        self.filters: list[str] = []
        self.modifies: list[tuple] = []
        self.result = {"result": 0, "description": "success"}

    def search(self, search_base, search_filter, search_scope, attributes=None, size_limit=0):
        self.filters.append(search_filter)
        self.entries = self.pages.pop(0) if self.pages else []
        return True

    def modify(self, dn, changes):
        self.modifies.append((dn, changes))
        return True

    def unbind(self):
        return None


def user_entry(**extra):
    attrs = {
        "sAMAccountName": ["ivan"],
        "displayName": ["Иван"],
        "userAccountControl": ["512"],
        "lockoutTime": ["0"],
        "memberOf": [],
        "primaryGroupID": ["513"],
        "objectSid": ["S-1-5-21-1-2-3-1104"],
    }
    attrs.update(extra)
    return Entry("CN=Иван,OU=Users,DC=example,DC=local", **attrs)


def test_search_escapes_filter_injection():
    conn = ScriptedConn([[user_entry()]])
    client = ADClient(SETTINGS, connector=lambda: conn)
    found = client.search_users("*)(objectClass=*")
    assert found["count"] == 1
    assert r"\28objectClass=" in conn.filters[0]
    assert "(objectClass=*)" not in conn.filters[0]
    assert public_user({"dn": "CN=Иван,DC=example,DC=local", "sAMAccountName": ["ivan"]})["sam"] == "ivan"


def test_base_dn_outside_tree_is_rejected():
    client = ADClient(SETTINGS, connector=lambda: ScriptedConn([]))
    with pytest.raises(IntegrationError, match="AD_BASE_DN"):
        client.search_users("ivan", base_dn="DC=other,DC=local")


def test_tools_are_read_only():
    server = create_server(client=ADClient(SETTINGS, connector=lambda: ScriptedConn([])))
    tools = anyio.run(server.list_tools)
    names = {tool.name for tool in tools}
    assert {"ad_search_users", "ad_get_user", "ad_ping"} <= names
    assert not names & {"ad_unlock_user", "ad_set_user_enabled", "ad_reset_password", "ad_add_group_member"}
    assert all(tool.annotations is not None and tool.annotations.read_only_hint for tool in tools)
