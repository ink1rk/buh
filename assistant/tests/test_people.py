"""Phase 2: contacts, entity resolution, conversations, commitments."""
import time

from domain import commitments as commitments_mod
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod
from domain import episodes as episodes_mod
from domain.enrichment import parse_due


# --- contacts ------------------------------------------------------------
def make(name, aliases=(), telegram_id=None, **kwargs):
    contact = contacts_mod.Contact(display_name=name, aliases=list(aliases),
                                   telegram_ids=[str(telegram_id)] if telegram_id else [],
                                   **kwargs)
    return contacts_mod.save(contact)


def test_telegram_contact_is_created_once(bus):
    first = contacts_mod.upsert_from_telegram(777, "Иван Петров", "ivan", bus=bus)
    second = contacts_mod.upsert_from_telegram(777, "Иван Петров", "ivan", bus=bus)
    assert first.id == second.id
    assert len(contacts_mod.all_contacts()) == 1


def test_username_is_kept_as_alias():
    contact = contacts_mod.upsert_from_telegram(778, "Иван Петров", "vanya")
    assert "vanya" in contact.aliases


def test_single_match_resolves_automatically():
    make("Сергей Иванов", aliases=["Серёга"])
    make("Мария Кузнецова")
    contact, candidates = contacts_mod.resolve_one("Серёга")
    assert contact is not None
    assert contact.display_name == "Сергей Иванов"


def test_nickname_resolves_to_full_name():
    contact = make("Сергей Иванов")
    resolved, _ = contacts_mod.resolve_one("Серёга")
    assert resolved is not None and resolved.id == contact.id


def test_two_matches_are_ambiguous():
    make("Сергей Иванов")
    make("Сергей Петров")
    contact, candidates = contacts_mod.resolve_one("Сергей")
    assert contact is None
    assert len(candidates) == 2


def test_unknown_name_resolves_to_nothing():
    make("Сергей Иванов")
    contact, candidates = contacts_mod.resolve_one("Афанасий")
    assert contact is None and candidates == []


def test_resolution_by_telegram_id():
    contact = make("Иван", telegram_id=12345)
    found, _ = contacts_mod.resolve_one("12345")
    assert found.id == contact.id


def test_style_is_derived_from_messages():
    contact = make("Иван")
    history = [{"from_owner": False, "text": "прив, ну че там с сервером?"},
               {"from_owner": False, "text": "ок"},
               {"from_owner": True, "text": "сделаю"}]
    contacts_mod.update_style(contact, history)
    style = contacts_mod.get(contact.id).communication_style
    assert style["length"] == "short"
    assert style["formality"] == "informal"


def test_formal_style_is_detected():
    contact = make("Директор")
    history = [{"from_owner": False,
                "text": "Здравствуйте! Прошу вас подготовить отчёт к пятнице, "
                        "он нужен для обсуждения с коллегами на совещании."}]
    contacts_mod.update_style(contact, history)
    assert contacts_mod.get(contact.id).communication_style["formality"] == "formal"


# --- conversations --------------------------------------------------------
def test_conversation_is_reused_for_the_same_peer(bus):
    first = conversations_mod.get_or_create("telegram", "555", bus=bus)
    second = conversations_mod.get_or_create("telegram", "555", bus=bus)
    assert first.id == second.id


def test_duplicate_message_is_ignored(bus):
    conversation = conversations_mod.get_or_create("telegram", "556", bus=bus)
    message = conversations_mod.Message(conversation_id=conversation.id, text="привет",
                                        external_id="42")
    _, first = conversations_mod.add_message(message, bus=bus)
    _, second = conversations_mod.add_message(
        conversations_mod.Message(conversation_id=conversation.id, text="привет",
                                  external_id="42"), bus=bus)
    assert first is True and second is False
    assert len(conversations_mod.messages(conversation.id)) == 1


def test_voice_message_keeps_transcription(bus):
    conversation = conversations_mod.get_or_create("telegram", "557", bus=bus)
    seen = []
    bus.subscribe("message.transcribed", lambda e: seen.append(e.payload))
    conversations_mod.add_message(conversations_mod.Message(
        conversation_id=conversation.id, text="напомни позвонить Сергею",
        message_type="VOICE", transcription="напомни позвонить Сергею"), bus=bus)
    bus.drain()
    stored = conversations_mod.messages(conversation.id)[0]
    assert stored.message_type == "VOICE"
    assert stored.transcription == "напомни позвонить Сергею"
    assert seen and seen[0]["text"] == "напомни позвонить Сергею"


