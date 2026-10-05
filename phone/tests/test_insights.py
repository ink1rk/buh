"""Смысл поверх замеров: норма человека, отклонения и незакрытые разговоры."""
import time

import pytest
from conftest import at

from phone import ingest, insights, store


def health(metric, value, days_ago=0, hour=12, end_hour=None):
    sample = {"metric": metric, "value": value, "start": at(days_ago, hour)}
    if end_hour is not None:
        sample["end"] = at(days_ago - 1 if end_hour < hour else days_ago, end_hour)
    ingest.ingest_health([sample])


def routine(metric, value, days=14, **kwargs):
    """Две недели одинаковых дней — это и есть норма человека."""
    for day in range(1, days + 1):
        health(metric, value, days_ago=day, **kwargs)


# --- норма и отклонения --------------------------------------------------
def test_a_number_comes_with_your_own_norm():
    routine("steps", 11000)
    health("steps", 4000)

    steps = insights.health_today()["steps"]

    assert steps["value"] == 4000
    assert steps["baseline"] == 11000
    assert steps["delta_pct"] == -64


def test_today_does_not_count_towards_its_own_norm():
    """Иначе рекордный день сам себя объявил бы нормой."""
    routine("resting_hr", 54)
    health("resting_hr", 70)

    assert insights.health_today()["resting_hr"]["baseline"] == 54


def test_one_marathon_does_not_move_the_norm():
    routine("steps", 9000, days=13)
    health("steps", 60000, days_ago=14)
    health("steps", 9000)

    assert insights.health_today()["steps"]["baseline"] == 9000


def test_a_short_night_is_worth_saying_out_loud():
    routine("sleep", 7.5)
    health("sleep", 4.5)

    [found] = [item for item in insights.anomalies() if item["metric"] == "sleep"]
    assert found["severity"] == "medium"
    assert "4.5" in found["title"]


def test_a_rested_night_is_not_an_anomaly():
    routine("sleep", 7.5)
    health("sleep", 7.6)

    assert insights.anomalies() == []


def test_a_raised_resting_pulse_is_the_loudest_signal():
    """Пульс покоя выше своей нормы — первый признак, что человек заболевает."""
    routine("resting_hr", 54)
    health("resting_hr", 62)

    [found] = insights.anomalies()
    assert found["metric"] == "resting_hr" and found["severity"] == "high"


def test_a_night_belongs_to_the_morning():
    """Сон с 23:00 до 07:00 — это сегодняшняя ночь, а не вчерашний вечер."""
    ingest.ingest_health([{"metric": "sleep", "start": at(1, 23), "end": at(0, 7),
                           "value": 8, "unit": "ч"}])

    assert insights.metric_today("sleep") == 8


def test_without_history_there_is_no_verdict():
    """Первый день с телефоном: число есть, нормы нет — и молчим про норму."""
    health("steps", 3000)

    assert insights.health_today()["steps"]["baseline"] is None
    assert insights.anomalies() == []


# --- незакрытые разговоры ------------------------------------------------
def missed(hours_ago=3, name="Саша", number="+79991234567"):
    ingest.ingest_calls([{"direction": "incoming", "status": "missed",
                          "peer_name": name, "peer_number": number,
                          "started_at": time.time() - hours_ago * 3600,
                          "duration": 0}])


def test_a_missed_call_waits_for_an_answer():
    missed()

    [waiting] = insights.waiting_for_reply()
    assert waiting["who"] == "Саша" and waiting["what"] == "пропущенный звонок"


def test_calling_back_closes_it():
    missed()
    ingest.ingest_calls([{"direction": "outgoing", "status": "answered",
                          "peer_number": "+79991234567",
                          "started_at": time.time() - 3600, "duration": 90}])

    assert insights.waiting_for_reply() == []


