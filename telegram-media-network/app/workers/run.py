from __future__ import annotations

import os
import time

from app.core.config import Settings, assert_can_boot
from app.core.db import make_engine, make_session_factory, prepare_database
from app.core.security import Policy
from app.publishing.gate import build_telegram_transport
from app.publishing.leader import LeaderLock
from app.services.bootstrap import bootstrap
from app.services.dispatch import scheduler_tick
from app.workers.collect import collect_once


def main() -> None:
    settings = Settings()
    assert_can_boot(settings)
    engine = make_engine(settings.database_url)
    prepare_database(engine, os.environ.get("TMN_SCHEMA", "create_all"))
    factory = make_session_factory(engine)
    with factory() as session:
        bootstrap(session, settings)
        session.commit()
    role = os.environ.get("TMN_ROLE", "scheduler")
    once = os.environ.get("TMN_ONCE") == "1"
    if role == "collector":
        while True:
            with factory() as session:
                collect_once(session, settings)
            if once:
                return
            time.sleep(60)
    lock = LeaderLock(engine)
    transport = build_telegram_transport(settings)
    try:
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
                )
            if once:
                return
            time.sleep(60)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
