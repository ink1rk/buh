import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ad.client import ADClient, ADSettings, public_user, sid_rid
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


def test_sid_rid_bytes_and_string():
    assert sid_rid("S-1-5-21-9-512") == 512
    blob = bytes([1, 1, 0, 0, 0, 0, 0, 5]) + (512).to_bytes(4, "little")
    assert sid_rid(blob) == 512


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


def test_reset_requires_ldaps_and_blocks_privileged_group():
    plain = ADSettings(
        server="dc.example.local",
        port=389,
        use_ssl=False,
        starttls=False,
        tls_verify=False,
        bind_user="EXAMPLE\\svc",
        bind_password="x",
        base_dn="DC=example,DC=local",
    )
    client = ADClient(plain, connector=lambda: ScriptedConn([]))
    with pytest.raises(IntegrationError, match="LDAPS"):
        client.reset_password("ivan", "correct-horse-battery")

    user = user_entry(memberOf=["CN=Domain Admins,CN=Users,DC=example,DC=local"])
    group = Entry(
        "CN=Domain Admins,CN=Users,DC=example,DC=local",
        sAMAccountName=["Domain Admins"],
        objectSid=["S-1-5-21-1-2-3-512"],
    )
    conn = ScriptedConn([[user], [group]])
    secure = ADClient(SETTINGS, connector=lambda: conn)
    with pytest.raises(IntegrationError, match="привилегирован"):
        secure.reset_password("ivan", "correct-horse-battery")
    assert conn.modifies == []


def test_unlock_writes_lockout_time():
    conn = ScriptedConn([[user_entry()]])
    client = ADClient(SETTINGS, connector=lambda: conn)
    result = client.unlock_user("ivan")
    assert result["unlocked"] is True
    assert conn.modifies[0][1]["lockoutTime"][0][1] == ["0"]


def test_password_is_not_returned_and_protected_group_add_is_blocked():
    conn = ScriptedConn([[user_entry()]])
    client = ADClient(SETTINGS, connector=lambda: conn)
    result = client.reset_password("ivan", "correct-horse-battery", must_change=True)
    assert "correct-horse-battery" not in str(result)
    encoded = conn.modifies[0][1]["unicodePwd"][0][1][0]
    assert encoded == '"correct-horse-battery"'.encode("utf-16-le")

    admin = Entry("CN=Domain Admins,CN=Users,DC=example,DC=local", sAMAccountName=["Domain Admins"], objectSid=["S-1-5-21-1-2-3-512"])
    conn = ScriptedConn([[user_entry()], [admin]])
    client = ADClient(SETTINGS, connector=lambda: conn)
    with pytest.raises(IntegrationError, match="привилегирован"):
        client.add_group_member("ivan", "Domain Admins")


def test_write_tools_are_off_until_enabled(monkeypatch):
    monkeypatch.delenv("MCP_ENABLE_WRITES", raising=False)
    server = create_server(client=ADClient(SETTINGS, connector=lambda: ScriptedConn([[user_entry()]])))
    with pytest.raises(ToolError, match="MCP_ENABLE_WRITES"):
        anyio.run(server.call_tool, "ad_unlock_user", {"identity": "ivan"})

    monkeypatch.setenv("MCP_ENABLE_WRITES", "true")
    conn = ScriptedConn([[user_entry()]])
    server = create_server(client=ADClient(SETTINGS, connector=lambda: conn))
    result = anyio.run(server.call_tool, "ad_unlock_user", {"identity": "ivan"})
    assert result.is_error is False
    assert "unlocked" in result.content[0].text
