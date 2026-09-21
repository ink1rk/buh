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
           sender="Анна Ковалёва <anna@example.com>", headers=None, html=False,
           message_id=None, ts=None):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ACCOUNT.user
    message["Subject"] = subject
    message["Date"] = email.utils.formatdate(ts, localtime=True)
    message["Message-ID"] = message_id or email.utils.make_msgid()
    for key, value in (headers or {}).items():
        message[key] = value
    message.set_content(body)
    if html:
        message.add_alternative(f"<html><body><p>{body}</p></body></html>",
                                subtype="html")
    return message


class FakeIMAP:
    """Столько от IMAP, сколько использует Mailbox — включая UID."""

    def __init__(self, messages, uidvalidity=7, first_uid=100):
        self.uidvalidity = uidvalidity
        self.by_uid = {first_uid + i: m for i, m in enumerate(messages)}
        self.next_uid = first_uid + len(messages)
        self.logged_out = False
        self.readonly = None

    def deliver(self, message):
        """Пришло новое письмо — UID больше всех прежних."""
        self.by_uid[self.next_uid] = message
        self.next_uid += 1

    def select(self, folder, readonly=False):
        self.readonly = readonly
        return ("OK", [b"1"])

    def status(self, folder, what):
        return ("OK", [f'"{folder}" (UIDVALIDITY {self.uidvalidity})'.encode()])

    def uid(self, command, *args):
        if command == "search":
            return ("OK", [b" ".join(str(u).encode()
                                     for u in sorted(self.by_uid))])
        uid, spec = args
        assert "PEEK" in spec           # прочитанным письмо делает человек
        return ("OK", [(b"header", self.by_uid[int(uid)].as_bytes())])

    def logout(self):
        self.logged_out = True


@pytest.fixture
def mailbox(monkeypatch):
    def build(messages, cfg=None, **options):
        box = Mailbox(ACCOUNT, cfg or settings())
        fake = FakeIMAP(messages, **options)
        monkeypatch.setattr(box, "_connect", lambda: fake)
        box.fake = fake
        return box
    return build


def catch_up(watcher):
    """Первый опрос отмечает прошлое ящика; дальше идут только новые письма."""
    started = watcher.poll_once()
    assert started["new"] == 0 and started["started"]
    return started


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


@pytest.mark.parametrize("address", [
    "echeck@1-ofd.ru", "receipt@shop.ru", "invoice@billing.com",
    "order-3312@market.ru", "noreply-service@bank.ru", "alerts@monitor.io"])
def test_transactional_robots_are_caught_by_name(address):
    """Чеки и счёта не носят заголовков рассылки — узнать их можно только так."""
    assert not looks_personal(address, ["From"], settings(), lists={})


@pytest.mark.parametrize("address", [
    "newsome@gmail.com", "billy@example.com", "checkanov@yandex.ru",
    "orlov@mail.ru", "infanteev@corp.ru"])
def test_people_whose_names_start_like_robots_get_through(address):
    """Сверяется имя ящика целиком, иначе «news» ловил бы Newsome."""
    assert looks_personal(address, ["From"], settings(), lists={})


def test_the_owner_overrules_the_heuristic(isolated_db):
    """Отбор не безошибочен, поэтому слово владельца сильнее любого правила."""
    from providers.email import mark_sender, sender_lists

    assert not looks_personal("echeck@1-ofd.ru", ["From"], settings())

    mark_sender("echeck@1-ofd.ru", robot=False)
    assert looks_personal("echeck@1-ofd.ru", ["From"], settings())
    assert sender_lists()["allowed"] == ["echeck@1-ofd.ru"]

    mark_sender("echeck@1-ofd.ru", robot=True)
    assert not looks_personal("echeck@1-ofd.ru", ["From"], settings())
    assert sender_lists() == {"muted": ["echeck@1-ofd.ru"], "allowed": []}


def test_a_person_can_be_muted_too(isolated_db):
    from providers.email import mark_sender

    mark_sender("anna@example.com", robot=True)
    assert not looks_personal("anna@example.com", ["From"], settings())