def test_the_same_person_on_two_channels_is_one_debt():
    """Позвонил и написал — это один незакрытый разговор, а не два."""
    missed(hours_ago=5)
    ingest.ingest_messages([{"direction": "incoming", "peer_name": "Саша",
                             "peer_number": "+79991234567", "text": "ты тут?",
                             "ts": time.time() - 4 * 3600}])

    assert len(insights.waiting_for_reply()) == 1


def test_a_message_from_a_minute_ago_is_not_yet_a_debt():
    """Человек мог ещё не дойти до телефона — это не повод дёргать."""
    ingest.ingest_messages([{"direction": "incoming", "peer_name": "Аня",
                             "text": "привет", "ts": time.time() - 120}])

    assert insights.waiting_for_reply() == []


def test_an_answered_call_owes_nothing():
    ingest.ingest_calls([{"direction": "incoming", "status": "answered",
                          "peer_name": "Аня", "peer_number": "+79990000000",
                          "started_at": time.time() - 7200, "duration": 300}])

    assert insights.waiting_for_reply() == []


# --- состояние моста -----------------------------------------------------
def test_a_silent_bridge_is_a_problem(device):
    store.touch_device(device[0]["id"], when=time.time() - 12 * 3600)

    [problem] = [p for p in insights.problems() if p["kind"] == "bridge"]
    assert "молчит" in problem["title"]


def test_a_fresh_sync_is_not_a_problem(device):
    store.touch_device(device[0]["id"])

    assert [p for p in insights.problems() if p["kind"] == "bridge"] == []


def test_a_dying_battery_is_worth_a_word(device):
    ingest.ingest_state({"battery": 9, "charging": False}, device[0]["id"])
    store.touch_device(device[0]["id"])

    assert any(p["kind"] == "battery" for p in insights.problems())


def test_a_charging_phone_at_nine_percent_is_fine(device):
    ingest.ingest_state({"battery": 9, "charging": True}, device[0]["id"])
    store.touch_device(device[0]["id"])

    assert not any(p["kind"] == "battery" for p in insights.problems())


# --- сводки --------------------------------------------------------------
def test_the_day_counts_calls_and_messages(device):
    ingest.ingest_calls([{"direction": "incoming", "status": "missed",
                          "peer_name": "Саша", "peer_number": "+79991234567",
                          "started_at": at(0, 8), "duration": 0}])
    ingest.ingest_calls([{"direction": "outgoing", "status": "answered",
                          "peer_number": "+79995550000", "started_at": at(0, 10),
                          "duration": 600}])
    ingest.ingest_messages([{"direction": "incoming", "peer_name": "Аня",
                             "text": "ок", "ts": at(0, 9)}])

    day = insights.today()["communication"]

    assert day["calls"]["missed"] == 1
    assert day["calls"]["talk_minutes"] == 10.0
    assert day["messages"]["incoming"] == 1


def test_the_digest_leads_with_sleep_and_debts():
    routine("sleep", 7.5)
    health("sleep", 5.0)
    health("steps", 8200)
    missed()

    text = insights.digest()

    assert "Сон 5 ч 00 мин" in text
    assert "8200 шагов" in text
    assert "Саша" in text


def test_a_bridge_without_devices_says_so():
    assert "не подключён" in insights.digest()


def test_a_quiet_day_says_nothing_instead_of_inventing(device):
    store.touch_device(device[0]["id"])

    assert insights.digest() == "Телефон пока ничего не прислал."


def test_a_series_sees_the_trend():
    for day in range(10, 0, -1):
        health("hrv", 30 + (10 - day) * 3, days_ago=day)

    series = insights.series("hrv", days=10)

    assert series["trend"] == "растёт"
    assert series["unit"] == "мс"
    assert len(series["points"]) == 10


def test_sleep_nights_carry_the_heart(device):
    health("sleep", 7.1, days_ago=1, hour=2)
    health("resting_hr", 55, days_ago=1, hour=4)

    [night] = [n for n in insights.sleep_nights(3) if n["hours"]]
    assert night["hours"] == pytest.approx(7.1)
    assert night["resting_hr"] == 55