def test_history_marks_who_wrote_what(bus):
    conversation = conversations_mod.get_or_create("telegram", "558", bus=bus)
    conversations_mod.add_message(conversations_mod.Message(
        conversation_id=conversation.id, text="привет", sender_type="CONTACT"))
    conversations_mod.add_message(conversations_mod.Message(
        conversation_id=conversation.id, text="здорово", sender_type="OWNER"))
    history = conversations_mod.as_history(conversation.id)
    assert [item["from_owner"] for item in history] == [False, True]


def test_summary_is_stored(bus):
    conversation = conversations_mod.get_or_create("telegram", "559", bus=bus)
    conversations_mod.set_summary(conversation.id, "Обсуждали сервер X", bus=bus)
    assert conversations_mod.get(conversation.id).summary == "Обсуждали сервер X"


def test_deleting_conversation_removes_messages(bus):
    conversation = conversations_mod.get_or_create("telegram", "560", bus=bus)
    conversations_mod.add_message(conversations_mod.Message(
        conversation_id=conversation.id, text="привет"))
    conversations_mod.delete(conversation.id)
    assert conversations_mod.get(conversation.id) is None
    assert conversations_mod.messages(conversation.id) == []


# --- episodes -------------------------------------------------------------
def test_episode_groups_a_burst_of_messages(bus):
    conversation = conversations_mod.get_or_create("telegram", "561", bus=bus)
    now = time.time()
    first = episodes_mod.upsert(conversation.id, summary="начали про сервер", ts=now,
                                bus=bus)
    second = episodes_mod.upsert(conversation.id, summary="закончили про сервер",
                                 ts=now + 600, bus=bus)
    assert first.id == second.id


def test_long_pause_starts_a_new_episode(bus):
    conversation = conversations_mod.get_or_create("telegram", "562", bus=bus)
    now = time.time()
    first = episodes_mod.upsert(conversation.id, summary="вчерашнее", ts=now - 86400)
    second = episodes_mod.upsert(conversation.id, summary="сегодняшнее", ts=now)
    assert first.id != second.id


# --- commitments ----------------------------------------------------------
def test_commitment_is_created(bus):
    contact = make("Иван")
    commitment = commitments_mod.create("прислать договор", direction="I_OWE",
                                        counterparty_id=contact.id, bus=bus)
    assert commitment.status == "OPEN"
    assert commitments_mod.i_owe()[0].description == "прислать договор"


def test_duplicate_commitment_is_not_doubled(bus):
    contact = make("Иван")
    first = commitments_mod.create("прислать договор завтра", counterparty_id=contact.id,
                                   bus=bus)
    second = commitments_mod.create("прислать договор завтра",
                                    counterparty_id=contact.id, bus=bus)
    assert first.id == second.id


def test_waiting_state_closes_when_they_answer(bus):
    contact = make("Иван")
    conversation = conversations_mod.get_or_create("telegram", "563",
                                                   contact_id=contact.id, bus=bus)
    commitments_mod.create("пришлёт договор", direction="THEY_OWE",
                           counterparty_id=contact.id, conversation_id=conversation.id,
                           bus=bus)
    assert len(commitments_mod.waiting_for_reply()) == 1
    commitments_mod.close_on_reply(conversation.id, contact.id, bus=bus)
    assert commitments_mod.waiting_for_reply() == []


def test_overdue_commitment_is_flagged(bus):
    commitment = commitments_mod.create("оплатить счёт", due_at=time.time() - 3600,
                                        bus=bus)
    commitments_mod.mark_overdue(bus)
    assert commitments_mod.get(commitment.id).status == "OVERDUE"


def test_completed_commitment_leaves_the_open_list(bus):
    commitment = commitments_mod.create("позвонить Сергею", bus=bus)
    commitments_mod.complete(commitment.id, bus=bus)
    assert commitments_mod.i_owe() == []


# --- due parsing ----------------------------------------------------------
def test_due_parsing_understands_tomorrow():
    import datetime
    from core.config import config
    now = datetime.datetime(2026, 9, 21, 10, 0, tzinfo=config.tz)
    parsed = datetime.datetime.fromtimestamp(parse_due("завтра к 14:00", now), config.tz)
    assert (parsed.day, parsed.hour) == (22, 14)


def test_due_parsing_understands_relative_hours():
    import datetime
    from core.config import config
    now = datetime.datetime(2026, 9, 21, 10, 0, tzinfo=config.tz)
    parsed = datetime.datetime.fromtimestamp(parse_due("через 3 часа", now), config.tz)
    assert parsed.hour == 13


def test_due_parsing_gives_up_gracefully():
    assert parse_due("когда-нибудь") is None
    assert parse_due("") is None
