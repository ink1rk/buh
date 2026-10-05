"""Папки IMAP: список, частые отправители и создание без перекладки писем."""
import email.utils

from core.config import EmailConfig, MailAccount
from providers.email import (Mailbox, decode_imap_utf7, encode_imap_utf7,
                             folder_name_for)

ACCOUNT = MailAccount(name="yandex", user="kirill@yandex.ru", password="secret",
                      imap_host="imap.yandex.ru", imap_port=993,
                      smtp_host="smtp.yandex.ru", smtp_port=465)


def settings():
    return EmailConfig(accounts=(ACCOUNT,))


def letter(sender, subject="тема"):
    from email.message import EmailMessage
    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = subject
    message["Date"] = email.utils.formatdate(localtime=True)
    message.set_content("текст")
    return message


class FakeIMAP:
    def __init__(self, messages):
        self.by_uid = {100 + i: m for i, m in enumerate(messages)}
        self.folders = ["INBOX"]
        self.created = []
        self.readonly = None

    def list(self):
        lines = [f'(\\HasNoChildren) "/" "{encode_imap_utf7(name)}"'.encode()
                 for name in self.folders]
        return ("OK", lines)

    def select(self, folder, readonly=False):
        self.readonly = readonly
        if folder not in self.folders:
            return ("NO", [b"missing"])
        return ("OK", [b"1"])

    def create(self, mailbox):
        self.created.append(mailbox)
        self.folders.append(decode_imap_utf7(mailbox))
        return ("OK", [b"Completed"])

    def uid(self, command, *args):
        if command == "search":
            return ("OK", [b" ".join(str(uid).encode() for uid in sorted(self.by_uid))])
        uid, spec = args
        assert "PEEK" in spec
        return ("OK", [(b"header", self.by_uid[int(uid)].as_bytes())])

    def logout(self):
        return ("OK", [b"bye"])


def box(messages):
    fake = FakeIMAP(messages)
    mailbox = Mailbox(ACCOUNT, settings())
    mailbox._connect = lambda: fake
    return mailbox, fake


def test_utf7_roundtrip_keeps_cyrillic_and_ampersand():
    for name in ("GitHub", "Кирилл", "A & B"):
        assert decode_imap_utf7(encode_imap_utf7(name)) == name


def test_folder_name_drops_imap_separators():
    assert folder_name_for("news@github.com", "") == "github.com"
    assert "/" not in folder_name_for("a@b.c", "A/B|C")
    assert folder_name_for("anna@example.com", "Анна") == "Анна"


def test_frequent_senders_are_counted_not_invented():
    messages = [letter("GitHub <noreply@github.com>", "build")] * 4
    messages += [letter("Анна <anna@example.com>", "договор")]
    mailbox, fake = box(messages)

    ranking = mailbox.frequent_senders(sample=10)

    assert ranking["sampled"] == 5
    assert ranking["senders"][0]["address"] == "noreply@github.com"
    assert ranking["senders"][0]["count"] == 4
    assert fake.readonly is True
    assert "secret" not in str(ranking)


def test_create_sender_folders_creates_only_the_repeated_ones():
    messages = [letter("GitHub <noreply@github.com>")] * 5
    messages += [letter("Анна <anna@example.com>")]
    mailbox, fake = box(messages)

    made = mailbox.create_sender_folders(sample=10, min_count=5, max_folders=10)

    assert [item["folder"] for item in made["created"]] == ["GitHub"]
    assert made["already"] == []
    assert fake.created == [encode_imap_utf7("GitHub")]
    assert "GitHub" in mailbox.list_folders()


def test_an_existing_folder_is_not_created_again():
    mailbox, fake = box([letter("GitHub <noreply@github.com>")] * 3)
    fake.folders.append("GitHub")

    made = mailbox.create_sender_folders(sample=10, min_count=2, max_folders=5)

    assert made["created"] == []
    assert made["already"][0]["folder"] == "GitHub"
    assert fake.created == []


def test_inbox_cannot_be_created():
    mailbox, _ = box([])
    try:
        mailbox.create_folder("INBOX")
    except Exception as exc:
        assert "INBOX" in str(exc)
    else:
        raise AssertionError("INBOX не должен создаваться")
