"""`python -m ingest reindex-search`: which flag calls which
`ingest.search_sync` function. The sync functions themselves are
`tests/test_search_mapping.py`'s; this is only the CLI's routing and its two
special-cased exits (`DISABLE_SEARCH_SYNC=1`, a missing `SEARCH_PASSWORD`)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from db.base import Base, make_engine
from ingest import reindex_search, search_sync
from storage import search as search_module


def _factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture()
def sessions(monkeypatch):
    import db.base

    made = _factory()
    monkeypatch.setattr(db.base, "SessionLocal", made)
    return made


@pytest.fixture()
def fake_client(monkeypatch):
    client = object()
    monkeypatch.setattr(reindex_search, "get_search_client", lambda: client)
    return client


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch):
    """`get_search_client` caches a singleton; a real one must not be built."""
    search_module.reset_search_client()
    yield
    search_module.reset_search_client()


def _calls(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        search_sync, "rebuild",
        lambda session, client, *, recreate=False: calls.append(("rebuild", recreate))
        or {"alias": "statutes_units", "index": "statutes_units_x", "fingerprint": "x",
            "documents": {"enacted": 3, "compiled": 1}, "recreated": recreate},
    )
    monkeypatch.setattr(
        search_sync, "resync_since",
        lambda session, client, since: calls.append(("resync_since", since))
        or {"alias": "statutes_units", "since": since.isoformat(),
            "documents": {"enacted": 2, "compiled": 0}},
    )
    return calls


def test_the_default_is_a_plain_rebuild(sessions, fake_client, monkeypatch, capsys):
    from ingest.__main__ import main

    calls = _calls(monkeypatch)
    assert main(["reindex-search"]) == 0
    assert calls == [("rebuild", False)]
    assert "3 enacted, 1 compiled" in capsys.readouterr().out


def test_recreate_rebuilds_with_recreate_true(sessions, fake_client, monkeypatch):
    from ingest.__main__ import main

    calls = _calls(monkeypatch)
    assert main(["reindex-search", "--recreate"]) == 0
    assert calls == [("rebuild", True)]


def test_since_calls_resync_since(sessions, fake_client, monkeypatch, capsys):
    from ingest.__main__ import main

    calls = _calls(monkeypatch)
    assert main(["reindex-search", "--since", "2026-01-01"]) == 0
    assert calls == [("resync_since", datetime.date(2026, 1, 1))]
    assert "resynced since 2026-01-01" in capsys.readouterr().out


def test_if_changed_rebuilds_only_when_stale(sessions, fake_client, monkeypatch, capsys):
    from ingest.__main__ import main

    calls = _calls(monkeypatch)
    monkeypatch.setattr(search_sync, "alias_is_current", lambda client: False)
    assert main(["reindex-search", "--if-changed"]) == 0
    assert calls == [("rebuild", False)]


def test_if_changed_does_nothing_when_current(sessions, fake_client, monkeypatch, capsys):
    from ingest.__main__ import main

    calls = _calls(monkeypatch)
    monkeypatch.setattr(search_sync, "alias_is_current", lambda client: True)
    assert main(["reindex-search", "--if-changed"]) == 0
    assert calls == []
    assert "nothing rebuilt" in capsys.readouterr().out


def test_the_modes_are_mutually_exclusive():
    from ingest.__main__ import main

    with pytest.raises(SystemExit):
        main(["reindex-search", "--if-changed", "--recreate"])


def test_disabled_skips_with_no_client(monkeypatch, capsys):
    from ingest.__main__ import main

    monkeypatch.setenv("DISABLE_SEARCH_SYNC", "1")

    def _fail():
        raise AssertionError("get_search_client called while DISABLE_SEARCH_SYNC=1")

    monkeypatch.setattr(reindex_search, "get_search_client", _fail)
    assert main(["reindex-search"]) == 0
    assert "no-op" in capsys.readouterr().out


def test_a_missing_search_password_is_a_one_line_error(monkeypatch, capsys):
    from ingest.__main__ import main

    monkeypatch.delenv("SEARCH_PASSWORD", raising=False)
    assert main(["reindex-search"]) == 1
    assert "SEARCH_PASSWORD" in capsys.readouterr().err
