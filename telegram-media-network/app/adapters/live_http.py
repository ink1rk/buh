"""HTTP client for a live collector. DNS is checked again on the socket that sends the request."""

from __future__ import annotations

import http.client
import socket
import ssl
from urllib.parse import urlsplit

from app.adapters.http_client import MAX_BYTES, HttpResult
from app.pipeline.urlsec import DefaultResolver, resolve_checked


class TransportError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(host, timeout=timeout, context=context)
        self._ip = ip
        self._pinned_context = context

    def connect(self) -> None:
        raw = socket.create_connection((self._ip, self.port or 443), self.timeout)
        self.sock = self._pinned_context.wrap_socket(raw, server_hostname=self.host)


class PinnedHTTPTransport:
    """One GET to an allowlisted host, pinned to the address just checked."""

    def __init__(self, resolver=None, timeout: float = 10.0, audit: list | None = None) -> None:
        self.resolver = resolver or DefaultResolver()
        self.timeout = timeout
        self.audit = audit if audit is not None else []

    def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult:
        if method != "GET":
            raise TransportError("method")
        try:
            host, addresses = resolve_checked(url, self.resolver)
        except Exception as exc:
            reason = getattr(exc, "reason", "") or "blocked"
            raise TransportError(reason) from exc
        ip = addresses[0]
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        context = ssl.create_default_context()
        conn = _PinnedHTTPSConnection(host, ip, self.timeout, context)
        try:
            conn.request(method, path, headers={str(key): str(value) for key, value in headers.items()})
            response = conn.getresponse()
            status = int(response.status)
            response_headers = {key.lower(): value for key, value in response.getheaders()}
            body = response.read(MAX_BYTES + 1)
        except (socket.timeout, TimeoutError) as exc:
            raise TransportError("timeout") from exc
        except ssl.SSLError as exc:
            raise TransportError("tls") from exc
        except OSError as exc:
            raise TransportError("network") from exc
        finally:
            conn.close()
        declared = response_headers.get("content-length")
        if len(body) > MAX_BYTES:
            raise TransportError("response_too_large")
        if declared:
            try:
                expected = int(declared)
            except ValueError:
                expected = -1
            if expected >= 0 and expected != len(body):
                raise TransportError("truncated")
        self.audit.append({"method": method, "host": host, "status": status})
        return HttpResult(status, response_headers, body, url)
