"""Single migration job. API and workers only check that this revision is already current."""

from __future__ import annotations

from app.core.config import Settings, assert_can_boot
from app.core.db import make_engine, prepare_database


def main() -> None:
    settings = Settings()
    assert_can_boot(settings)
    engine = make_engine(settings.database_url)
    prepare_database(engine, "migrate")


if __name__ == "__main__":
    main()
