"""Ядро как клиент MCP: обе эпохи протокола, реестр и действия."""
import json

import httpx
import pytest

from core.config import McpServer
from core.mcp import LATEST, McpClient, McpError, McpRegistry
from test_pipeline import core  # noqa: F401

TOOLS = [{"name": "phone_today", "title": "Сегодня", "description": "сводка дня"},
         {"name": "phone_push", "description": "задание телефону"}]


class FakeServer:
    """MCP-сервер новой эпохи: без сессий, с проверкой заголовков."""

    def __init__(self, tools=TOOLS, versions=(LATEST,)):
        self.tools = tools
        self.versions = list(versions)
        self.requests = []

    def transport(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request):
        body = json.loads(request.content)
        self.requests.append((dict(request.headers), body))
        method, params = body.get("method"), body.get("params") or {}
        version = request.headers.get("mcp-protocol-version")
        if version not in self.versions:
            return self.error(body, -32022, "Unsupported protocol version",
                              {"supported": self.versions, "requested": version},
                              status=400)
        if request.headers.get("mcp-method") != method:
            return self.error(body, -32020, "заголовок не совпадает с телом", status=400)
        return self.dispatch(body, method, params)

    def dispatch(self, body, method, params):
        if method == "server/discover":
            return self.ok(body, {"supportedVersions": self.versions,
                                  "capabilities": {"tools": {}}})
        if method == "tools/list":
            return self.ok(body, {"tools": self.tools})
        if method == "tools/call":
            return self.ok(body, {"content": [{"type": "text", "text": "Сон 7 ч"}],
                                  "structuredContent": {"sleep": 7},
                                  "isError": params.get("name") == "phone_boom"})
        if method == "resources/read":
            return self.ok(body, {"contents": [{"uri": params["uri"],
                                                "text": "{\"ok\": true}"}]})
        return self.error(body, -32601, "нет такого метода", status=404)

    def ok(self, body, result):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"),
                                         "result": {**result, "resultType": "complete"}})

    def error(self, body, code, message, data=None, status=200):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return httpx.Response(status, json={"jsonrpc": "2.0", "id": body.get("id"),
                                            "error": error})


