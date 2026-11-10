"""Positive SPDX check. An identifier is open source only when every token is known."""

from __future__ import annotations

import re

# Exact identifiers. A prefix such as "MIT" must not accept "MIT-PrivateRestricted".
OPEN_SOURCE_IDS = frozenset(
    {
        "0BSD",
        "AFL-3.0",
        "AGPL-3.0",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "Apache-2.0",
        "Artistic-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSL-1.0",
        "CC0-1.0",
        "EPL-2.0",
        "EUPL-1.2",
        "GPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "ISC",
        "LGPL-2.1",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "OFL-1.1",
        "PostgreSQL",
        "Python-2.0",
        "Unlicense",
        "Zlib",
    }
)

OPEN_EXCEPTIONS = frozenset(
    {
        "Autoconf-exception-3.0",
        "Bison-exception-2.2",
        "Classpath-exception-2.0",
        "GCC-exception-3.1",
        "LLVM-exception",
    }
)

_TOKEN = re.compile(r"\(|\)|\bAND\b|\bOR\b|\bWITH\b|[A-Za-z0-9][A-Za-z0-9.+-]*")
_BLANK = {"", "NONE", "NOASSERTION", "OTHER"}


def classify_spdx(value: str | None) -> tuple[str, str]:
    """Return (license_state, stored_spdx). Unknown values are never open source."""
    text = " ".join(str(value or "").split())
    if text.upper() in _BLANK:
        return "unknown", ""
    if _expression_is_open(text):
        return "explicit_open_source", text[:80]
    return "unknown", text[:80]


def is_explicit_open_source(value: str | None) -> bool:
    return classify_spdx(value)[0] == "explicit_open_source"


def _expression_is_open(text: str) -> bool:
    tokens = _TOKEN.findall(text)
    if not tokens or "".join(tokens) != re.sub(r"\s+", "", text):
        return False
    try:
        opened = _parse_or(tokens)
    except (IndexError, ValueError):
        return False
    return opened and not tokens


def _parse_or(tokens: list[str]) -> bool:
    opened = _parse_and(tokens)
    while tokens and tokens[0] == "OR":
        tokens.pop(0)
        opened = _parse_and(tokens) and opened
    return opened


def _parse_and(tokens: list[str]) -> bool:
    opened = _parse_with(tokens)
    while tokens and tokens[0] == "AND":
        tokens.pop(0)
        opened = _parse_with(tokens) and opened
    return opened


def _parse_with(tokens: list[str]) -> bool:
    opened = _parse_primary(tokens)
    if tokens and tokens[0] == "WITH":
        tokens.pop(0)
        if not tokens:
            raise ValueError("exception")
        return opened and tokens.pop(0) in OPEN_EXCEPTIONS
    return opened


def _parse_primary(tokens: list[str]) -> bool:
    if not tokens:
        raise ValueError("empty")
    token = tokens.pop(0)
    if token == "(":
        opened = _parse_or(tokens)
        if not tokens or tokens.pop(0) != ")":
            raise ValueError("paren")
        return opened
    if token in {"AND", "OR", "WITH", ")"}:
        raise ValueError("operator")
    return token in OPEN_SOURCE_IDS
