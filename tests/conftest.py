"""Shared fixtures: a SQLite database loaded from the committed slices, a
repository over it, and an API client whose repository dependency is that one.

The slices are verbatim cuts of the real source files (`make fixtures`), so
every test runs against GovInfo's own markup and no network.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("GOVINFO_API_KEY", "")

import pytest
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base, make_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
COMPS_FIXTURES = FIXTURES / "comps"
STATUTE_SLICES = [
    FIXTURES / "statute-26-slice.xml",
    FIXTURES / "statute-64-slice.xml",
    FIXTURES / "statute-68-slice.xml",
    FIXTURES / "statute-72-slice.xml",
    FIXTURES / "statute-116-slice.xml",
    FIXTURES / "statute-124-slice.xml",
    FIXTURES / "statute-137-slice.xml",
]
COMP_SLICES = [
    COMPS_FIXTURES / "COMPS-1630-slice.xml",
    COMPS_FIXTURES / "COMPS-973-slice.xml",
    COMPS_FIXTURES / "COMPS-3055.xml",
    COMPS_FIXTURES / "COMPS-8755-slice.xml",
]
VOLUME_DIR = REPO_ROOT / "data" / "statute" / "xmls"
CITATIONS_SLICE = FIXTURES / "uscode-current-slice.parquet"
"""57 US Code sections cut from the `dreamproit/uscode` `current` shards
(`scripts/extract_citations_fixture.py`): the ones whose source credits cite
the laws in the volume slices, plus 16 U.S.C. §§ 1 and 45f."""


def require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"not present: {path}")
    return path


@pytest.fixture(scope="session")
def engine():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(scope="session")
def loaded(session_factory) -> dict:
    """Load every slice once per session; returns the per-file load reports."""
    from ingest.load import load_volume

    reports = {}
    with session_factory() as session:
        for path in STATUTE_SLICES:
            reports[path.name] = load_volume(session, path, record_check=True)
    try:
        from ingest.comps import load_comp_file
    except ImportError:
        load_comp_file = None
    if load_comp_file is not None:
        with session_factory() as session:
            for path in COMP_SLICES:
                summary = COMPS_FIXTURES / (path.name.replace("-slice", "").replace(".xml", ".summary.json"))
                reports[path.name] = load_comp_file(session, path, summary_path=summary if summary.exists() else None)
    from ingest.citations import load_citations

    with session_factory() as session:
        reports[CITATIONS_SLICE.name] = load_citations(session, [CITATIONS_SLICE], revision="fixture")
    return reports


@pytest.fixture()
def db(loaded, session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture()
def repo(db):
    from storage.postgres import PostgresRepository

    return PostgresRepository(db)


@pytest.fixture(scope="session")
def client(loaded, session_factory):
    from fastapi.testclient import TestClient

    from main import app
    from storage import get_repository
    from storage.postgres import PostgresRepository

    def override():
        with session_factory() as session:
            yield PostgresRepository(session)

    app.dependency_overrides[get_repository] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_repository, None)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from params import LIMITERS

    for limiter in LIMITERS.values():
        limiter.reset()
    yield
