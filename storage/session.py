"""Where a `Repository` comes from. Storage owns the session; `api/` depends on
`get_repository` and receives the interface."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session, sessionmaker

from db.base import engine
from db.config import settings
from storage.postgres import PostgresRepository
from storage.repository import Repository, RepositoryUnavailableError

ApiSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

_BOUNDS = text(
    "SELECT set_config('statement_timeout', :statement, true),"
    "       set_config('idle_in_transaction_session_timeout', :idle, true)"
)


@event.listens_for(ApiSessionLocal, "after_begin")
def _bound_the_transaction(session: Session, transaction: object, connection: object) -> None:
    """Per-transaction statement and idle bounds; Postgres only."""
    if connection.dialect.name != "postgresql":  # type: ignore[attr-defined]
        return
    connection.execute(  # type: ignore[attr-defined]
        _BOUNDS,
        {
            "statement": f"{settings.db_statement_timeout_ms}ms",
            "idle": f"{settings.db_idle_in_transaction_timeout_ms}ms",
        },
    )


@contextmanager
def bounded_session() -> Iterator[Session]:
    with ApiSessionLocal() as session:
        try:
            yield session
        except PoolTimeout as exc:
            raise RepositoryUnavailableError(str(exc)) from exc


def get_repository() -> Iterator[Repository]:
    """Request-scoped repository. Wired into FastAPI as a dependency."""
    with bounded_session() as session:
        yield PostgresRepository(session)