class LegacyServer(FakeServer):
    """Сервер прошлой эпохи: рукопожатие, сессия, никаких заголовков."""

    def __init__(self, tools=TOOLS):
        super().__init__(tools, versions=["2025-06-18"])
        self.session = "sess-1"
        self.initialized = False

    def handle(self, request):
        body = json.loads(request.content)
        self.requests.append((dict(request.headers), body))
        method, params = body.get("method"), body.get("params") or {}
        if method == "server/discover":
            return self.error(body, -32601, "нет такого метода", status=404)
        if method == "initialize":
            self.initialized = True
            response = self.ok(body, {"protocolVersion": "2025-06-18",
                                      "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "старый", "version": "0.9"}})
            response.headers["Mcp-Session-Id"] = self.session
            return response
        if body.get("id") is None:
            return httpx.Response(202)
        if request.headers.get("mcp-session-id") != self.session:
            return self.error(body, -32600, "нет сессии", status=400)
        return self.dispatch(body, method, params)


def client(server, token=""):
    return McpClient("phone", "http://bridge/mcp", token=token,
                     transport=server.transport())


# --- новая эпоха ---------------------------------------------------------
def test_a_modern_server_needs_no_handshake():
    server = FakeServer()

    tools = client(server).tools()

    assert [t["name"] for t in tools] == ["phone_today", "phone_push"]
    assert [body["method"] for _, body in server.requests] == [
        "server/discover", "tools/list"]


def test_every_request_carries_its_version_and_route():
    """Ради этого протокол и сделали stateless: шлюз читает заголовки."""
    server = FakeServer()
    client(server).call("phone_today", {"day": "2026-09-21"})

    headers, body = server.requests[-1]
    assert headers["mcp-protocol-version"] == LATEST
    assert headers["mcp-method"] == "tools/call"
    assert headers["mcp-name"] == "phone_today"
    assert body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == LATEST


def test_a_tool_answer_splits_into_text_and_data():
    answer = client(FakeServer()).call("phone_today")

    assert answer["text"] == "Сон 7 ч"
    assert answer["data"] == {"sleep": 7}
    assert answer["is_error"] is False


def test_a_tool_can_report_its_own_failure():
    answer = client(FakeServer()).call("phone_boom")

    assert answer["is_error"] is True


def test_a_token_is_sent_when_the_bridge_asks_for_one():
    server = FakeServer()
    client(server, token="secret").tools()

    assert server.requests[0][0]["authorization"] == "Bearer secret"


def test_resources_come_back_as_text():
    assert json.loads(client(FakeServer()).read("phone://today")) == {"ok": True}


# --- прошлая эпоха -------------------------------------------------------
def test_an_old_server_gets_a_handshake():
    server = LegacyServer()

    tools = client(server).tools()

    assert [t["name"] for t in tools] == ["phone_today", "phone_push"]
    assert server.initialized
    methods = [body["method"] for _, body in server.requests]
    assert methods == ["server/discover", "initialize", "notifications/initialized",
                       "tools/list"]


def test_the_session_of_an_old_server_is_remembered():
    server = LegacyServer()
    connection = client(server)
    connection.tools()
    connection.call("phone_today")

    headers, _ = server.requests[-1]
    assert headers["mcp-session-id"] == "sess-1"


def test_the_handshake_happens_once():
    server = LegacyServer()
    connection = client(server)
    connection.tools(refresh=True)
    connection.tools(refresh=True)

    assert [body["method"] for _, body in server.requests].count("initialize") == 1


def test_a_server_that_refuses_the_new_version_names_the_old_ones():
    """Отказ по версии — это не «сервер сломан», а «говори по-другому»."""
    server = FakeServer(versions=["2025-06-18"])
    server.handle = LegacyServer.handle.__get__(server)
    server.session = "sess-1"
    server.initialized = False

    assert client(server).tools()


# --- когда всё плохо -----------------------------------------------------
def test_a_dead_bridge_is_an_error_not_a_crash():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    connection = McpClient("phone", "http://bridge/mcp",
                           transport=httpx.MockTransport(refuse))

    with pytest.raises(McpError) as failure:
        connection.tools()
    assert failure.value.retryable is True


def test_a_protocol_error_is_not_worth_repeating():
    server = FakeServer()
    connection = client(server)

    with pytest.raises(McpError) as failure:
        connection._send("prompts/list")
    assert failure.value.retryable is False


# --- реестр --------------------------------------------------------------
def registry(servers):
    entries = tuple(McpServer(name, f"http://{name}/mcp") for name in servers)

    def factory(name, url, token):
        return McpClient(name, url, token, transport=servers[name].transport())

    return McpRegistry(servers=entries, client_factory=factory)


def test_the_registry_shows_what_is_connected():
    catalogue = registry({"phone": FakeServer()}).catalogue()

    assert catalogue[0]["name"] == "phone"
    assert catalogue[0]["status"] == "ok"
    assert len(catalogue[0]["tools"]) == 2


def test_a_broken_server_does_not_hide_the_others():
    class Dead(FakeServer):
        def handle(self, request):
            raise httpx.ConnectError("нет связи")

    catalogue = registry({"phone": FakeServer(), "home": Dead()}).catalogue()
    by_name = {item["name"]: item for item in catalogue}

    assert by_name["phone"]["status"] == "ok"
    assert by_name["home"]["status"] == "error"


def test_a_tool_is_found_without_knowing_its_server():
    """Через шлюз имена приезжают с приставкой, и звать по точному имени нельзя."""
    gateway = FakeServer(tools=[{"name": "phone.phone_today", "description": ""}])

    server, tool = registry({"gateway": gateway}).find("phone_today")

    assert (server, tool) == ("gateway", "phone.phone_today")


def test_asking_for_a_tool_nobody_has_is_an_honest_error():
    with pytest.raises(McpError):
        registry({"phone": FakeServer()}).call_tool("open_the_pod_bay_doors")


# --- действия ------------------------------------------------------------
def test_a_change_on_the_phone_goes_through_the_action_engine(bus):
    """Спросить — можно сразу, отправить — только через разрешения и журнал."""
    from core.actions import ActionEngine
    from core.permissions import PermissionEngine
    from providers.mcp import McpActionProvider

    server = FakeServer()
    engine = ActionEngine(bus, PermissionEngine(),
                          providers=[McpActionProvider(registry({"phone": server}))])

    action = engine.request("mcp.tool.call",
                            {"server": "phone", "tool": "phone_push",
                             "arguments": {"text": "Позвонить Саше"}},
                            source="test")

    assert action.status == "WAITING_APPROVAL"
    done = engine.approve(action.id, "owner")
    assert done.status == "SUCCESS"
    assert done.result["text"] == "Сон 7 ч"


def test_a_call_to_a_missing_server_is_refused_before_the_network(bus):
    from core.actions import ActionEngine
    from core.permissions import PermissionEngine
    from providers.mcp import McpActionProvider

    engine = ActionEngine(bus, PermissionEngine(),
                          providers=[McpActionProvider(registry({"phone": FakeServer()}))])

    action = engine.request("mcp.tool.call", {"server": "home", "tool": "lights_on"},
                            source="test")

    assert action.status == "FAILED"


# --- чтение не должно быть лазейкой --------------------------------------
MARKED = [{"name": "phone_today", "description": "сводка дня",
           "annotations": {"readOnlyHint": True}},
          {"name": "phone_push", "description": "задание телефону",
           "annotations": {"readOnlyHint": False}},
          {"name": "phone_maybe", "description": "без пометки"}]


def test_a_promise_to_change_nothing_is_read_from_the_server():
    reg = registry({"phone": FakeServer(tools=MARKED)})

    assert reg.read_only("phone", "phone_today") is True
    assert reg.read_only("phone", "phone_push") is False


def test_a_tool_without_a_promise_counts_as_writing():
    """Сервер, забывший разметку, не должен получать право писать даром."""
    reg = registry({"phone": FakeServer(tools=MARKED)})

    assert reg.read_only("phone", "phone_maybe") is False
    assert reg.read_only("phone", "нет такого") is False


@pytest.fixture
def panel(core, monkeypatch):  # noqa: F811
    """Эндпоинты берут ядро через get_core — привяжем его к нашему."""
    from core import bootstrap

    from providers.mcp import McpActionProvider

    core.mcp = registry({"phone": FakeServer(tools=MARKED)})
    core.actions.register(McpActionProvider(core.mcp))
    monkeypatch.setattr(bootstrap, "_core", core)
    return core


def test_a_writing_tool_is_refused_on_the_reading_path(panel):
    """Запуск ярлыка на телефоне — поступок, и подтверждение ему нужно."""
    from core.api import api_mcp_read

    answer = api_mcp_read({"tool": "phone_push", "arguments": {"text": "привет"}})

    assert "может менять данные" in answer["error"]


def test_a_tool_that_forgot_to_promise_is_refused_too(panel):
    from core.api import api_mcp_read

    assert "может менять данные" in api_mcp_read({"tool": "phone_maybe"})["error"]


def test_a_reading_tool_still_goes_straight_through(panel):
    from core.api import api_mcp_read

    assert api_mcp_read({"tool": "phone_today"})["text"] == "Сон 7 ч"


def test_a_change_is_not_confirmed_on_our_behalf(panel):
    """Уровень риска MEDIUM — украшение, если подтверждать за владельца."""
    from core.api import api_mcp_call

    answer = api_mcp_call({"server": "phone", "tool": "phone_push",
                           "arguments": {"text": "привет"}})

    assert answer["status"] == "WAITING_APPROVAL"


def test_a_change_the_owner_confirmed_goes_through(panel):
    from core.api import api_mcp_call

    answer = api_mcp_call({"server": "phone", "tool": "phone_push",
                           "arguments": {"text": "привет"}, "user_confirmed": True})

    assert answer["status"] == "SUCCESS"


# --- повисший сервер не должен стопорить ответы --------------------------
def test_a_hung_bridge_does_not_queue_everyone_behind_it():
    """Отказ приходит мгновенно, а молчание держит спрашивающего.

    Пока согласование версии занимало общий замок, пять заходов на главный
    экран складывались в пять ожиданий подряд. Теперь первый платит своим
    ожиданием, а остальные получают отказ сразу.
    """
    import threading
    import time as clock

    class Hung:
        """Принимает соединение и не отвечает — как сервер под нагрузкой."""

        def transport(self):
            def handle(request):
                clock.sleep(0.4)
                raise httpx.ReadTimeout("тишина")
            return httpx.MockTransport(handle)

    one = McpClient("phone", "http://bridge/mcp", timeout=0.4,
                    transport=Hung().transport())
    spent = []

    def ask():
        started = clock.time()
        try:
            one.call("phone_today")
        except McpError:
            pass
        spent.append(clock.time() - started)

    threads = [threading.Thread(target=ask) for _ in range(5)]
    started = clock.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    whole = clock.time() - started

    # Одно ожидание на всех, а не по одному на каждого.
    assert whole < 1.2, (whole, spent)
    assert max(spent) < 0.8, spent

    # А пришедший следом уже не ждёт вовсе: мост помечен молчащим.
    started = clock.time()
    with pytest.raises(McpError):
        one.call("phone_today")
    assert clock.time() - started < 0.1


def test_a_bridge_that_went_silent_is_left_alone_for_a_while():
    class Hung:
        def __init__(self):
            self.tries = 0

        def transport(self):
            def handle(request):
                self.tries += 1
                raise httpx.ReadTimeout("тишина")
            return httpx.MockTransport(handle)

    server = Hung()
    one = McpClient("phone", "http://bridge/mcp", transport=server.transport())
    for _ in range(4):
        with pytest.raises(McpError):
            one.call("phone_today")

    assert server.tries == 1


def test_a_bridge_that_came_back_is_asked_again():
    """Пауза не должна превращаться в приговор."""
    from core import mcp as mcp_mod

    server = FakeServer()
    calls = {"n": 0}

    def handle(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("тишина")
        return server.handle(request)

    one = McpClient("phone", "http://bridge/mcp", transport=httpx.MockTransport(handle))
    with pytest.raises(McpError):
        one.tools()
    one._silent_until = 0.0  # как будто пауза вышла

    assert [t["name"] for t in one.tools()] == ["phone_today", "phone_push"]
    assert mcp_mod.COOLDOWN > 0
