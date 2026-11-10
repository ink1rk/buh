"""Drive the local dry-run UI and save R10 screenshots. No cookies are printed."""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.request
from pathlib import Path

OUT = Path("/agent/repos/buh/telegram-media-network/reports/screenshots/r10")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("TMN_BASE", "http://127.0.0.1:8787")
NOTES = OUT / "browser-notes.txt"


class Cdp:
    def __init__(self, url: str) -> None:
        host_path = url.split("://", 1)[1]
        host, path = host_path.split("/", 1)
        name, port = host.split(":")
        self.sock = socket.create_connection((name, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.buf = b""
        self.seq = 0

    def call(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self.seq += 1
        ident = self.seq
        self._send({"id": ident, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = self._recv()
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]
        raise TimeoutError(method)

    def _send(self, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        length = len(raw)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))
        header.extend(mask)
        self.sock.sendall(bytes(header) + bytes(byte ^ mask[index % 4] for index, byte in enumerate(raw)))

    def _recv(self) -> dict:
        while True:
            frame = self._frame()
            if frame is None:
                continue
            message = json.loads(frame)
            if "id" in message or message.get("method") == "Page.loadEventFired":
                return message

    def _frame(self) -> str | None:
        header = self._read(2)
        opcode = header[0] & 0x0F
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read(8))[0]
        payload = self._read(length)
        if opcode == 8:
            raise RuntimeError("socket closed")
        if opcode != 1:
            return None
        return payload.decode()

    def _read(self, count: int) -> bytes:
        while len(self.buf) < count:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise RuntimeError("eof")
            self.buf += chunk
        data, self.buf = self.buf[:count], self.buf[count:]
        return data


def main() -> None:
    request = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(request) as response:
        target = json.load(response)
    page = Cdp(target["webSocketDebuggerUrl"])
    page.call("Page.enable")
    page.call("Runtime.enable")
    notes: list[str] = []

    def go(url: str) -> None:
        page.call("Page.navigate", {"url": url})
        deadline = time.time() + 90
        while time.time() < deadline:
            state = page.call("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True})
            if state["result"]["value"] == "complete":
                time.sleep(0.5)
                return
            time.sleep(0.2)
        raise TimeoutError(url)

    def js(expression: str, timeout: float = 60):
        result = page.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("text", "js"))
        return result["result"].get("value")

    def shot(name: str, width: int) -> None:
        page.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 700},
        )
        time.sleep(0.4)
        metrics = js(
            "({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})"
        )
        if metrics["scroll"] > metrics["client"] + 24 and "calendar" not in name:
            notes.append(f"OVERFLOW {name} {metrics}")
        image = page.call("Page.captureScreenshot", {"format": "png"})
        (OUT / name).write_bytes(base64.b64decode(image["data"]))

    def shots(name: str) -> None:
        for width in (375, 768, 1280, 1600):
            shot(f"{name}-{width}.png", width)

    go(f"{BASE}/login")
    js(
        """
        document.querySelector('[name=username]').value = 'owner';
        document.querySelector('[name=password]').value = 'owner-password-12';
        document.querySelector('form').submit();
        """
    )
    time.sleep(1.8)
    go(f"{BASE}/")
    text = js("document.body.innerText")
    if "НейроПульс" not in text:
        raise RuntimeError("overview missing channels")
    shots("overview-empty")

    go(f"{BASE}/lab")
    js("document.querySelector('form[action=\"/lab/load\"]').submit()")
    deadline = time.time() + 180
    loaded = False
    while time.time() < deadline:
        try:
            body = js("document.body.innerText")
        except Exception:
            time.sleep(1.5)
            continue
        if "ещё не запускался" not in body and "Прогон:" in body and "Telegram send = 0" in body:
            loaded = True
            break
        time.sleep(1.5)
    if not loaded:
        raise RuntimeError("lab load did not finish")
    shots("lab")

    go(f"{BASE}/")
    if "НейроПульс" not in js("document.body.innerText"):
        raise RuntimeError("overview after lab missing")
    shots("overview")

    go(f"{BASE}/radar?channel=cyber&q=CVE")
    radar = js("document.body.innerText")
    if "CVE-2026-880001" not in radar:
        raise RuntimeError("radar missing lab CVE")
    shots("radar")

    href = js(
        "document.querySelector('a[href^=\"/dossier/\"]') && document.querySelector('a[href^=\"/dossier/\"]').href"
    )
    if not href:
        raise RuntimeError("no dossier link")
    go(href)
    dossier = js("document.body.innerText")
    if "Досье" not in dossier:
        raise RuntimeError("dossier missing")
    shots("dossier")

    review = js(
        "document.querySelector('a[href^=\"/review/\"]') && document.querySelector('a[href^=\"/review/\"]').href"
    )
    if review:
        go(review)
        editor = js("document.body.innerText")
        if "Редакция" not in editor:
            raise RuntimeError("editor missing")
        if "Варианты" not in editor:
            notes.append("editor variants heading missing")
        shots("editor")

    go(f"{BASE}/studio")
    images = js("document.images.length")
    if images != 48:
        raise RuntimeError(f"studio images {images}")
    shots("studio")

    go(f"{BASE}/calendar?days=7")
    week = js("document.querySelector('.cal-grid').getAttribute('aria-label')")
    if week != "Сетка 7 дней":
        raise RuntimeError(f"week grid {week}")
    shots("calendar-7")
    go(f"{BASE}/calendar?days=28")
    month = js("document.querySelector('.cal-grid').getAttribute('aria-label')")
    if month != "Сетка 28 дней":
        raise RuntimeError(f"month grid {month}")
    shots("calendar")

    conflict = js(
        """
        (async () => {
          const token = document.querySelector('meta[name=csrf]').content;
          const row = document.querySelector('[data-episode]');
          if (!row) return 'missing';
          const response = await fetch('/api/v1/calendar/episodes/' + row.dataset.episode, {
            method: 'PATCH',
            headers: {'content-type': 'application/json', 'x-csrf-token': token},
            body: JSON.stringify({slot_utc: '2026-11-12T06:10:00+00:00', expected_version: 999})
          });
          const payload = await response.json();
          return response.status + ' ' + (payload.detail || '');
        })()
        """
    )
    if not str(conflict).startswith("409") and conflict != "missing":
        raise RuntimeError(f"move conflict was {conflict}")
    notes.append(f"slot-conflict {conflict}")

    go(f"{BASE}/autopilot")
    js(
        """
        const form = document.querySelector('form[action=\"/autopilot/pause\"]');
        if (form) form.submit();
        """
    )
    time.sleep(1.2)
    go(f"{BASE}/autopilot")
    shots("autopilot")

    go(f"{BASE}/analytics")
    growth = js("document.body.innerText")
    if "н/д" not in growth:
        raise RuntimeError("growth missing unknown label")
    shots("growth")

    go(f"{BASE}/commercial")
    js(
        """
        const form = document.querySelector('form[action=\"/commercial/offer\"]');
        if (form) form.submit();
        """
    )
    time.sleep(1.2)
    go(f"{BASE}/commercial")
    js(
        """
        const form = document.querySelector('form[action=\"/commercial/reserve\"]');
        if (form) form.submit();
        """
    )
    time.sleep(1.2)
    go(f"{BASE}/commercial")
    js(
        """
        const form = document.querySelector('form[action=\"/commercial/cancel\"]');
        if (form) form.submit();
        """
    )
    time.sleep(1.2)
    go(f"{BASE}/commercial")
    commercial = js("document.body.innerText")
    if "cancelled" not in commercial and "отмен" not in commercial.lower():
        notes.append("commercial cancel label not obvious")
    shots("commercial")

    go(f"{BASE}/shift")
    shots("shift")
    go(f"{BASE}/passport/cyber")
    shots("passport")
    go(f"{BASE}/quality")
    shots("quality")

    exported = js(
        """
        (async () => {
          const response = await fetch('/api/v1/lab/export');
          const payload = await response.json();
          return JSON.stringify({status: response.status, telegram_send: payload.telegram_send, published_messages: payload.published_messages, clusters: payload.clusters});
        })()
        """
    )
    notes.append(f"lab-export {exported}")
    payload = json.loads(exported)
    if payload.get("telegram_send") != 0:
        raise RuntimeError("telegram_send not 0")

    NOTES.write_text("\n".join(notes) + "\n", encoding="utf-8")
    print("OK")
    print("\n".join(notes))


if __name__ == "__main__":
    main()
