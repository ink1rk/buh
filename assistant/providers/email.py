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
import json
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

from core.actions import ActionProvider, ProviderError, ValidationError
from core.config import config

# Имена ящиков, за которыми не сидит человек. Сверяется начало локальной части
# адреса, а не любое вхождение: иначе «news» ловил бы Newsome, а «bill» — Билла.
ROBOT_NAMES = (
    "no-reply", "noreply", "do-not-reply", "donotreply", "reply-to",
    "mailer-daemon", "postmaster", "bounce", "daemon", "auto", "automail",
    "notification", "notifications", "notify", "alert", "alerts",
    "newsletter", "mailing", "news", "digest", "info", "support", "robot",
    # Транзакционные роботы: чеки, счета, заказы, коды подтверждения. Заголовков
    # рассылки у них нет, так что узнать их можно только по имени ящика.
    "echeck", "check", "cheque", "receipt", "bill", "billing", "invoice",
    "order", "orders", "ticket", "promo", "offer", "sale", "service",
    "account", "accounts", "security", "verify", "confirm", "welcome",
    "mailer", "sender", "mail", "webmaster", "feedback",
)

# Заголовки, которыми рассылки сами себя объявляют рассылками.
BULK_HEADERS = ("list-unsubscribe", "list-id", "list-post", "auto-submitted",
                "x-auto-response-suppress")

MUTED_KEY = "email_muted_senders"
ALLOWED_KEY = "email_allowed_senders"

# Почтовые серверы отвечают на отказ по-своему и по-английски. Владельцу нужно
# не это, а что именно поправить: самая частая ошибка — пароль аккаунта вместо
# пароля приложения, и по ответу сервера её видно точно.
LOGIN_PROBLEMS = (
    ("application-specific password",
     "нужен пароль приложения, а не пароль аккаунта "
     "(Google Аккаунт → Безопасность → Пароли приложений)"),
    ("imap access is disabled",
     "в настройках ящика выключен доступ по IMAP"),
    ("imap is disabled",
     "в настройках ящика выключен доступ по IMAP"),
    ("login via application password",
     "нужен пароль приложения, а не пароль аккаунта"),
    ("authenticationfailed", "логин или пароль не приняты"),
    ("invalid credentials", "логин или пароль не приняты"),
    ("authentication failed", "логин или пароль не приняты"),
    ("login failure", "логин или пароль не приняты"),
    ("username and password not accepted", "логин или пароль не приняты"),
)


def login_problem(error):
    """Отказ на входе, переведённый в действие. None — дело не в доступе."""
    text = str(error).lower()
    for marker, advice in LOGIN_PROBLEMS:
        if marker in text:
            return advice
    return None

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


def is_robot_mailbox(address):
    """Имя ящика выдаёт робота.

    Сверяется имя целиком, а не его начало: «news» иначе ловил бы Newsome,
    «bill» — Билла, а «check» — Чеканова. Отбрасываются только приписки из
    цифр и разделителей, какими роботы нумеруют письма: order-3312, noreply2.
    """
    local = (address or "").lower().split("@")[0]
    candidates = {local,
                  local.rstrip("0123456789-_."),
                  re.split(r"[^a-z]", local, maxsplit=1)[0]}
    return bool(candidates.intersection(ROBOT_NAMES))


def _senders(key):
    from core import db

    try:
        return set(json.loads(db.setting(key) or "[]"))
    except (ValueError, TypeError):
        return set()


def sender_lists():
    """Решения владельца об отправителях: кто робот, а кто всё-таки человек."""
    return {"muted": sorted(_senders(MUTED_KEY)),
            "allowed": sorted(_senders(ALLOWED_KEY))}


def mark_sender(address, robot=True):
    """Слово владельца сильнее эвристики и запоминается."""
    from core import db

    address = (address or "").strip().lower()
    if not address:
        return sender_lists()
    muted, allowed = _senders(MUTED_KEY), _senders(ALLOWED_KEY)
    if robot:
        muted.add(address)
        allowed.discard(address)
    else:
        allowed.add(address)
        muted.discard(address)
    db.set_setting(MUTED_KEY, json.dumps(sorted(muted), ensure_ascii=False))
    db.set_setting(ALLOWED_KEY, json.dumps(sorted(allowed), ensure_ascii=False))
    return sender_lists()


# Чеки и счета — не люди, но и не мусор: это деньги, их место в финансах.
FINANCIAL_ROBOTS = {
    "receipt", "invoice", "bill", "billing", "order", "orders",
    "echeck", "check", "cheque", "account", "accounts",
}
MONEY_SUBJECT = re.compile(
    r"(счет|счёт|чек|оплат|квитанц|invoice|receipt|\bbill\b|подписк|"
    r"списан|платеж|платёж|задолжен|к оплате)",
    re.I,
)
AMOUNT_RE = re.compile(
    r"(?:сумма|к оплате|итог|total|amount)[:\s]*"
    r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,](\d{2}))?"
    r"|"
    r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+)(?:[.,](\d{2}))?\s*(?:₽|руб|RUB)",
    re.I,
)
DUE_RE = re.compile(
    r"(?:оплатит[ьте]|до|срок|due)\s+(\d{1,2})[./](\d{1,2})[./](\d{2,4})",
    re.I,
)


