"""Фоновый обработчик.

В Phase 1 он делает немного: разбирает очередь доменных событий, чистит истёкшие
сессии и переиндексирует поиск. Дальше сюда переедут напоминания о сроках
документов, пересчёт электрической модели и проверки резервирования питания.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from arq.connections import RedisSettings
from sqlalchemy import select, update

from itms.core.config import settings
from itms.core.context import ActorKind, RequestContext, use_context
from itms.core.db import dispose_engine, session_scope
from itms.domain.audit_rules import configure_audit
from itms.domain.search import ci_document, document_document
from itms.models.cmdb import Ci, Location
from itms.models.documents import Document
from itms.models.system import OutboxEvent
from itms.services import auth_service, document_service, search_service

logger = logging.getLogger("itms.worker")

BATCH_SIZE = 200


async def process_outbox(ctx: dict[str, Any]) -> int:
    """Разбирает события, записанные в одной транзакции с данными."""
    processed = 0
    async with session_scope() as session:
        events = (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for event in events:
            event.processed_at = datetime.now(UTC)
            event.attempts += 1
            processed += 1
    if processed:
        logger.info("Обработано событий: %s", processed)
    return processed


async def reindex_search(ctx: dict[str, Any]) -> int:
    """Полная переиндексация: нужна после импорта и при смене правил построения индекса."""
    count = 0
    async with session_scope() as session:
        paths = dict(
            (await session.execute(select(Location.id, Location.path))).all()
        )
        for ci in (
            await session.execute(select(Ci).where(Ci.deleted_at.is_(None),
                                                   Ci.archived_at.is_(None)))
        ).scalars():
            await search_service.index_entity(
                session, ci.id, ci_document(ci, paths.get(ci.location_id))
            )
            count += 1
        for doc in (
            await session.execute(select(Document).where(Document.deleted_at.is_(None)))
        ).scalars():
            version = await document_service.current_content(session, doc.id)
            await search_service.index_entity(
                session, doc.id, document_document(doc, version.content if version else None)
            )
            count += 1
    logger.info("Переиндексировано записей: %s", count)
    return count


async def cleanup_sessions(ctx: dict[str, Any]) -> int:
    async with session_scope() as session:
        return await auth_service.cleanup_sessions(session)


async def flag_documents_for_review(ctx: dict[str, Any]) -> int:
    """Отмечает документы, у которых истёк срок пересмотра."""
    async with session_scope() as session:
        with use_context(
            RequestContext(actor_kind=ActorKind.JOB, actor_label="Проверка документов",
                           source="job")
        ):
            overdue = await document_service.review_overdue(session, limit=500)
            if overdue:
                await session.execute(
                    update(Document)
                    .where(Document.id.in_([doc.id for doc in overdue]))
                    .values(status="IN_REVIEW")
                )
            return len(overdue)


async def startup(ctx: dict[str, Any]) -> None:
    configure_audit()
    logger.info("Обработчик запущен, база: %s", settings.database_url.split("@")[-1])


async def shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions = [process_outbox, reindex_search, cleanup_sessions, flag_documents_for_review]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    cron_jobs: list[Any] = []


def build_cron_jobs() -> list[Any]:
    from arq import cron

    return [
        cron(process_outbox, second={0, 15, 30, 45}, run_at_startup=True),
        cron(cleanup_sessions, hour={3}, minute={10}),
        cron(flag_documents_for_review, hour={6}, minute={0}),
    ]


WorkerSettings.cron_jobs = build_cron_jobs()
