"""Background enrichment: what gets remembered, what becomes a task."""
import pytest

from domain import commitments as commitments_mod
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod
from domain import memory as memory_mod
from domain.enrichment import Enricher


@pytest.fixture
def setup(bus):
    from conftest import FakeLLM
    llm = FakeLLM()
    enricher = Enricher(llm, bus)
    contact = contacts_mod.save(contacts_mod.Contact(display_name="Иван"))
    conversation = conversations_mod.get_or_create("telegram", "700",
                                                   contact_id=contact.id, bus=bus)
    return enricher, llm, bus, contact, conversation


def message(conversation, text, **kwargs):
    item = conversations_mod.Message(conversation_id=conversation.id, text=text, **kwargs)
    conversations_mod.add_message(item)
    return item


def test_statement_is_stored_as_a_fact(setup):
    enricher, llm, bus, contact, conversation = setup
    llm.structured = {"MemoryExtraction": {
        "memories": [{"type": "FACT", "content": "Кирилл больше не работает в X",
                      "confidence": 0.9, "importance": 0.7, "about": "owner"}],
        "tasks": []}}
    enricher._extract_memories(conversation, contact,
                               message(conversation, "Я больше не работаю в X"),
                               from_owner=True)
    stored = memory_mod.list_memories(type_="FACT")
    assert [m.content for m in stored] == ["Кирилл больше не работает в X"]
    assert stored[0].source == "USER_MESSAGE"


def test_greeting_leaves_no_memory(setup):
    enricher, llm, bus, contact, conversation = setup
    llm.structured = {"MemoryExtraction": {"memories": [], "tasks": []}}
    enricher._extract_memories(conversation, contact,
                               message(conversation, "Привет"), from_owner=False)
    assert memory_mod.list_memories() == []
    assert llm.calls == []          # даже модель не вызывали


def test_reminder_becomes_a_task_not_a_memory(setup):
    enricher, llm, bus, contact, conversation = setup
    seen = []
    bus.subscribe("task.candidate.detected", lambda e: seen.append(e.payload["text"]))
    enricher._extract_memories(conversation, contact,
                               message(conversation, "Напомни завтра купить молоко"),
                               from_owner=True)
    bus.drain()
    assert memory_mod.list_memories() == []
    assert seen == ["Напомни завтра купить молоко"]


def test_contact_facts_are_attached_to_the_contact(setup):
    enricher, llm, bus, contact, conversation = setup
    llm.structured = {"MemoryExtraction": {
        "memories": [{"type": "FACT", "content": "Иван работает в компании X",
                      "confidence": 0.8, "importance": 0.6, "about": "contact"}],
        "tasks": []}}
    enricher._extract_memories(conversation, contact,
                               message(conversation, "Я теперь работаю в компании X"),
                               from_owner=False)
    stored = memory_mod.list_memories()
    assert stored[0].entity_id == contact.id
    assert stored[0].source == "TELEGRAM"


def test_promise_creates_a_commitment(setup):
    enricher, llm, bus, contact, conversation = setup
    llm.structured = {"CommitmentExtraction": {"commitments": [
        {"description": "прислать конфиг", "direction": "I_OWE",
         "due_hint": "завтра", "confidence": 0.8}]}}
    enricher._extract_commitments(conversation, contact,
                                  message(conversation, "Пришлю конфиг завтра"),
                                  from_owner=True)
    open_items = commitments_mod.i_owe()
    assert [c.description for c in open_items] == ["прислать конфиг"]
    assert open_items[0].due_at is not None


def test_request_from_them_creates_an_expectation(setup):
    enricher, llm, bus, contact, conversation = setup
    llm.structured = {"CommitmentExtraction": {"commitments": [
        {"description": "прислать договор", "direction": "THEY_OWE",
         "due_hint": "завтра", "confidence": 0.9}]}}
    enricher._extract_commitments(conversation, contact,
                                  message(conversation, "Пришли мне договор завтра"),
                                  from_owner=True)
    assert [c.description for c in commitments_mod.waiting_for_reply()] == \
        ["прислать договор"]


def test_low_confidence_commitment_is_skipped(setup):
    enricher, llm, bus, contact, conversation = setup
    llm.structured = {"CommitmentExtraction": {"commitments": [
        {"description": "возможно созвониться", "direction": "I_OWE",
         "due_hint": "", "confidence": 0.3}]}}
    enricher._extract_commitments(conversation, contact,
                                  message(conversation, "Может как-нибудь созвонимся"),
                                  from_owner=True)
    assert commitments_mod.i_owe() == []


def test_their_reply_closes_the_waiting_state(setup):
    enricher, llm, bus, contact, conversation = setup
    commitments_mod.create("пришлёт договор", direction="THEY_OWE",
                           counterparty_id=contact.id, conversation_id=conversation.id)
    llm.structured = {"CommitmentExtraction": {"commitments": []}}
    enricher._extract_commitments(conversation, contact,
                                  message(conversation, "Вот договор, смотри"),
                                  from_owner=False)
    assert commitments_mod.waiting_for_reply() == []


def test_summary_and_episode_are_written(setup):
    enricher, llm, bus, contact, conversation = setup
    from domain import episodes as episodes_mod
    llm.structured = {"ConversationSummary": {
        "summary": "Обсуждали сервер X, Кирилл закончил настройку",
        "title": "Сервер X", "decisions": ["перезапустить ночью"],
        "entities": ["сервер X"]}}
    for text in ("Что с сервером?", "Настроил", "Спасибо"):
        last = message(conversation, text)
    enricher._maybe_summarise(conversations_mod.get(conversation.id), contact, last,
                              from_owner=False)
    assert "сервер X" in conversations_mod.get(conversation.id).summary
    episodes = episodes_mod.for_conversation(conversation.id)
    assert episodes and episodes[0].title == "Сервер X"


def test_broken_step_does_not_stop_the_others(setup):
    enricher, llm, bus, contact, conversation = setup

    def explode(*args, **kwargs):
        raise RuntimeError("модель недоступна")

    llm.structured_output = explode
    enricher._safe_process(conversation, contact,
                           message(conversation, "Пришлю конфиг завтра вечером"),
                           from_owner=True)
    # style detection does not need the model and still runs
    assert contacts_mod.get(contact.id) is not None
