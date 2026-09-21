#!/usr/bin/env python3
"""Turn model output into Telegram-safe HTML.

Models mix markdown and HTML no matter what the prompt says, and Telegram
rejects the whole message on a single stray tag. So: stash code blocks, keep
the handful of tags Telegram allows, escape everything else, convert the
markdown that slipped through, and fall back to plain text if tags end up
unbalanced.
"""
import re
from html import escape

ALLOWED = ("b", "strong", "i", "em", "u", "s", "code", "pre", "a")
TAG_ALIASES = {"strong": "b", "em": "i"}
TAG_RE = re.compile(
    r"</?(?:" + "|".join(t for t in ALLOWED if t != "a") + r")>|"
    r"<a\s+href=[\"']([^\"']*)[\"']\s*>|</a>",
    re.IGNORECASE,
)
SENTINEL = "\x00"


def _stash_code(text, store):
    def repl(match):
        store.append(("pre", match.group(2) or ""))
        return f"{SENTINEL}{len(store) - 1}{SENTINEL}"

    return re.sub(r"```[ \t]*(\w+)?\n?(.*?)```", repl, text, flags=re.S)


def _stash_tags(text, store):
    def repl(match):
        raw = match.group(0)
        href = match.group(1)
        if href is not None:
            store.append(("tag", f'<a href="{escape(href, quote=True)}">'))
        else:
            name = re.sub(r"[</>]", "", raw).lower()
            closing = raw.startswith("</")
            name = TAG_ALIASES.get(name, name)
            store.append(("tag", f"</{name}>" if closing else f"<{name}>"))
        return f"{SENTINEL}{len(store) - 1}{SENTINEL}"

    return TAG_RE.sub(repl, text)


def _markdown(text):
    text = re.sub(r"^[ \t]*#{1,6}[ \t]*(.+?)[ \t]*#*[ \t]*$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^[ \t]*[-–—_*]{3,}[ \t]*$", "", text, flags=re.M)
    text = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w`])`([^`\n]+)`(?![\w`])", r"<code>\1</code>", text)
    text = re.sub(r"^[ \t]*[-*•‣▪][ \t]+", "• ", text, flags=re.M)
    return text


def _balanced(text):
    for tag in ("b", "i", "u", "s", "code", "pre", "a"):
        opens = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", text))
        closes = len(re.findall(rf"</{tag}>", text))
        if opens != closes:
            return False
    return True


def to_html(text):
    """Model output -> Telegram HTML. Never raises; degrades to escaped text."""
    if not text:
        return ""
    store = []
    body = _stash_code(text.strip(), store)
    body = _stash_tags(body, store)
    body = escape(body, quote=False)
    body = _markdown(body)

    def unstash(match):
        kind, value = store[int(match.group(1))]
        return f"<pre>{escape(value)}</pre>" if kind == "pre" else value

    body = re.sub(rf"{SENTINEL}(\d+){SENTINEL}", unstash, body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not _balanced(body):
        return escape(plain(text), quote=False)
    return body


def plain(text):
    """Strip markup entirely — for voice and for plain-text fallbacks."""
    if not text:
        return ""
    text = re.sub(r"```[ \t]*\w*\n?(.*?)```", r"\1", text, flags=re.S)
    # Only known markup goes: "5 < 7 & 8 > 3" must survive intact.
    text = re.sub(r"</?(?:b|strong|i|em|u|s|code|pre)>|<a\s[^>]*>|</a>", "", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"\1", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^[ \t]*#{1,6}[ \t]*", "", text, flags=re.M)
    text = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", r"\1", text)
    text = re.sub(r"^[ \t]*[-*•‣▪][ \t]+", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split(text, limit=3900):
    """Split long messages on paragraph/line boundaries, keeping tags balanced."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        for piece in ([para] if len(para) <= limit else _hard_split(para, limit)):
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return [c for c in (_repair(c) for c in chunks) if c.strip()]


def _hard_split(para, limit):
    out, current = [], ""
    for line in para.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            out.append(current)
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        out.append(current)
    return out


def _repair(chunk):
    """Close tags left open by a split (and drop markup if that fails)."""
    if _balanced(chunk):
        return chunk
    for tag in ("b", "i", "u", "s", "code", "pre", "a"):
        opens = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", chunk))
        closes = len(re.findall(rf"</{tag}>", chunk))
        if opens > closes:
            chunk += f"</{tag}>" * (opens - closes)
        elif closes > opens:
            chunk = re.sub(rf"</{tag}>", "", chunk, count=closes - opens)
    return chunk if _balanced(chunk) else plain(chunk)
