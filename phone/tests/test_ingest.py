"""Приём данных с телефона: повторы, форматы Apple и приватность."""
import dataclasses

import pytest
from conftest import at

from phone import ingest, store
from phone.config import config


def call(**overrides):
    payload = {"direction": "incoming", "status": "answered", "peer_name": "Саша",
               "peer_number": "+7 (999) 123-45-67", "started_at": at(0, 11),
               "duration": 125}
    payload.update(overrides)
    return payload


# --- повторы -------------------------------------------------------------
def test_the_same_batch_twice_is_one_call(device):
    """Ярлык не помнит, что уже отправлял: при плохой связи он повторит всё."""
    first = ingest.ingest_calls([call(external_id="A1")], device[0]["id"])
    again = ingest.ingest_calls([call(external_id="A1")], device[0]["id"])

    assert first["new"] == 1 and again["duplicates"] == 1
    assert len(store.calls()) == 1


def test_a_call_without_an_id_is_still_recognised(device):
    """iOS не даёт идентификатор звонка — ключ приходится считать самим."""
    ingest.ingest_calls([call()], device[0]["id"])
    ingest.ingest_calls([call()], device[0]["id"])

    assert len(store.calls()) == 1


def test_two_different_calls_are_two_records(device):
    ingest.ingest_calls([call(started_at=at(0, 11)), call(started_at=at(0, 15))],
                        device[0]["id"])
    assert len(store.calls()) == 2


# --- разбор звонка -------------------------------------------------------
def test_an_incoming_call_of_zero_length_is_missed(device):
    """Телефон не всегда пишет статус; нулевая длительность говорит сама."""
    ingest.ingest_calls([call(status=None, duration=0)], device[0]["id"])
    assert store.calls()[0]["status"] == "missed"


def test_the_stated_status_wins(device):
    ingest.ingest_calls([call(status="voicemail", duration=0)], device[0]["id"])
    assert store.calls()[0]["status"] == "voicemail"


@pytest.mark.parametrize("raw", ["+7 (999) 123-45-67", "89991234567", "8 999 123 45 67",
                                 "+79991234567"])
def test_numbers_in_any_format_are_one_person(raw):
    assert ingest.normalize_number(raw) == "+79991234567"


@pytest.mark.parametrize("raw", [
    1758443400, "1758443400", "2026-09-21T08:30:00+03:00", "2026-09-21 08:30:00 +0300",
    "2026-09-21 08:30:00", "21.09.2026 08:30",
])
def test_time_comes_in_every_shape(raw):
    assert ingest.parse_time(raw) > 1_700_000_000


def test_milliseconds_are_not_the_year_57000():
    assert ingest.parse_time(1758443400000) == pytest.approx(1758443400, abs=1)


def test_a_broken_row_does_not_reject_the_batch(device):
    """Одна кривая строка не должна заставить телефон слать пакет вечно."""
    report = ingest.ingest_calls(
        [call(), call(started_at="позавчера вечером")], device[0]["id"])

    assert report["new"] == 1
    assert report["rejected"][0]["index"] == 1


# --- переписка -----------------------------------------------------------
def test_message_text_is_not_stored(device):
    """От сообщения остаётся форма — кто, когда и сколько, — а не содержание."""
    ingest.ingest_messages([{"app": "imessage", "direction": "incoming",
                             "peer_name": "Аня", "text": "Привет, позвони мне",
                             "ts": at(0, 10)}], device[0]["id"])

    [saved] = store.messages()
    assert saved["preview"] == ""
    assert saved["chars"] == len("Привет, позвони мне")


def test_text_is_kept_only_when_asked(monkeypatch, device):
    monkeypatch.setattr(ingest, "config",
                        dataclasses.replace(config, store_text=True))
    ingest.ingest_messages([{"direction": "incoming", "peer_name": "Аня",
                             "text": "Привет", "ts": at(0, 10)}], device[0]["id"])

    assert store.messages()[0]["preview"] == "Привет"


# --- здоровье ------------------------------------------------------------
def test_apple_identifiers_map_to_one_metric(device):
    ingest.ingest_health([
        {"metric": "HKQuantityTypeIdentifierStepCount", "value": 4000,
         "start": at(0, 9), "unit": "count"},
        {"metric": "step_count", "value": 3000, "start": at(0, 14), "unit": "count"},
    ], device[0]["id"])

    assert {s["metric"] for s in store.samples()} == {"steps"}


def test_sleep_in_minutes_becomes_hours(device):
    ingest.ingest_health([{"metric": "sleep_analysis", "value": 402, "unit": "min",
                           "start": at(1, 23), "end": at(0, 6)}], device[0]["id"])

    [sample] = store.samples()
    assert sample["value"] == pytest.approx(6.7, abs=0.01)
    assert sample["unit"] == "ч"


def test_sleep_without_a_value_is_read_from_the_interval(device):
    """Ярлык умеет отдать «лёг — встал», но не умеет посчитать часы."""
    ingest.ingest_health([{"metric": "sleep", "start": at(1, 23), "end": at(0, 6),
                           "value": 1}], device[0]["id"])

    assert store.samples()[0]["value"] == pytest.approx(7.0, abs=0.01)


def test_health_auto_export_format_is_understood(device):
    """Приложение выгрузки шлёт свой формат — пусть шлёт прямо в мост."""
    ingest.ingest_batch({"data": {"metrics": [
        {"name": "step_count", "units": "count",
         "data": [{"date": "2026-09-20 00:00:00 +0300", "qty": 8123}]},
        {"name": "resting_heart_rate", "units": "bpm",
         "data": [{"date": "2026-09-20 00:00:00 +0300", "qty": 54}]},
    ]}}, device[0]["id"])

    assert {s["metric"] for s in store.samples()} == {"steps", "resting_hr"}


def test_a_workout_length_is_taken_from_the_interval(device):
    ingest.ingest_workouts([{"kind": "Бег", "start": at(0, 8), "end": at(0, 9)}],
                           device[0]["id"])

    assert store.workouts()[0]["duration"] == pytest.approx(60, abs=0.1)


def test_battery_fraction_becomes_percent(device):
    ingest.ingest_state({"battery": 0.32, "charging": False, "focus": "Работа"},
                        device[0]["id"])

    [state] = store.states()
    assert state["battery"] == pytest.approx(32)
    assert state["focus"] == "Работа"


# --- пакет целиком -------------------------------------------------------
def test_a_batch_touches_the_device(device):
    ingest.ingest_batch({"calls": [call()], "health": [
        {"metric": "steps", "value": 1200, "start": at(0, 9)}]}, device[0]["id"])

    assert store.device(device[0]["id"])["last_seen_at"] is not None


def test_an_empty_batch_is_not_an_error(device):
    assert ingest.ingest_batch({}, device[0]["id"])["accepted"] == 0


def test_fahrenheit_becomes_celsius(device):
    ingest.ingest_health([{"metric": "body_temperature", "value": 98.6,
                           "unit": "degF", "start": at(0, 8)}], device[0]["id"])
    assert store.samples()[0]["value"] == pytest.approx(37.0, abs=0.05)


def test_an_unknown_metric_is_kept(device):
    """Выгрузка присылает всё — неизвестное имя не повод выбросить замер."""
    ingest.ingest_health([{"metric": "HKQuantityTypeIdentifierUvExposure",
                           "value": 3, "start": at(0, 12)}], device[0]["id"])
    assert store.samples()[0]["metric"] == "uvexposure"
