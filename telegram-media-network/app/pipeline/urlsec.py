from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src", "yclid"}
DENY_HOSTS = {"localhost", "metadata.google.internal", "metadata.internal", "instance-data"}
CGNAT = ipaddress.ip_network("100.64.0.0/10")

DEFAULT_ALLOWLIST = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "huggingface.co",
    "cdn-lfs.huggingface.co",
    "hacker-news.firebaseio.com",
    "news.ycombinator.com",
    "rss.arxiv.org",
    "arxiv.org",
    "export.arxiv.org",
    "www.cisa.gov",
    "cisa.gov",
    "kubernetes.io",
    "pypi.org",
    "pypi.python.org",
    "developers.cloudflare.com",
    "blog.cloudflare.com",
    "allowlisted.example",
}


class SSRFBlocked(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CanonicalURL:
    ok: bool
    url: str = ""
    host: str = ""
    reason: str = ""


def canonicalize(url: str) -> CanonicalURL:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return CanonicalURL(False, reason="unparseable")
    if parts.scheme.lower() != "https":
        return CanonicalURL(False, reason="scheme")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return CanonicalURL(False, reason="host")
    port = parts.port
    netloc = host if port in (None, 443) else f"{host}:{port}"
    path = "/" + "/".join(segment for segment in parts.path.split("/") if segment)
    if path == "":
        path = "/"
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        query_pairs.append((key, value))
    query_pairs.sort()
    canon = urlunsplit(("https", netloc, path, urlencode(query_pairs), ""))
    return CanonicalURL(True, url=canon, host=host)


def forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return forbidden_ip(ip.ipv4_mapped)
    if ip in CGNAT:
        return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def host_allowed(host: str, allowlist: set[str]) -> bool:
    for allowed in allowlist:
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


class DefaultResolver:
    def resolve(self, host: str) -> list[str]:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise SSRFBlocked("dns_failed") from exc
        return [str(info[4][0]) for info in infos]


def resolve_checked(
    url: str,
    resolver: DefaultResolver | Callable[[str], list[str]],
    allowlist: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Check the URL and return the addresses from this one lookup."""
    allow = DEFAULT_ALLOWLIST if allowlist is None else allowlist
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https":
        raise SSRFBlocked("scheme")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise SSRFBlocked("host")
    if host in DENY_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise SSRFBlocked("denied_host")
    literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if forbidden_ip(literal):
            raise SSRFBlocked("forbidden_ip")
        raise SSRFBlocked("ip_literal")
    if not host_allowed(host, allow):
        raise SSRFBlocked("not_allowlisted")
    if isinstance(resolver, DefaultResolver):
        addresses = resolver.resolve(host)
    else:
        addresses = resolver(host)
    if not addresses:
        raise SSRFBlocked("dns_failed")
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise SSRFBlocked("dns_failed") from exc
        if forbidden_ip(ip):
            raise SSRFBlocked("forbidden_ip")
    return host, [str(item) for item in addresses]


def assert_url_safe(url: str, resolver: DefaultResolver | Callable[[str], list[str]], allowlist: set[str] | None = None) -> str:
    """Raise SSRFBlocked before any socket is opened by the caller."""
    host, _addresses = resolve_checked(url, resolver, allowlist)
    return host
