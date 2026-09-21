"""Почта: разбор письма, отсев рассылок и общий с Telegram путь до ответа."""
import email.utils
import time
from email.message import EmailMessage

import pytest

from core import pipeline
from core.actions import ActionProvider
from core.config import EmailConfig, MailAccount
from core.mailwatch import MailWatcher
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod
from providers.email import (EmailActionProvider, Mailbox, looks_personal,
                             strip_quotes)

from test_pipeline import StubSkills  # noqa: F401

ACCOUNT = MailAccount(name="yandex", user="kirill@yandex.ru", password="secret",
                      imap_host="imap.yandex.ru", imap_port=993,
                      smtp_host="smtp.yandex.ru", smtp_port=465,
                      from_name="Кирилл")


def settings(**overrides):
    return EmailConfig(accounts=(ACCOUNT,), **overrides)


def letter(subject="Договор", body="Добрый день! Пришлите договор.",
           sender="Анна Ковалёва <anna@example.com>", headers=None, html=False):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ACCOUNT.user
    message["Subject"] = subject
    message["Date"] = email.utils.formatdate(localtime=True)
    message["Message-ID"] = email.utils.make_msgid()
    for key, value in (headers or {}).items():
        message[key] = value
    message.set_content(body)
    if html:
        message.add_alternative(f"<html><body><p>{body}</p></body></html>",
                                subtype="html")
    return message


class FakeIMAP:
    """Столько от IMAP, сколько использует Mailbox."""

    def __init__(self, messages):
        self.messages = messages
        self.logged_out = False
        self.readonly = None

    def select(self, folder, readonly=False):
        self.readonly = readonly
        return ("OK", [b"1"])

    def search(self, charset, criterion):
        assert criterion == "UNSEEN"
        return ("OK", [b" ".join(str(i + 1).encode() for i in
                                 range(len(self.messages)))])

    def fetch(self, uid, spec):
        assert "PEEK" in spec           # прочитанным письмо делает человек
        index = int(uid) - 1
        return ("OK", [(b"header", self.messages[index].as_bytes())])

    def logout(self):
        self.logged_out = True


@pytest.fixture
def mailbox(monkeypatch):
    def build(messages):
        box = Mailbox(ACCOUNT, settings())
        fake = FakeIMAP(messages)
        monkeypatch.setattr(box, "_connect", lambda: fake)
        box.fake = fake
        return box
    return build


# --- разбор письма --------------------------------------------------------
def test_a_letter_becomes_a_plain_message(mailbox):
    box = mailbox([letter()])
    [parsed] = box.fetch_unseen()

    assert parsed["address"] == "anna@example.com"
    assert parsed["name"] == "Анна Ковалёва"
    assert parsed["subject"] == "Договор"
    assert parsed["text"] == "Добрый день! Пришлите договор."
    assert parsed["personal"] is True
    assert parsed["account"] == "yandex"


def test_encoded_headers_are_readable(mailbox):
    box = mailbox([letter(subject="Счёт за сентябрь",
                          sender="Пётр Сергеев <petr@example.com>")])
    [parsed] = box.fetch_unseen()
    assert parsed["subject"] == "Счёт за сентябрь"
    assert parsed["name"] == "Пётр Сергеев"


def test_html_letters_are_read_as_text(mailbox):
    """HTML-вёрстка модели не нужна и стоит токенов."""
    box = mailbox([letter(html=True)])
    [parsed] = box.fetch_unseen()
    assert "<html>" not in parsed["text"]
    assert parsed["text"] == "Добрый день! Пришлите договор."


def test_reading_does_not_mark_the_letter_read(mailbox):
    box = mailbox([letter()])
    box.fetch_unseen()
    assert box.fake.readonly is True
    assert box.fake.logged_out is True


def test_a_letter_without_message_id_still_has_one(mailbox):
    """Иначе непрочитанное письмо приходило бы заново при каждом опросе."""
    message = letter()
    del message["Message-ID"]
    box = mailbox([message])
    [parsed] = box.fetch_unseen()
    assert parsed["message_id"]

    again = mailbox([message])
    assert again.fetch_unseen()[0]["message_id"] == parsed["message_id"]


