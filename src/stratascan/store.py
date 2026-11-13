"""The database connection: the app's schema `stratascan` in the shared Postgres (omarchy-db), or what OMARCHY_DB_URL /
STRATASCAN_DATABASE_URL name (a SQLite path for a machine without the shared server). Only the long-running server migrates (`migrate`, at
start), never a CLI command, so a stray process cannot move the schema under the running service (omarchy-db's rule)."""

import threading
from collections.abc import Generator
from contextlib import contextmanager

from omarchy_db import Project, connect  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]
from sqlalchemy import Engine
from sqlalchemy.orm import Session

_lock = threading.Lock()
_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            _engine = connect("stratascan")
        return _engine


def migrate() -> None:
    """Bring the schema to the code's head (a no-op when it is there): the server calls this once at start."""
    Project.load(__file__).upgrade(engine())  # pyright: ignore[reportUnknownMemberType]


def reset() -> None:
    """Forget the engine, so the next use connects again (tests point each test at a fresh database)."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None


@contextmanager
def session() -> Generator[Session]:
    """A session that commits on success and rolls back on an exception. Objects stay readable after it closes (expire_on_commit off), so a
    stage can hand rows to worker threads without a query each."""
    s = Session(engine(), expire_on_commit=False)
    try:
        yield s
        s.commit()
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()
