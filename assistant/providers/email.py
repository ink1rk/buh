#!/usr/bin/env python3
"""Почта: чтение по IMAP и отправка по SMTP.

Это транспорт и только транспорт. Здесь письмо превращается в обычный словарь
с текстом и отправителем, а дальше с ним работает тот же конвейер, что и с
сообщением из Telegram: контакт, диалог, обязательства, подсказки ответов.

Аутентификация — логин и пароль приложения. OAuth для Gmail не сделан: он
требует регистрации приложения в Google Cloud и обновления токенов, а пароль
приложения даёт тот же доступ по тем же IMAP и SMTP.
"""
import email
import email.header
import email.utils
import hashlib
import imaplib
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

from core.actions import ActionProvider, ProviderError, ValidationError
from core.config import config

# Отправители, которые никогда не ждут ответа.
ROBOT_NAMES = ("no-reply", "noreply", "do-not-reply", "donotreply", "mailer-daemon",
               "postmaster", "bounce", "notification", "notifications", "newsletter",
               "mailing", "info@", "support@", "robot@", "news@")

# Заголовки, которыми рассылки сами себя объявляют рассылками.
BULK_HEADERS = ("list-unsubscribe", "list-id", "list-post", "auto-submitted",
                "x-auto-response-suppress")

QUOTE_LINE = re.compile(r"^\s*(>|On .+ wrote:|\d{1,2}\.\d{1,2}\.\d{2,4}.*(писал|wrote))",
                        re.IGNORECASE)
SIGNATURE = re.compile(r"^\s*(--\s*$|С уважением|Best regards|Sent from my)",
                       re.IGNORECASE)


def _fallback_id(address, subject, date_header):
    digest = hashlib.sha1(
        f"{address}|{subject}|{date_header}".encode("utf-8", "replace")).hexdigest()
    return f"<no-id-{digest[:24]}@local>"


