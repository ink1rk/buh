from __future__ import annotations

import os
import time

from app.core.config import Settings, assert_can_boot
from app.core.db import init_schema, make_engine, make_session_factory
from app.core.security import Policy
from app.publishing.leader import LeaderLock
from app.services.bootstrap import bootstrap
from app.services.dispatch import scheduler_tick


def main() -> None:
    settings = Settings()
    assert_can_boot(settings)
    engine = make_engine(settings.database_url)
    init_schema(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        bootstrap(session, settings)
        session.commit()
    role = os.environ.get("TMN_ROLE", "scheduler")
    once = os.environ.get("TMN_ONCE") == "1"
    if role == "collector":
        # Offline mode does not call source APIs. Live polling stays disabled
        # until an operator turns SOURCE_MODE off and supplies read-only tokens.
        if once:
            return
        while True:
            time.sleep(3600)
    lock = LeaderLock(engine)
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
                scheduler_tick(session, leader=leader, now=utcnow(), policy=policy, transport=None)
            if once:
                return
            time.sleep(60)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
