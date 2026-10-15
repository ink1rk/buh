"""Trusted policy checks. Untrusted text never becomes a system instruction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

FORBIDDEN_TOOLS = frozenset(
    {
        "kubectl",
        "qm",
        "pvesh",
        "proxmox",
        "ssh",
        "shell",
        "host_shell",
    }
)
WRITE_TOOLS = frozenset(
    {
        "calendar.create",
        "calendar.update",
        "calendar.delete",
        "email.send",
        "email.delete",
        "purchase",
        "post.publish",
    }
)
SECRET_REQUEST = re.compile(
    r"(api[_ -]?key|secret|password|token|kubeconfig|credential|парол|секрет|токен)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


def payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def screen_untrusted(text: str) -> Decision:
    """Content from mail, web, and chat is data. It cannot grant tools or secrets."""
    if not text:
        return Decision(True, "empty")
    if SECRET_REQUEST.search(text) and re.search(
        r"(reveal|show|print|dump|вывед|покаж|tell me|отправ)", text, re.IGNORECASE
    ):
        return Decision(False, "untrusted text requested secrets")
    if re.search(r"ignore (all|previous) instructions|system prompt", text, re.IGNORECASE):
        return Decision(False, "untrusted text attempted to override policy")
    return Decision(True, "data-only")


def authorize_tool(tool: str, *, has_approval: bool, untrusted_text: str | None = None) -> Decision:
    screened = screen_untrusted(untrusted_text or "")
    if not screened.allowed:
        return screened
    if tool in FORBIDDEN_TOOLS or tool.startswith("kubectl") or tool.startswith("proxmox"):
        return Decision(False, "tool is outside the worker allowlist")
    if tool in WRITE_TOOLS and not has_approval:
        return Decision(False, "external write requires a consumed approval")
    return Decision(True, "allowed")
