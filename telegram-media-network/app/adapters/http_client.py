from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from app.pipeline.urlsec import SSRFBlocked, assert_url_safe

USER_AGENT = "TMNBot/0.1 (+https://example.invalid/tmn; editorial-research; contact=local-admin)"
MAX_REDIRECTS = 3
MAX_BYTES = 2_000_000
_CONDITIONAL = {"if-none-match", "if-modified-since"}


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes = b""
    url: str = ""


class Transport(Protocol):
    def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult: ...


@dataclass
class FetchOutcome:
    ok: bool
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    reason: str = ""
    requests: int = 0
    final_url: str = ""


def header_map(headers: dict[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def conditional_headers(etag: str = "", last_modified: str = "", accept: str = "application/json") -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def backoff_seconds(status: int, headers: dict[str, str], attempt: int, now: float) -> float | None:
    """Return the wait before another try. Never returns a tight-loop delay of 0."""
    lowered = header_map(headers)
    rate_limited = status == 429 or (status == 403 and lowered.get("x-ratelimit-remaining") == "0")
    if status == 403 and not rate_limited:
        rate_limited = "retry-after" in lowered or "x-ratelimit-reset" in lowered
    if not rate_limited:
        return None
    if "retry-after" in lowered:
        try:
            delay = float(lowered["retry-after"])
        except ValueError:
            return 1.0
        # A zero delay would busy-loop. A positive Retry-After is used unchanged.
        return delay if delay >= 1 else 1.0
    if "x-ratelimit-reset" in lowered:
        try:
            reset = float(lowered["x-ratelimit-reset"])
        except ValueError:
            return float(min(300, 2 ** max(1, attempt)))
        if reset > 1_000_000_000:
            return max(1.0, reset - now)
        return max(1.0, reset)
    return float(min(300, 2 ** max(1, attempt)))


def _origin(url: str) -> tuple[str, str, int] | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if not parts.scheme or not host:
        return None
    default = 443 if parts.scheme.lower() == "https" else 80
    return parts.scheme.lower(), host, parts.port or default


def _without(headers: dict[str, str], names: set[str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() not in names}


def safe_get(
    url: str,
    transport: Transport,
    resolver,
    allowlist: set[str] | None = None,
    headers: dict[str, str] | None = None,
    max_redirects: int = MAX_REDIRECTS,
    max_requests: int | None = None,
) -> FetchOutcome:
    """Follow only same-origin redirects. Credentials never leave the origin that sent them."""
    current = url
    sent = dict(headers or conditional_headers())
    seen = {current}
    made = 0
    for _hop in range(max_redirects + 1):
        if max_requests is not None and made >= max_requests:
            return FetchOutcome(False, reason="budget", requests=made)
        try:
            assert_url_safe(current, resolver, allowlist)
        except SSRFBlocked as exc:
            return FetchOutcome(False, reason=exc.reason, requests=made)
        result = transport.request("GET", current, sent)
        made += 1
        if len(result.body) > MAX_BYTES:
            return FetchOutcome(False, status=result.status, reason="response_too_large", requests=made)
        lowered = header_map(result.headers)
        if result.status not in {301, 302, 303, 307, 308}:
            return FetchOutcome(True, status=result.status, headers=lowered, body=result.body, requests=made, final_url=current)
        if max_requests is not None and made >= max_requests:
            return FetchOutcome(False, status=result.status, reason="budget", requests=made)
        location = lowered.get("location") or ""
        if not location:
            return FetchOutcome(False, status=result.status, reason="redirect_missing", requests=made)
        nxt = urljoin(current, location)
        try:
            assert_url_safe(nxt, resolver, allowlist)
        except SSRFBlocked as exc:
            return FetchOutcome(False, status=result.status, reason=exc.reason, requests=made)
        if _origin(nxt) != _origin(current):
            return FetchOutcome(False, status=result.status, reason="redirect_cross_origin", requests=made)
        if nxt in seen:
            return FetchOutcome(False, status=result.status, reason="redirect_loop", requests=made)
        seen.add(nxt)
        sent = _without(sent, _CONDITIONAL)
        current = nxt
    return FetchOutcome(False, reason="too_many_redirects", requests=made)


def fetch_with_backoff(fetch, sleeper, clock, max_attempts: int = 4) -> HttpResult:
    """Call `fetch` again only after `sleeper` has been asked to wait out the quota."""
    attempt = 0
    while True:
        response = fetch()
        delay = backoff_seconds(response.status, response.headers, attempt, clock())
        if delay is None or attempt + 1 >= max_attempts:
            return response
        sleeper(delay)
        attempt += 1


def interpret_status(status: int) -> str:
    if status == 304:
        return "not_modified"
    if status == 200:
        return "ok"
    if status in {403, 429}:
        return "rate_limited"
    if status >= 500 or status == 0:
        return "outage"
    return "error"
