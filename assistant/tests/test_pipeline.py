"""End-to-end pipeline: incoming messages, suggested replies, voice, no TTS."""
import pytest

from core import db, pipeline
from core.actions import ActionProvider
from core.agents import AgentResult, ReplyOptions
from domain import commitments as commitments_mod
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod


class FakeTelegramProvider(ActionProvider):
    action_types = ("send.telegram.message",)

    def __init__(self):
        self.sent = []

    def execute(self, action):
        self.sent.append(action.parameters)
        return {"message_id": len(self.sent), "transport": "fake"}


class StubSkills:
    """Stands in for the legacy skills module."""

    @staticmethod
    def detect_intents(text):
        return ["general"]

    @staticmethod
    def is_private(intents):
        return True

    @staticmethod
    def context_blocks(intents, text=""):
        return []

    @staticmethod
    def build_system(channel="chat", brain="local"):
        return "ты ассистент"

    @staticmethod
    def history(session):
        return []

    @staticmethod
    def remember(session, role, text):
        pass


@pytest.fixture
def core(monkeypatch):
    from conftest import FakeLLM
    from core.bootstrap import Core

    llm = FakeLLM(structured={"ReplyOptions": {
        "context_summary": "Обсуждали сервер X",
        "options": ["Да, готово.", "Сегодня закончу.", "Напомни, какой сервер?"]}},
        text="текстовый ответ")
    instance = Core(skills=StubSkills(), start_workers=False)
    instance.llm = llm
    instance.communication.llm = llm
    instance.personal.llm = llm
    instance.enricher.llm = llm
    provider = FakeTelegramProvider()
    instance.actions.providers = [provider]
    instance.telegram_provider = provider
    # Enrichment runs in the background in production; keep tests deterministic.
    monkeypatch.setattr(instance.enricher, "on_message", lambda *a, **k: None)
    # Сбор чужих чатов выключен; эти тесты проверяют сам конвейер.
    monkeypatch.setattr(pipeline, "telegram_ingest_allowed", lambda: True)
    yield instance
    instance.stop()


def incoming(text="Ну что, сервер поднялся?", peer_id="4242", name="Иван Петров"):
    return {"peer_id": peer_id, "peer_name": name, "text": text, "message_id": "m1",
            "history": [{"me": True, "text": "Настраиваю сервер X", "ts": 1},
                        {"me": False, "text": "ок, жду", "ts": 2}]}


# --- incoming message flow ------------------------------------------------
def test_telegram_ingest_is_off_unless_explicitly_enabled():
    assert pipeline.telegram_ingest_allowed() is False
    result = pipeline.ingest_incoming(None, incoming())
    assert result["disabled"] is True
    assert result["channel"] == "telegram"


def test_incoming_message_creates_contact_conversation_and_suggestions(core):
    result = pipeline.ingest_incoming(core, incoming())
    assert result["options"] == ["Да, готово.", "Сегодня закончу.",
                                 "Напомни, какой сервер?"]
    contact = contacts_mod.get(result["contact_id"])
    assert contact.display_name == "Иван Петров"
    conversation = conversations_mod.get(result["conversation_id"])
    assert conversation.platform == "telegram"


def test_history_is_backfilled_once(core):
    result = pipeline.ingest_incoming(core, incoming())
    messages = conversations_mod.messages(result["conversation_id"])
    assert [m.text for m in messages][:2] == ["Настраиваю сервер X", "ок, жду"]


def test_duplicate_incoming_message_is_dropped(core):
    pipeline.ingest_incoming(core, incoming())
    second = pipeline.ingest_incoming(core, incoming())
    assert second.get("duplicate") is True


def test_incoming_message_raises_a_notification(core):
    pipeline.ingest_incoming(core, incoming())
    pending = core.notifications.pending()
    assert pending and pending[0]["metadata"]["kind"] == "incoming_message"
    assert pending[0]["title"] == "Иван Петров"


def test_suggestion_prompt_includes_history_and_memory(core):
    from domain import memory as memory_mod
    contact = contacts_mod.upsert_from_telegram("4242", "Иван Петров")
    memory_mod.remember("Иван отвечает за сеть в офисе", type_="FACT",
                        source="TELEGRAM", entity_id=contact.id, confidence=0.8)
    pipeline.ingest_incoming(core, incoming())
    prompt = core.llm.calls[-1][-1]["content"]
    assert "Настраиваю сервер X" in prompt
    assert "отвечает за сеть" in prompt


def test_sending_a_suggestion_goes_through_the_action_engine(core):
    result = pipeline.ingest_incoming(core, incoming())
    sent = pipeline.send_reply(core, result["suggestion_id"], index=0)
    assert sent["status"] == "SUCCESS"
    assert core.telegram_provider.sent[0]["text"] == "Да, готово."
    assert core.telegram_provider.sent[0]["as_user"] is True


def test_sent_reply_is_stored_in_the_conversation(core):
    result = pipeline.ingest_incoming(core, incoming())
    pipeline.send_reply(core, result["suggestion_id"], index=1)
    texts = [m.text for m in conversations_mod.messages(result["conversation_id"])]
    assert "Сегодня закончу." in texts


def test_own_words_reply_is_sent_as_is(core):
    result = pipeline.ingest_incoming(core, incoming())
    sent = pipeline.send_reply(core, result["suggestion_id"], text="Перезвоню вечером")
    assert sent["status"] == "SUCCESS"
    assert core.telegram_provider.sent[0]["text"] == "Перезвоню вечером"