def test_quotes_and_signatures_are_cut():
    text = ("Да, договор готов.\n\n"
            "С уважением,\nАнна\n\n"
            "> Пришлите договор")
    assert strip_quotes(text) == "Да, договор готов."


# --- отсев рассылок -------------------------------------------------------
def test_a_person_is_personal():
    assert looks_personal("anna@example.com", ["From", "Subject"])


@pytest.mark.parametrize("address", [
    "no-reply@ozon.ru", "noreply@bank.ru", "mailer-daemon@example.com",
    "newsletter@shop.ru", "notifications@github.com"])
def test_robots_are_not_personal(address):
    assert not looks_personal(address, ["From"])


def test_mailing_lists_announce_themselves():
    """Рассылка сама себя объявляет заголовком отписки — этого достаточно."""
    assert not looks_personal("editor@digest.ru",
                              ["From", "List-Unsubscribe", "Subject"])
    assert not looks_personal("robot@service.io", ["From", "Auto-Submitted"])


def test_the_owner_can_silence_an_address():
    quiet = settings(ignore_senders=("hh.ru",))
    assert not looks_personal("jobs@hh.ru", ["From"], quiet)
    assert looks_personal("jobs@hh.ru", ["From"], settings())


# --- отправка -------------------------------------------------------------
class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.user = user

    def send_message(self, message):
        FakeSMTP.sent.append(message)


class FakeStartTLS(FakeSMTP):
    started = False

    def starttls(self, context=None):
        FakeStartTLS.started = True


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)
    return FakeSMTP


class Action:
    def __init__(self, **params):
        self.type = "send.email"
        self.parameters = params


def test_a_reply_keeps_the_thread(smtp):
    provider = EmailActionProvider(settings())
    result = provider.execute(Action(to="anna@example.com", subject="Re: Договор",
                                     body="Пришлю сегодня.",
                                     in_reply_to="<original@example.com>"))
    [sent] = smtp.sent
    assert sent["To"] == "anna@example.com"
    assert sent["In-Reply-To"] == "<original@example.com>"
    assert sent["References"] == "<original@example.com>"
    assert "Кирилл" in sent["From"] and ACCOUNT.user in sent["From"]
    assert result["transport"] == "smtp"


def test_a_starttls_mailbox_is_not_opened_as_ssl(monkeypatch):
    """Порт не говорит о режиме: угадывание молча вешало отправку."""
    FakeSMTP.sent = []
    FakeStartTLS.started = False
    monkeypatch.setattr("smtplib.SMTP", FakeStartTLS)
    starttls = MailAccount(name="corp", user="k@corp.ru", password="x",
                           imap_host="imap.corp.ru", imap_port=993,
                           smtp_host="smtp.corp.ru", smtp_port=587, smtp_ssl=False)

    EmailActionProvider(EmailConfig(accounts=(starttls,))).execute(
        Action(to="anna@example.com", body="Привет"))

    assert FakeStartTLS.started is True
    assert len(FakeSMTP.sent) == 1


def test_the_default_mode_follows_the_port(monkeypatch):
    monkeypatch.setenv("MAIL_ACCOUNTS", "yandex,corp")
    monkeypatch.setenv("MAIL_YANDEX_USER", "k@yandex.ru")
    monkeypatch.setenv("MAIL_YANDEX_PASSWORD", "x")
    monkeypatch.setenv("MAIL_CORP_USER", "k@corp.ru")
    monkeypatch.setenv("MAIL_CORP_PASSWORD", "x")
    monkeypatch.setenv("MAIL_CORP_IMAP_HOST", "imap.corp.ru")
    monkeypatch.setenv("MAIL_CORP_SMTP_HOST", "smtp.corp.ru")
    monkeypatch.setenv("MAIL_CORP_SMTP_PORT", "587")

    built = {a.name: a for a in EmailConfig().accounts}

    assert built["yandex"].smtp_ssl is True        # 465
    assert built["corp"].smtp_ssl is False         # 587 — STARTTLS


