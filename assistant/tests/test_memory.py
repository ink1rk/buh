"""Phase 2: memory write pipeline, provenance, dedupe, conflicts, retrieval."""
import time

from domain import memory as memory_mod


def test_explicit_statement_becomes_a_fact(bus):
    memory, outcome = memory_mod.remember(
        "Кирилл больше не работает в компании X", type_="FACT",
        source="USER_EXPLICIT", confidence=0.95, bus=bus)
    assert outcome == "created"
    assert memory.type == "FACT"
    assert memory.confidence >= 0.9


def test_inference_confidence_is_capped():
    memory, _ = memory_mod.remember("Похоже, он работает в Y", source="LLM_INFERENCE",
                                    confidence=0.99)
    assert memory.confidence <= 0.6


def test_low_confidence_is_not_stored():
    memory, outcome = memory_mod.remember("может быть что-то", confidence=0.1)
    assert memory is None
    assert outcome == "low_confidence"


def test_trivial_content_is_rejected():
    memory, outcome = memory_mod.remember("ок", source="USER_MESSAGE", confidence=0.9)
    assert memory is None and outcome == "rejected"


def test_new_statement_supersedes_the_old_one(bus):
    old, _ = memory_mod.remember("Кирилл работает в компании X", type_="FACT",
                                 source="USER_EXPLICIT", confidence=0.9)
    new, outcome = memory_mod.remember("Кирилл больше не работает в компании X",
                                       type_="FACT", source="USER_EXPLICIT",
                                       confidence=0.95, bus=bus)
    assert outcome == "superseded"
    assert new.supersedes_id == old.id
    assert memory_mod.get(old.id).status == "SUPERSEDED"


def test_weaker_contradiction_is_marked_as_conflict():
    memory_mod.remember("Кирилл работает в компании X", type_="FACT",
                        source="USER_EXPLICIT", confidence=0.95)
    weak, outcome = memory_mod.remember("Кирилл больше не работает в компании X",
                                        type_="FACT", source="LLM_INFERENCE",
                                        confidence=0.55)
    assert outcome == "conflict"
    assert weak.status == "CONFLICT"


def test_near_duplicates_reinforce_instead_of_multiplying():
    first, _ = memory_mod.remember("Кирилл любит крепкий кофе по утрам",
                                   type_="PREFERENCE", source="USER_MESSAGE",
                                   confidence=0.7)
    second, outcome = memory_mod.remember("Кирилл любит крепкий кофе утром",
                                          type_="PREFERENCE", source="USER_MESSAGE",
                                          confidence=0.7)
    assert outcome == "reinforced"
    assert second.id == first.id
    assert len(memory_mod.list_memories(type_="PREFERENCE")) == 1


def test_different_topics_are_kept_apart():
    memory_mod.remember("Кирилл любит кофе", type_="PREFERENCE",
                        source="USER_MESSAGE", confidence=0.8)
    memory_mod.remember("Кирилл ездит на работу на велосипеде", type_="PREFERENCE",
                        source="USER_MESSAGE", confidence=0.8)
    assert len(memory_mod.list_memories(type_="PREFERENCE")) == 2


def test_search_ranks_relevant_memories_first():
    memory_mod.remember("Сервер X стоит в офисе на третьем этаже", type_="FACT",
                        source="USER_MESSAGE", confidence=0.8)
    memory_mod.remember("Кирилл любит горные лыжи", type_="PREFERENCE",
                        source="USER_MESSAGE", confidence=0.8)
    results = memory_mod.search("где стоит сервер")
    assert results
    assert "Сервер X" in results[0][0].content


def test_entity_memories_are_boosted():
    memory_mod.remember("Работает в банке", type_="FACT", source="TELEGRAM",
                        entity_id="cnt-ivan", confidence=0.7)
    memory_mod.remember("Работает в банке", type_="FACT", source="TELEGRAM",
                        entity_id="cnt-petr", confidence=0.7)
    results = memory_mod.search("работа", entity_id="cnt-ivan")
    assert results[0][0].entity_id == "cnt-ivan"


def test_expired_memory_is_not_returned():
    memory_mod.remember("Временный пропуск действует до пятницы", type_="EVENT",
                        source="USER_MESSAGE", confidence=0.8,
                        expires_at=time.time() - 60)
    assert memory_mod.search("пропуск") == []


def test_delete_removes_the_row_completely(bus):
    memory, _ = memory_mod.remember("Секретная заметка про проект", source="USER_EXPLICIT",
                                    confidence=0.9)
    memory_mod.delete(memory.id, bus=bus)
    assert memory_mod.get(memory.id) is None
    assert memory_mod.search("Секретная заметка") == []


def test_memory_events_are_published(bus):
    seen = []
    bus.subscribe("memory.*", lambda e: seen.append(e.type))
    memory_mod.remember("Кирилл живёт в Москве", type_="FACT", source="USER_EXPLICIT",
                        confidence=0.9, bus=bus)
    bus.drain()
    assert "memory.created" in seen