def test_resending_the_same_suggestion_is_idempotent(core):
    result = pipeline.ingest_incoming(core, incoming())
    pipeline.send_reply(core, result["suggestion_id"], index=0)
    pipeline.send_reply(core, result["suggestion_id"], index=0)
    assert len(core.telegram_provider.sent) == 1


def test_ignored_suggestion_sends_nothing(core):
    result = pipeline.ingest_incoming(core, incoming())
    pipeline.ignore_suggestion(result["suggestion_id"])
    assert pipeline.get_suggestion(result["suggestion_id"])["status"] == "IGNORED"
    assert core.telegram_provider.sent == []


def test_bad_suggestion_index_is_refused(core):
    result = pipeline.ingest_incoming(core, incoming())
    assert "error" in pipeline.send_reply(core, result["suggestion_id"], index=9)


# --- owner messages -------------------------------------------------------
def test_owner_message_gets_a_text_answer(core):
    result = pipeline.handle_message(core, "что у меня сегодня?", session="tg:1")
    assert result["reply"] == "текстовый ответ"
    assert "audio" not in result and "voice" not in result


def test_voice_message_is_stored_as_voice_with_transcription(core):
    pipeline.handle_message(core, "напомни завтра позвонить Сергею", session="tg:1",
                            message_type="VOICE",
                            transcription="напомни завтра позвонить Сергею")
    conversation = conversations_mod.get_or_create(pipeline.BOT_PLATFORM, "tg:1")
    stored = conversations_mod.messages(conversation.id)
    voice = [m for m in stored if m.message_type == "VOICE"]
    assert voice and voice[0].transcription == "напомни завтра позвонить Сергею"


def test_voice_and_text_take_the_same_path(core):
    text_result = pipeline.handle_message(core, "какие новости?", session="tg:1")
    voice_result = pipeline.handle_message(core, "какие новости?", session="tg:1",
                                           message_type="VOICE",
                                           transcription="какие новости?")
    assert text_result["agent"] == voice_result["agent"]
    assert text_result["reply"] == voice_result["reply"]


def test_assistant_never_produces_audio_actions(core):
    pipeline.handle_message(core, "расскажи новости", session="tg:1")
    types = [row["type"] for row in db.query("SELECT type FROM actions")]
    assert not any("voice" in t or "audio" in t or "tts" in t for t in types)


def test_owner_conversation_keeps_both_sides(core):
    pipeline.handle_message(core, "привет", session="tg:1")
    conversation = conversations_mod.get_or_create(pipeline.BOT_PLATFORM, "tg:1")
    senders = [m.sender_type for m in conversations_mod.messages(conversation.id)]
    assert senders == ["OWNER", "ASSISTANT"]


# --- agent routing --------------------------------------------------------
def test_communication_questions_go_to_the_communication_agent(core):
    contact = contacts_mod.upsert_from_telegram("999", "Иван")
    commitments_mod.create("прислать конфиг", direction="I_OWE",
                           counterparty_id=contact.id)
    result = pipeline.handle_message(core, "что я обещал?", session="tg:1")
    assert result["agent"] == "communication"
    assert "прислать конфиг" in result["reply"]


def test_waiting_question_lists_expected_replies(core):
    contact = contacts_mod.upsert_from_telegram("998", "Пётр")
    commitments_mod.create("пришлёт договор", direction="THEY_OWE",
                           counterparty_id=contact.id)
    result = pipeline.handle_message(core, "от кого я жду ответа?", session="tg:1")
    assert "Пётр" in result["reply"]


def test_contact_question_returns_a_profile(core):
    contacts_mod.upsert_from_telegram("997", "Сергей Иванов")
    result = pipeline.handle_message(core, "кто такой Сергей?", session="tg:1")
    assert "Сергей Иванов" in result["reply"]


def test_capitalised_question_does_not_read_as_a_name(core):
    """«Кто такой Сергей Тестов?» — имя, а не вопросительное слово «Кто»."""
    contacts_mod.upsert_from_telegram("994", "Сергей Тестов")
    result = pipeline.handle_message(core, "Кто такой Сергей Тестов?", session="tg:1")
    assert "Сергей Тестов" in result["reply"]


def test_ambiguous_contact_question_asks_back(core):
    contacts_mod.upsert_from_telegram("996", "Сергей Иванов")
    contacts_mod.upsert_from_telegram("995", "Сергей Петров")
    result = pipeline.handle_message(core, "кто такой Сергей?", session="tg:1")
    assert "несколько" in result["reply"].lower()


def test_general_questions_fall_back_to_the_personal_agent(core):
    result = pipeline.handle_message(core, "какая погода?", session="tg:1")
    assert result["agent"] == "personal"


# --- audit ----------------------------------------------------------------
def test_pipeline_writes_an_audit_chain(core):
    result = pipeline.ingest_incoming(core, incoming())
    pipeline.send_reply(core, result["suggestion_id"], index=0)
    core.bus.drain()
    events = [row["event"] for row in db.query("SELECT event FROM audit_log")]
    assert "telegram.message.received" in events
    assert "reply.sent" in events


# --- intent recognition ---------------------------------------------------
def test_communication_intents_are_recognised_by_rules():
    from core import intents as intents_mod
    cases = {"что я обещал Ивану?": "commitments",
             "от кого я жду ответа": "waiting_reply",
             "кто мне написал?": "who_wrote",
             "кто такой Сергей": "contact_info",
             "ответь Сергею": "suggest_reply"}
    for text, expected in cases.items():
        assert expected in intents_mod.detect(text), text


def test_unrelated_question_is_not_a_communication_intent():
    from core import intents as intents_mod
    detected = intents_mod.detect("какая погода в Москве?")
    assert not intents_mod.is_communication(detected)