def _decode(raw):
    """Заголовки приходят в MIME-кодировке, иногда по частям и в разных наборах."""
    if not raw:
        return ""
    parts = []
    for chunk, charset in email.header.decode_header(str(raw)):
        if isinstance(chunk, bytes):
            try:
                parts.append(chunk.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _body(message, limit):
    """Только текстовая часть: HTML-вёрстка модели не нужна и стоит токенов."""
    text = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() != "text/plain":
                continue
            if "attachment" in str(part.get("Content-Disposition", "")):
                continue
            payload = part.get_payload(decode=True)
            if payload:
                text = payload.decode(part.get_content_charset() or "utf-8",
                                      errors="replace")
                break
    else:
        payload = message.get_payload(decode=True)
        if payload:
            text = payload.decode(message.get_content_charset() or "utf-8",
                                  errors="replace")
    return strip_quotes(text)[:limit].strip()


def strip_quotes(text):
    """Убрать цитату и подпись: в ответ попадает только новое."""
    lines = []
    for line in (text or "").splitlines():
        if QUOTE_LINE.match(line) or SIGNATURE.match(line):
            break
        lines.append(line.rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def looks_personal(sender, headers, cfg=None):
    """Письмо от человека, а не от рассылки.

    Без этой проверки каждая рекламная рассылка превращалась бы в контакт,
    диалог и подсказку ответа — входящие перестали бы что-то значить.
    """
    cfg = cfg or config.email
    address = (sender or "").lower()
    if any(mark in address for mark in ROBOT_NAMES):
        return False
    if any(mark in address for mark in cfg.ignore_senders):
        return False
    lowered = {key.lower() for key in headers}
    return not lowered.intersection(BULK_HEADERS)


class Mailbox:
    """Один почтовый ящик по IMAP."""

    def __init__(self, account, cfg=None):
        self.account = account
        self.cfg = cfg or config.email

    def _connect(self):
        try:
            client = imaplib.IMAP4_SSL(self.account.imap_host, self.account.imap_port,
                                       ssl_context=ssl.create_default_context())
            client.login(self.account.user, self.account.password)
            return client
        except (imaplib.IMAP4.error, OSError) as e:
            raise ProviderError(f"IMAP {self.account.name}: {e}", retryable=True) from e

    def check(self):
        """Жив ли ящик — для реестра интеграций."""
        client = self._connect()
        try:
            status, _ = client.select(self.cfg.folder, readonly=True)
            if status != "OK":
                raise ProviderError(f"нет папки {self.cfg.folder}", retryable=False)
            return True
        finally:
            self._logout(client)

    def fetch_unseen(self, limit=None):
        """Непрочитанные письма. Флаг \\Seen не трогаем: почтой владеет человек."""
        limit = limit or self.cfg.max_per_poll
        client = self._connect()
        try:
            status, _ = client.select(self.cfg.folder, readonly=True)
            if status != "OK":
                raise ProviderError(f"нет папки {self.cfg.folder}", retryable=False)
            status, data = client.search(None, "UNSEEN")
            if status != "OK":
                return []
            uids = (data[0] or b"").split()[-limit:]
            letters = []
            for uid in uids:
                status, raw = client.fetch(uid, "(BODY.PEEK[])")
                if status != "OK" or not raw or not isinstance(raw[0], tuple):
                    continue
                parsed = self.parse(raw[0][1])
                if parsed:
                    letters.append(parsed)
            return letters
        finally:
            self._logout(client)

    def parse(self, raw_bytes):
        message = email.message_from_bytes(raw_bytes)
        name, address = email.utils.parseaddr(_decode(message.get("From")))
        if not address:
            return None
        try:
            stamp = email.utils.parsedate_to_datetime(message.get("Date")) \
                if message.get("Date") else None
        except (TypeError, ValueError):
            stamp = None
        subject = _decode(message.get("Subject"))
        return {
            "account": self.account.name,
            "address": address.lower(),
            "name": name or address.split("@")[0],
            "subject": subject,
            "text": _body(message, self.cfg.max_body_chars),
            # Без Message-ID письмо приходило бы заново при каждом опросе:
            # непрочитанным оно остаётся, а повторы ловятся только по нему.
            "message_id": (_decode(message.get("Message-ID"))
                           or _fallback_id(address, subject, message.get("Date"))),
            "references": _decode(message.get("References")),
            "ts": stamp.timestamp() if stamp else time.time(),
            "personal": looks_personal(address, message.keys(), self.cfg),
        }

    @staticmethod
    def _logout(client):
        try:
            client.logout()
        except Exception:
            pass                       # соединение всё равно закрывается


class EmailActionProvider(ActionProvider):
    """Отправка письма как обычное действие — через Action Engine и разрешения."""

    name = "email"
    action_types = ("send.email",)

    def __init__(self, cfg=None):
        self.cfg = cfg or config.email

    def validate(self, action):
        params = action.parameters or {}
        if not (params.get("to") or "").strip():
            raise ValidationError("нужен адрес получателя")
        if "@" not in params["to"]:
            raise ValidationError("адрес получателя без @")
        if not (params.get("body") or "").strip():
            raise ValidationError("пустое письмо")
        if not self.cfg.enabled:
            raise ValidationError("почта не настроена")

    def execute(self, action):
        params = action.parameters
        account = self.cfg.account(params.get("account"))
        if account is None:
            raise ProviderError("нет настроенного ящика", retryable=False)

        message = EmailMessage()
        message["From"] = email.utils.formataddr(
            (account.from_name or None, account.user))
        message["To"] = params["to"]
        message["Subject"] = params.get("subject") or "Re:"
        message["Date"] = email.utils.formatdate(localtime=True)
        message["Message-ID"] = email.utils.make_msgid()
        if params.get("in_reply_to"):
            message["In-Reply-To"] = params["in_reply_to"]
            message["References"] = params["in_reply_to"]
        message.set_content(params["body"])

        try:
            if account.smtp_ssl:
                server = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port,
                                          timeout=45,
                                          context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=45)
                server.starttls(context=ssl.create_default_context())
            with server:
                server.login(account.user, account.password)
                server.send_message(message)
        except smtplib.SMTPAuthenticationError as e:
            raise ProviderError(f"SMTP {account.name}: не пускает — {e}",
                                retryable=False) from e
        except (smtplib.SMTPException, OSError) as e:
            raise ProviderError(f"SMTP {account.name}: {e}", retryable=True) from e

        return {"transport": "smtp", "account": account.name, "to": params["to"],
                "subject": message["Subject"], "message_id": message["Message-ID"]}


def mailboxes(cfg=None):
    cfg = cfg or config.email
    return [Mailbox(account, cfg) for account in cfg.accounts]
