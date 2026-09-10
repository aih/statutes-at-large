"""`storage.search.SearchSettings` (ADR-0025): the search settings come from
the process environment, then from `.env`, the environment winning. Each test
names its own file; `tests/conftest.py` keeps the working directory's `.env`
out of every other test."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingest import search_sync
from storage import search
from storage.search import SearchNotConfigured, SearchSettings

VARIABLES = ("SEARCH_URL", "SEARCH_USER", "SEARCH_PASSWORD", "SEARCH_VERIFY_CERTS", "DISABLE_SEARCH_SYNC")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    search.reset_search_client()
    yield
    search.reset_search_client()


@pytest.fixture()
def env_file(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / ".env"
    path.write_text(
        "SEARCH_URL=https://from-file:9201\n"
        "SEARCH_PASSWORD=from-file\n"
        "SEARCH_VERIFY_CERTS=false\n"
        "DISABLE_SEARCH_SYNC=1\n"
    )
    monkeypatch.setattr(search, "ENV_FILE", str(path))
    return path


def test_the_defaults_with_no_file_and_no_environment():
    settings = SearchSettings(_env_file=None)
    assert settings.search_url == "https://localhost:9201"
    assert settings.search_user == "admin"
    assert settings.search_password is None
    assert settings.search_verify_certs is True
    assert settings.disable_search_sync is False


def test_the_file_is_read(env_file):
    settings = search.search_settings()
    assert settings.search_url == "https://from-file:9201"
    assert settings.search_password == "from-file"
    assert settings.search_verify_certs is False
    assert search_sync._disabled() is True


def test_the_environment_wins_over_the_file(env_file, monkeypatch):
    monkeypatch.setenv("SEARCH_URL", "https://search-relay:9200")
    monkeypatch.setenv("DISABLE_SEARCH_SYNC", "0")
    settings = search.search_settings()
    assert settings.search_url == "https://search-relay:9200"
    assert settings.search_password == "from-file"
    assert search_sync._disabled() is False


def test_an_empty_password_in_the_environment_wins_over_the_file(env_file, monkeypatch):
    monkeypatch.setenv("SEARCH_PASSWORD", "")
    with pytest.raises(SearchNotConfigured, match="SEARCH_PASSWORD is not set"):
        search.get_search_client()


def test_a_blank_flag_is_its_default(monkeypatch):
    monkeypatch.setenv("SEARCH_VERIFY_CERTS", "")
    monkeypatch.setenv("DISABLE_SEARCH_SYNC", " ")
    settings = SearchSettings(_env_file=None)
    assert settings.search_verify_certs is True
    assert settings.disable_search_sync is False


def test_a_test_run_reads_no_env_file():
    assert search.ENV_FILE is None