def test_a_nonstandard_ssl_port_can_be_declared(monkeypatch):
    """На своём сервере implicit TLS бывает не на 465 — это надо уметь сказать."""
    monkeypatch.setenv("MAIL_ACCOUNTS", "lab")
    monkeypatch.setenv("MAIL_LAB_USER", "k@lab.ru")
    monkeypatch.setenv("MAIL_LAB_PASSWORD", "x")
    monkeypatch.setenv("MAIL_LAB_IMAP_HOST", "imap.lab.ru")
    monkeypatch.setenv("MAIL_LAB_SMTP_HOST", "smtp.lab.ru")
    monkeypatch.setenv("MAIL_LAB_SMTP_PORT", "3465")
    monkeypatch.setenv("MAIL_LAB_SMTP_SSL", "true")

    [account] = EmailConfig().accounts
    assert account.smtp_port == 3465 and account.smtp_ssl is True


@pytest.mark.parametrize("params, complaint", [
    ({"body": "текст"}, "получател"),
    ({"to": "не-адрес", "body": "текст"}, "@"),
    ({"to": "a@b.ru", "body": "  "}, "пустое"),
])
def test_a_broken_letter_is_refused_before_sending(params, complaint):
    from core.actions import ValidationError
    provider = EmailActionProvider(settings())
    with pytest.raises(ValidationError) as caught:
        provider.validate(Action(**params))
    assert complaint in str(caught.value)


def test_nothing_is_sent_when_no_mailbox_is_configured():
    from core.actions import ValidationError
    provider = EmailActionProvider(EmailConfig(accounts=()))
    with pytest.raises(ValidationError):
        provider.validate(Action(to="a@b.ru", body="текст"))


# --- общий путь с Telegram ------------------------------------------------
class FakeEmailProvider(ActionProvider):
    action_types = ("send.email",)

    def __init__(self):
        self.sent = []

    def execute(self, action):
        self.sent.append(action.parameters)
        return {"transport": "fake", "message_id": len(self.sent)}


@pytest.fixture
def core(monkeypatch):
    from conftest import FakeLLM
    from core.bootstrap import Core

    llm = FakeLLM(structured={"ReplyOptions": {
        "context_summary": "Анна ждёт договор",
        "options": ["Пришлю сегодня.", "Договор готовлю.", "Уточню сроки."]}})
    instance = Core(skills=StubSkills(), start_workers=False)
    instance.llm = llm
    instance.communication.llm = llm
    instance.personal.llm = llm
    instance.enricher.llm = llm
    provider = FakeEmailProvider()
    instance.actions.providers = [provider]
    instance.email_provider = provider
    monkeypatch.setattr(instance.enricher, "on_message", lambda *a, **k: None)
    yield instance
    instance.stop()


def incoming(**overrides):
    payload = {"account": "yandex", "address": "anna@example.com",
               "name": "Анна Ковалёва", "subject": "Договор",
               "text": "Добрый день! Пришлите договор.",
               "message_id": "<letter-1@example.com>", "ts": time.time(),
               "personal": True}
    payload.update(overrides)
    return payload


def test_a_letter_walks_the_same_path_as_a_message(core):
    result = pipeline.ingest_incoming(core, incoming(), channel="email")

    contact = contacts_mod.get(result["contact_id"])
    assert contact.display_name == "Анна Ковалёва"
    assert contact.emails == ["anna@example.com"]

    conversation = conversations_mod.get(result["conversation_id"])
    assert conversation.platform == "email"
    assert conversation.external_id == "anna@example.com"
    assert result["options"] == ["Пришлю сегодня.", "Договор готовлю.",
                                 "Уточню сроки."]


def test_the_subject_reaches_the_model(core):
    """Без темы письмо часто нечитаемо: «см. вложение» — это не контекст."""
    seen = {}
    original = core.communication.suggest_replies

    def spy(context):
        seen["text"] = context.text
        return original(context)

    core.communication.suggest_replies = spy
    pipeline.ingest_incoming(core, incoming(), channel="email")
    assert "Договор" in seen["text"] and "Пришлите договор" in seen["text"]


