"""Полная выгрузка Здоровья: все метрики, кольца, тренировки, без двойного счёта."""
import os
import zipfile

from conftest import at

from phone import ingest, insights, store
from phone.apple import health_export

XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="ru_RU">
 <ExportDate value="2026-09-21 12:00:00 +0300"/>
 <Me HKCharacteristicTypeIdentifierDateOfBirth="1990-01-01"
     HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"
     HKCharacteristicTypeIdentifierBloodType="HKBloodTypeNotSet"
     HKCharacteristicTypeIdentifierFitzpatrickSkinType="HKFitzpatrickSkinTypeNotSet"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Кирилл’s Apple Watch"
         unit="count" value="1234"
         startDate="2026-09-21 08:00:00 +0300" endDate="2026-09-21 08:10:00 +0300"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone"
         unit="count" value="800"
         startDate="2026-09-21 08:00:00 +0300" endDate="2026-09-21 08:10:00 +0300"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch"
         value="HKCategoryValueSleepAnalysisAsleepDeep"
         startDate="2026-09-20 23:40:00 +0300" endDate="2026-09-21 00:40:00 +0300"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch"
         value="HKCategoryValueSleepAnalysisAsleepREM"
         startDate="2026-09-21 00:40:00 +0300" endDate="2026-09-21 01:40:00 +0300"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch"
         unit="count/min" value="62"
         startDate="2026-09-21 08:00:00 +0300" endDate="2026-09-21 08:00:00 +0300"/>
 <Record type="HKQuantityTypeIdentifierDietaryWater" sourceName="iPhone"
         unit="mL" value="500"
         startDate="2026-09-21 09:00:00 +0300" endDate="2026-09-21 09:00:00 +0300"/>
 <Record type="HKQuantityTypeIdentifierVO2Max" sourceName="Apple Watch"
         unit="mL/kg·min" value="44.2"
         startDate="2026-09-21 07:30:00 +0300" endDate="2026-09-21 07:30:00 +0300"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30"
          durationUnit="min" totalDistance="5.2" totalDistanceUnit="km"
          totalEnergyBurned="310" totalEnergyBurnedUnit="kcal"
          sourceName="Apple Watch"
          startDate="2026-09-21 07:00:00 +0300" endDate="2026-09-21 07:30:00 +0300">
  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate"
                     average="148" minimum="120" maximum="172" unit="count/min"
                     startDate="2026-09-21 07:00:00 +0300"
                     endDate="2026-09-21 07:30:00 +0300"/>
 </Workout>
 <ActivitySummary dateComponents="2026-09-21" activeEnergyBurned="410"
                  activeEnergyBurnedGoal="500" activeEnergyBurnedUnit="kcal"
                  appleExerciseTime="30" appleExerciseTimeGoal="30"
                  appleStandHours="10" appleStandHoursGoal="12"/>
</HealthData>
"""


def _write(path, name="export.xml"):
    xml_path = os.path.join(path, name)
    with open(xml_path, "w", encoding="utf-8") as fh:
        fh.write(XML)
    return xml_path


def test_the_export_keeps_every_metric(tmp_path, device):
    report = health_export.import_export(_write(tmp_path), device[0]["id"])

    assert report["read"] >= 8
    assert report["health"]["new"] >= 8
    names = {row["metric"] for row in store.samples(limit=None)}
    assert {"steps", "sleep", "sleep_deep", "sleep_rem", "heart_rate",
            "water", "vo2max", "ring_move", "ring_exercise", "ring_stand"} <= names


def test_watch_and_phone_steps_are_not_added_together(tmp_path):
    """Один шаг записали двое — день не должен стать вдвое бодрее."""
    health_export.import_export(_write(tmp_path))
    # 21 сентября 2026, не «сегодня»: иначе тест зависит от календаря.
    assert insights.metric_today("steps", "2026-09-21") == 1234


def test_sleep_stages_also_count_as_sleep(tmp_path):
    health_export.import_export(_write(tmp_path))
    assert insights.metric_today("sleep", "2026-09-21") == 2
    assert insights.metric_today("sleep_deep", "2026-09-21") == 1
    assert insights.metric_today("sleep_rem", "2026-09-21") == 1


def test_water_arrives_in_litres(tmp_path):
    health_export.import_export(_write(tmp_path))
    [row] = [s for s in store.samples(metric="water", limit=None)]
    assert row["value"] == 0.5
    assert row["unit"] == "л"


def test_a_workout_keeps_the_watch_summary(tmp_path):
    health_export.import_export(_write(tmp_path))
    [workout] = store.workouts(since=0)
    assert workout["kind"] == "Running"
    assert workout["duration"] == 30
    assert workout["energy"] == 310
    assert workout["avg_hr"] == 148
    assert workout["max_hr"] == 172


def test_activity_rings_are_not_mixed_with_samples(tmp_path):
    health_export.import_export(_write(tmp_path))
    assert insights.metric_today("ring_move", "2026-09-21") == 410
    assert insights.metric_today("ring_stand", "2026-09-21") == 10


def test_the_same_export_twice_does_not_double(tmp_path, device):
    path = _write(tmp_path)
    first = health_export.import_export(path, device[0]["id"])
    again = health_export.import_export(path, device[0]["id"])
    assert first["health"]["new"] > 0
    assert again["health"]["new"] == 0
    assert again["health"]["duplicates"] == first["health"]["new"]


def test_a_zip_is_read_without_unpacking(tmp_path, device):
    folder = tmp_path / "apple_health_export"
    folder.mkdir()
    _write(folder)
    archive = tmp_path / "экспорт.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(folder / "export.xml", "apple_health_export/экспорт.xml")
    report = health_export.import_export(str(archive), device[0]["id"])
    assert report["health"]["new"] > 0


def test_cli_import_health_writes_a_cursor(tmp_path, device):
    from phone.__main__ import main
    path = _write(tmp_path)
    main(["import-health", path, "--device", device[0]["name"]])
    assert store.cursors().get("health_export")


def test_today_lists_more_than_steps_and_sleep(tmp_path):
    health_export.import_export(_write(tmp_path))
    # Подменяем «сегодня», чтобы сводка смотрела на дату выгрузки.
    day = insights.health_today("2026-09-21")
    assert "vo2max" in day and "water" in day and "heart_rate" in day


def test_watch_wins_only_the_overlapping_minute():
    ingest.ingest_health([
        {"metric": "steps", "value": 1000, "start": at(0, 8), "source": "Apple Watch"},
        {"metric": "steps", "value": 800, "start": at(0, 8), "source": "iPhone"},
        {"metric": "steps", "value": 500, "start": at(0, 9), "source": "iPhone"},
    ])
    # В 8:00 часы победили телефон, в 9:00 телефона больше не с кем спорить.
    assert insights.metric_today("steps") == 1500