def test_skipped_senders_are_not_lost_silently(core, mailbox):
    """Если сюда попал человек, владелец должен это увидеть."""
    box = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[box])
    catch_up(watcher)

    box.fake.deliver(letter(sender="no-reply@ozon.ru", subject="Скидки"))
    box.fake.deliver(letter(sender="no-reply@ozon.ru", subject="Ещё скидки"))
    box.fake.deliver(letter(sender="echeck@1-ofd.ru", subject="Чек"))
    report = watcher.poll_once()

    assert report["skipped"] == 3
    assert report["skipped_senders"] == [{"address": "no-reply@ozon.ru", "count": 2},
                                         {"address": "echeck@1-ofd.ru", "count": 1}]


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
def test_the_first_poll_only_marks_the_past(core, mailbox):
    """Ящик со старой перепиской не должен превратиться в сотню подсказок."""
    box = mailbox([letter(), letter(subject="Ещё")])
    report = MailWatcher(core, settings(), mailboxes=[box]).poll_once()

    assert report["new"] == 0 and report["started"] == [ACCOUNT.address]
    assert pipeline.list_suggestions() == []


def test_a_letter_arriving_later_is_picked_up(core, mailbox):
    box = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[box])
    catch_up(watcher)

    box.fake.deliver(letter())
    report = watcher.poll_once()

    assert report["new"] == 1
    assert [s["subject"] for s in pipeline.list_suggestions()] == ["Договор"]


def test_a_person_is_not_lost_behind_a_wave_of_newsletters(core, mailbox):
    """Опрос по непрочитанным брал только последние: письмо человека тонуло."""
    roomy = settings(max_per_poll=50)
    box = mailbox([letter(subject="Прошлое")], cfg=roomy)
    watcher = MailWatcher(core, roomy, mailboxes=[box])
    catch_up(watcher)

    box.fake.deliver(letter())
    for i in range(20):
        box.fake.deliver(letter(sender="no-reply@ozon.ru", subject=f"Скидки {i}",
                                message_id=f"<ad{i}@ozon.ru>"))

    report = watcher.poll_once()

    assert report["new"] == 1 and report["skipped"] == 20
    assert [s["subject"] for s in pipeline.list_suggestions()] == ["Договор"]


def test_the_watcher_ignores_mailing_lists(core, mailbox):
    box = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[box])
    catch_up(watcher)

    box.fake.deliver(letter())
    box.fake.deliver(letter(sender="no-reply@ozon.ru", subject="Скидки",
                            message_id="<ad@ozon.ru>"))
    box.fake.deliver(letter(sender="digest@news.ru", subject="Дайджест",
                            message_id="<d@news.ru>",
                            headers={"List-Unsubscribe": "<https://news.ru/off>"}))

    report = watcher.poll_once()

    assert report["new"] == 1 and report["skipped"] == 2
    assert [c.display_name for c in contacts_mod.all_contacts()] == ["Анна Ковалёва"]


def test_a_recreated_mailbox_starts_over_instead_of_flooding(core, mailbox):
    """Смена UIDVALIDITY обнуляет нумерацию: старые UID больше ничего не значат."""
    box = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[box])
    catch_up(watcher)

    box.fake.uidvalidity = 99
    report = watcher.poll_once()

    assert report["new"] == 0 and report["started"] == [ACCOUNT.address]


def test_a_broken_mailbox_does_not_stop_the_others(core, mailbox):
    class Dead:
        account = ACCOUNT

        def fetch_new(self, state):
            raise OSError("соединение закрыто")

    alive = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[Dead(), alive])
    catch_up(watcher)
    alive.fake.deliver(letter())

    report = watcher.poll_once()

    assert report["new"] == 1
    assert report["errors"] and "соединение закрыто" in report["errors"][0]


def test_polling_twice_adds_nothing_new(core, mailbox):
    box = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[box])
    catch_up(watcher)
    box.fake.deliver(letter())

    first = watcher.poll_once()
    second = watcher.poll_once()

    assert first["new"] == 1
    assert second["new"] == 0 and second["skipped"] == 0


def test_old_letters_are_left_alone(core, mailbox):
    """Письмо, пролежавшее месяц, не стоит поднимать как срочное."""
    box = mailbox([letter(subject="Прошлое")])
    watcher = MailWatcher(core, settings(), mailboxes=[box])
    catch_up(watcher)

    box.fake.deliver(letter())
    box.fake.deliver(letter(subject="Прошлогоднее", message_id="<old@example.com>",
                            ts=time.time() - 40 * 86400))

    report = watcher.poll_once()

    assert report["new"] == 1 and report["stale"] == 1
    assert [s["subject"] for s in pipeline.list_suggestions()] == ["Договор"]


def test_the_watcher_stays_asleep_without_accounts(core):
    watcher = MailWatcher(core, EmailConfig(accounts=()))
    assert watcher.start() is False
