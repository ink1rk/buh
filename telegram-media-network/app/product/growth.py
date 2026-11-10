"""Honest metrics. Unknown stays unknown. Experiments start NOT_STARTED."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models import ExperimentPlan, MetricDefinition, MetricObservation
from app.core.timeutil import ensure_utc
from app.product.insights import funnel

DEFINITIONS = (
    ("ingested", "Принятые исходные записи", "count", "source items linked to channel clusters", "derived"),
    ("unique", "Уникальные сюжеты", "count", "stories assigned to the channel", "derived"),
    ("shortlisted", "Короткий список", "count", "stories with score_total >= 60", "derived"),
    ("drafted", "Черновики", "count", "posts that are not REJECTED", "derived"),
    ("published", "Опубликовано", "count", "posts with review_status PUBLISHED", "derived"),
    ("views", "Просмотры", "count", "unknown until a live measurement exists", "unknown"),
    ("members", "Подписчики", "count", "unknown until a live measurement exists", "unknown"),
    ("revenue_actual", "Фактическая выручка", "currency", "FinanceEvent actual with a non-null amount", "measured_manual"),
)

EXPERIMENTS = (
    ("Инструмент дня", "Регулярная рубрика инструментов увеличит возвращаемость", "unique"),
    ("Недельный дайджест", "Дайджест в понедельник соберёт просмотры", "views"),
    ("Разные часы", "Слоты вне тихих часов изменят охват", "views"),
    ("Редакционные подборки", "Сравнение форматов без публикации", "drafted"),
)


def ensure_metrics(session: Session) -> int:
    pending = {obj.id: obj for obj in session.new if isinstance(obj, MetricDefinition)}
    made = 0
    for metric_id, title, unit, formula, source_type in DEFINITIONS:
        row = pending.get(metric_id) or session.get(MetricDefinition, metric_id)
        if row is None:
            row = MetricDefinition(id=metric_id)
            session.add(row)
            pending[metric_id] = row
            made += 1
        row.title = title
        row.unit = unit
        row.formula = formula
        row.source_type = source_type
    session.flush()
    return made


def seed_experiments(session: Session) -> int:
    if session.query(ExperimentPlan).count():
        return 0
    made = 0
    for title, hypothesis, metric in EXPERIMENTS:
        session.add(
            ExperimentPlan(
                title=title,
                hypothesis=hypothesis,
                expected_metric=metric,
                status="NOT_STARTED",
                actual="н/д",
                decision="",
                demo=True,
            )
        )
        made += 1
    return made


def snapshot_derived(session: Session, now: datetime, *, demo: bool = True) -> int:
    ensure_metrics(session)
    moment = ensure_utc(now)
    report = funnel(session, now=moment)
    mapping = {
        "ingested": report["stages"]["ingested"],
        "unique": report["stages"]["unique"],
        "shortlisted": report["stages"]["shortlisted"],
        "drafted": report["stages"]["drafted"],
        "published": report["stages"]["published"],
        "views": None,
        "members": None,
        "revenue_actual": None,
    }
    written = 0
    for metric_id, value in mapping.items():
        source_type = "demo" if demo and value is not None else "unknown" if value is None else "derived"
        session.add(
            MetricObservation(
                metric_id=metric_id,
                channel_id="",
                period_at=moment,
                value=value,
                source_type=source_type,
                collected_at=moment,
                evidence_ref="funnel()" if value is not None else "",
                demo=demo,
            )
        )
        written += 1
    session.flush()
    return written


def board(session: Session) -> dict:
    definitions = [
        {
            "id": row.id,
            "title": row.title,
            "unit": row.unit,
            "formula": row.formula,
            "source_type": row.source_type,
        }
        for row in session.query(MetricDefinition).order_by(MetricDefinition.id)
    ]
    latest: dict[str, dict] = {}
    for row in session.query(MetricObservation).order_by(MetricObservation.id.desc()):
        key = f"{row.metric_id}:{row.channel_id}"
        if key in latest:
            continue
        latest[key] = {
            "metric_id": row.metric_id,
            "channel_id": row.channel_id or "network",
            "value": row.value,
            "display": "н/д" if row.value is None else row.value,
            "source_type": row.source_type,
            "demo": row.demo,
            "collected_at": row.collected_at.isoformat() if row.collected_at else "",
        }
    experiments = [
        {
            "title": row.title,
            "hypothesis": row.hypothesis,
            "status": row.status,
            "actual": row.actual,
            "decision": row.decision or "нет решения",
            "demo": row.demo,
        }
        for row in session.query(ExperimentPlan).order_by(ExperimentPlan.id)
    ]
    return {
        "data_mode": "mixed",
        "definitions": definitions,
        "observations": list(latest.values()),
        "experiments": experiments,
        "zero_vs_unknown": "0 — измеренный ноль; н/д — измерения нет; DEMO — учебная строка",
    }
