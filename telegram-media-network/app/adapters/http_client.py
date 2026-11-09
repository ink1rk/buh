from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin

from app.pipeline.urlsec import SSRFBlocked, assert_url_safe

USER_AGENT = "TMNBot/0.1 (+https://example.invalid/tmn; editorial-research; contact=local-admin)"
MAX_REDIRECTS = 3
MAX_BYTES = 2_000_000


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


def safe_get(
    url: str,
    transport: Transport,
    resolver,
    allowlist: set[str] | None = None,
    headers: dict[str, str] | None = None,
    max_redirects: int = MAX_REDIRECTS,
) -> FetchOutcome:
    current = url
    sent = headers or conditional_headers()
    for hop in range(max_redirects + 1):
        try:
            assert_url_safe(current, resolver, allowlist)
        except SSRFBlocked as exc:
            return FetchOutcome(False, reason=exc.reason, requests=hop)
        result = transport.request("GET", current, sent)
        if len(result.body) > MAX_BYTES:
            return FetchOutcome(False, status=result.status, reason="response_too_large", requests=hop + 1)
        lowered = header_map(result.headers)
        if result.status in {301, 302, 303, 307, 308}:
            location = lowered.get("location") or ""
            if not location:
                return FetchOutcome(False, status=result.status, reason="redirect_missing", requests=hop + 1)
            current = urljoin(current, location)
            continue
        return FetchOutcome(True, status=result.status, headers=lowered, body=result.body, requests=hop + 1)
    return FetchOutcome(False, reason="too_many_redirects", requests=max_redirects + 1)


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
