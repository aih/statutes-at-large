"""Migration e4a1c9d27b63 on Postgres: its SQL takes an act's congress from
the approval date exactly as `ingest.identifiers.congress_of_act` does, and
fills `laws.public_private` from the stored XML.

It downgrades and upgrades the database at `MIGRATION_TEST_DATABASE_URL`, an
empty throwaway Postgres (`docker run --rm -p 5499:5432 -e POSTGRES_PASSWORD=x
postgres:16`); skipped when that is unset.
"""

from __future__ import annotations

import datetime
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from ingest.identifiers import congress_of_act
from tests.conftest import REPO_ROOT

URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not URL, reason="MIGRATION_TEST_DATABASE_URL is unset")]

DATES = [
    datetime.date(1789, 3, 4),
    datetime.date(1791, 3, 3),
    datetime.date(1791, 3, 4),
    datetime.date(1843, 3, 3),
    datetime.date(1843, 3, 4),
    datetime.date(1844, 1, 2),
    datetime.date(1890, 8, 15),
    datetime.date(1900, 12, 31),
    datetime.date(1935, 1, 2),
    datetime.date(1935, 1, 3),
    datetime.date(1950, 1, 2),
]


def test_the_migration_matches_congress_of_act(monkeypatch):
    from db.config import settings

    # `db/migrations/env.py` reads the URL from the settings object.
    monkeypatch.setattr(settings, "database_url", URL)
    config = Config(str(REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.downgrade(config, "b7e2c4a91f05")
    engine = create_engine(URL)
    cases = []
    with engine.begin() as connection:
        for day in DATES:
            dated = congress_of_act(None, day)
            for stored in (None, dated, dated - 1, 7):
                identifier = f"/us/act/{day.isoformat()}/ch{9000 + len(cases)}"
                connection.execute(
                    text(
                        "INSERT INTO laws (identifier, kind, congress, enacted, short_titles, stat_volume,"
                        " source_collection, source_package, seq_in_volume, provenance_text,"
                        " provenance_identifiers, xml, content_hash, loaded_at)"
                        " VALUES (:identifier, 'act', :congress, :day, '[]', 26, 'STATUTE', 'STATUTE-26', :seq,"
                        " 'x', 'x', :xml, 'x', now())"
                    ),
                    {
                        "identifier": identifier,
                        "congress": stored,
                        "day": day,
                        "seq": 90000 + len(cases),
                        "xml": f"<pLaw><meta><publicPrivate>{'private' if len(cases) % 2 else 'public'}</publicPrivate></meta></pLaw>",
                    },
                )
                cases.append((identifier, stored, day, "private" if len(cases) % 2 else "public"))
    try:
        command.upgrade(config, "e4a1c9d27b63")
        with engine.connect() as connection:
            rows = {
                identifier: (congress, flag)
                for identifier, congress, flag in connection.execute(
                    text("SELECT identifier, congress, public_private FROM laws WHERE identifier LIKE '/us/act/%/ch9%'")
                ).tuples()
            }
        assert {i: rows[i] for i, *_ in cases} == {i: (congress_of_act(stored, day), flag) for i, stored, day, flag in cases}
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM laws WHERE identifier LIKE '/us/act/%/ch9%'"))
        engine.dispose()