def test_the_same_letter_twice_is_one_suggestion(core):
    """Непрочитанное письмо возвращается при каждом опросе IMAP."""
    first = pipeline.ingest_incoming(core, incoming(), channel="email")
    again = pipeline.ingest_incoming(core, incoming(), channel="email")

    assert again["duplicate"] is True
    assert [s["id"] for s in pipeline.list_suggestions()] == [first["suggestion_id"]]


def test_answering_a_letter_sends_a_letter(core):
    result = pipeline.ingest_incoming(core, incoming(), channel="email")
    sent = pipeline.send_reply(core, result["suggestion_id"], index=0)

    assert sent["status"] == "SUCCESS"
    [params] = core.email_provider.sent
    assert params["to"] == "anna@example.com"
    assert params["subject"] == "Re: Договор"
    assert params["in_reply_to"] == "<letter-1@example.com>"
    assert params["body"] == "Пришлю сегодня."
    assert params["account"] == "yandex"


def test_a_reply_does_not_pile_up_re(core):
    result = pipeline.ingest_incoming(core, incoming(subject="Re: Договор"),
                                      channel="email")
    pipeline.send_reply(core, result["suggestion_id"], index=0)
    assert core.email_provider.sent[0]["subject"] == "Re: Договор"


def test_the_same_person_in_mail_and_telegram_is_one_contact(core):
    """Иначе человек двоится и половина памяти о нём теряется."""
    contact = contacts_mod.upsert_from_telegram("777", "Анна Ковалёва")
    contact.emails = ["anna@example.com"]
    contacts_mod.save(contact)

    result = pipeline.ingest_incoming(core, incoming(), channel="email")
    assert result["contact_id"] == contact.id
    assert len(contacts_mod.all_contacts()) == 1


# --- опрос ящиков ---------------------------------------------------------
def test_the_watcher_ignores_mailing_lists(core, mailbox):
    box = mailbox([
        letter(),
        letter(sender="no-reply@ozon.ru", subject="Скидки"),
        letter(sender="digest@news.ru", subject="Дайджест",
               headers={"List-Unsubscribe": "<https://news.ru/off>"}),
    ])
    watcher = MailWatcher(core, settings(), mailboxes=[box])

    report = watcher.poll_once()

    assert report["new"] == 1 and report["skipped"] == 2
    assert [c.display_name for c in contacts_mod.all_contacts()] == ["Анна Ковалёва"]


def test_a_broken_mailbox_does_not_stop_the_others(core, mailbox):
    class Dead:
        account = ACCOUNT

        def fetch_unseen(self):
            raise OSError("соединение закрыто")

    alive = mailbox([letter()])
    watcher = MailWatcher(core, settings(), mailboxes=[Dead(), alive])

    report = watcher.poll_once()

    assert report["new"] == 1
    assert report["errors"] and "соединение закрыто" in report["errors"][0]


def test_polling_twice_adds_nothing_new(core, mailbox):
    box = mailbox([letter()])
    watcher = MailWatcher(core, settings(), mailboxes=[box])

    watcher.poll_once()
    second = watcher.poll_once()

    assert second["new"] == 0 and second["duplicates"] == 1


def test_old_unread_letters_are_left_alone(core, mailbox):
    """Иначе ящик с сотней старых непрочитанных завалил бы входящие."""
    box = mailbox([letter(), letter(subject="Прошлогоднее")])
    box.fetch_unseen = lambda: [
        incoming(),
        incoming(subject="Прошлогоднее", message_id="<old@example.com>",
                 ts=time.time() - 40 * 86400),
    ]
    watcher = MailWatcher(core, settings(), mailboxes=[box])

    report = watcher.poll_once()

    assert report["new"] == 1 and report["stale"] == 1
    assert [s["subject"] for s in pipeline.list_suggestions()] == ["Договор"]


def test_the_watcher_stays_asleep_without_accounts(core):
    watcher = MailWatcher(core, EmailConfig(accounts=()))
    assert watcher.start() is False
