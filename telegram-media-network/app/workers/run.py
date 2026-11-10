from __future__ import annotations

import os
import time

from app.adapters.live_http import PinnedHTTPTransport
from app.core.config import Settings, assert_can_boot
from app.core.db import make_engine, make_session_factory, prepare_database
from app.core.security import Policy
from app.pipeline.llm import LocalLLMClient
from app.publishing.gate import build_telegram_transport, sandbox_chat_id
from app.publishing.leader import LeaderLock
from app.services.bootstrap import bootstrap
from app.services.dispatch import recover_inflight, scheduler_tick
from app.workers.collect import collect_once


def schema_mode() -> str:
    return os.environ.get("TMN_SCHEMA", "create_all")


def apply_schema(engine) -> None:
    mode = schema_mode()
    if mode == "check":
        from app.core.db import assert_schema_head

        assert_schema_head(engine)
        return
    prepare_database(engine, mode)


def collect_cycle(session, settings: Settings, *, transport=None, resolver=None, now=None, force: bool = False):
    """One collector pass. Offline never receives a transport, so it cannot open a socket."""
    if settings.source_mode != "live":
        chosen = None
    elif transport is not None:
        chosen = transport
    else:
        chosen = PinnedHTTPTransport(resolver=resolver)
    client = None
    hosts = {item.strip().lower() for item in settings.llm_allowed_hosts.split(",") if item.strip()}
    if settings.llm_mode == "local" and settings.llm_base_url:
        client = LocalLLMClient(
            settings.llm_base_url,
            model=settings.llm_model,
            timeout=8,
            api_path=settings.llm_api_path,
            allowed_hosts=hosts,
        )
    report = collect_once(
        session,
        settings,
        transport=chosen,
        resolver=resolver,
        now=now,
        force=force,
        render=True,
        llm_mode=settings.llm_mode,
        llm_client=client,
    )
    from app.ops.heartbeat import beat

    beat(session, "collector", "ok" if report.errors == 0 else "error", f"requests={report.requests}")
    return report


def main() -> None:
    settings = Settings()
    assert_can_boot(settings)
    engine = make_engine(settings.database_url)
    apply_schema(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        bootstrap(session, settings)
        session.commit()
    role = os.environ.get("TMN_ROLE", "scheduler")
    once = os.environ.get("TMN_ONCE") == "1"
    if role == "collector":
        while True:
            with factory() as session:
                collect_cycle(session, settings)
            if once:
                return
            time.sleep(60)
    lock = LeaderLock(engine)
    transport = build_telegram_transport(settings)
    try:
        if lock.held or lock.acquire():
            with factory() as session:
                recover_inflight(session)
        while True:
            leader = lock.held or lock.acquire()
            with factory() as session:
                policy = Policy(
                    dry_run=settings.dry_run,
                    publish_enabled=settings.publish_enabled,
                    kill_switch=settings.global_kill_switch,
                    sponsored_enabled=settings.sponsored_enabled,
                )
                from app.core.timeutil import utcnow
                from app.services.moderation import policy_from

                policy = policy_from(session, policy)
                scheduler_tick(
                    session,
                    leader=leader,
                    now=utcnow(),
                    policy=policy,
                    transport=transport,
                    media_dir=settings.media_dir,
                    allowed_chat_id=sandbox_chat_id(settings),
                )
                from app.ops.heartbeat import beat

                beat(session, "scheduler", "ok")
            if once:
                return
            time.sleep(60)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