def extract_amount(text):
    match = AMOUNT_RE.search(text or "")
    if not match:
        return None
    whole = (match.group(1) or match.group(3) or "").replace(" ", "").replace("\u00a0", "")
    cents = match.group(2) or match.group(4)
    try:
        value = float(whole)
    except ValueError:
        return None
    if cents:
        value += int(cents) / 100
    return round(value, 2) if value > 0 else None


def extract_due_date(text, default=None):
    match = DUE_RE.search(text or "")
    if not match:
        return default
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if year < 100:
        year += 2000
    try:
        from datetime import date
        return date(year, month, day)
    except ValueError:
        return default


def looks_financial(address, subject="", text=""):
    """Письмо про деньги: чек, счёт, списание. Не человек, но и не реклама."""
    local = (address or "").lower().split("@")[0]
    names = {local, local.rstrip("0123456789-_."),
             re.split(r"[^a-z]", local, maxsplit=1)[0]}
    if names.intersection(FINANCIAL_ROBOTS):
        return True
    blob = f"{subject or ''}\n{text or ''}"
    if MONEY_SUBJECT.search(subject or "") and extract_amount(blob):
        return True
    return False


def looks_personal(sender, headers, cfg=None, lists=None):
    """Письмо от человека, а не от рассылки.

    Без этой проверки каждая рекламная рассылка превращалась бы в контакт,
    диалог и подсказку ответа — входящие перестали бы что-то значить.

    Совершенным отбор быть не может: транзакционные роботы — чеки, счета,
    коды — шлют письма, неотличимые от обычных по заголовкам. Поэтому слово
    владельца сильнее любой эвристики, а отсеянное не пропадает молча: кого
    именно отбросили, видно в настройках.
    """
    cfg = cfg or config.email
    lists = sender_lists() if lists is None else lists
    address = (sender or "").lower()

    if any(mark in address for mark in lists.get("allowed", ())):
        return True
    if any(mark in address for mark in lists.get("muted", ())):
        return False
    if any(mark in address for mark in cfg.ignore_senders):
        return False
    if is_robot_mailbox(address):
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
        except imaplib.IMAP4.error as e:
            # Неверный пароль не станет верным от повтора, а настойчивые
            # попытки входа провайдер считает подозрительными и блокирует ящик.
            advice = login_problem(e)
            if advice:
                raise ProviderError(f"{self.account.name}: {advice}",
                                    retryable=False) from e
            raise ProviderError(f"IMAP {self.account.name}: {e}",
                                retryable=True) from e
        except OSError as e:
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
            self._select(client)
            status, data = client.uid("search", None, "UNSEEN")
            if status != "OK":
                return []
            return self._load(client, (data[0] or b"").split()[-limit:])
        finally:
            self._logout(client)

    def fetch_new(self, state=None):
        """Письма, пришедшие после прошлого опроса.

        По непрочитанным идти нельзя: ящик, где их сотня, показывает только
        последние, и письмо человека, за которым пришла пачка рассылок,
        выпадает из окна навсегда. UID растёт монотонно и такого не допускает.

        Возвращает (письма, новое состояние). Пустое состояние на входе значит
        первый запуск: тогда почта только помечается прошлым, иначе ассистент
        начал бы с разбора всей истории ящика.
        """
        state = state or {}
        client = self._connect()
        try:
            validity = int(self._select(client))
            status, data = client.uid("search", None, "ALL")
            uids = [int(x) for x in (data[0] or b"").split()] if status == "OK" else []
            newest = max(uids) if uids else 0

            known = state.get("uid", 0) if state.get("uidvalidity") == validity else 0
            if not state or state.get("uidvalidity") != validity:
                # Первый запуск или ящик пересоздан: UID прошлого больше не
                # значат ничего, и разбирать историю заново незачем.
                return [], {"uid": newest, "uidvalidity": validity, "first": True}

            fresh = sorted(uid for uid in uids if uid > known)[:self.cfg.max_per_poll]
            letters = self._load(client, [str(uid).encode() for uid in fresh])
            highest = max(fresh) if fresh else known
            return letters, {"uid": highest, "uidvalidity": validity}
        finally:
            self._logout(client)

    def _select(self, client):
        status, _ = client.select(self.cfg.folder, readonly=True)
        if status != "OK":
            raise ProviderError(f"нет папки {self.cfg.folder}", retryable=False)
        status, data = client.status(self.cfg.folder, "(UIDVALIDITY)")
        if status != "OK":
            return 0
        found = re.search(rb"UIDVALIDITY (\d+)", data[0] or b"")
        return int(found.group(1)) if found else 0

    def _load(self, client, uids):
        letters = []
        for uid in uids:
            status, raw = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            parsed = self.parse(raw[0][1])
            if parsed:
                letters.append(parsed)
        return letters

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
            raise ProviderError(
                f"{account.name}: {login_problem(e) or 'логин или пароль не приняты'}",
                retryable=False) from e
        except (smtplib.SMTPException, OSError) as e:
            raise ProviderError(f"SMTP {account.name}: {e}", retryable=True) from e

        return {"transport": "smtp", "account": account.name, "to": params["to"],
                "subject": message["Subject"], "message_id": message["Message-ID"]}


def mailboxes(cfg=None):
    cfg = cfg or config.email
    return [Mailbox(account, cfg) for account in cfg.accounts]
