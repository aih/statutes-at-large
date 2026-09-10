"""The OpenSearch connection, its settings, and the index name both surfaces
agree on.

The alias lives here rather than in `ingest.search_sync` so `api/` can name an
index without importing the ingest layer: the dependency runs
ingest → storage ← api (architecture rule 1).

The cluster is the US Code site's, shared (ADR-0023, ADR-0024). On the box the
API reaches it through `search-relay` at `SEARCH_URL=https://search-relay:9200`;
the dev stack publishes its own cluster on host port 9201. `SearchSettings`
reads `SEARCH_URL`, `SEARCH_USER`, `SEARCH_PASSWORD`, `SEARCH_VERIFY_CERTS` and
`DISABLE_SEARCH_SYNC` from the process environment and then from `.env` in the
working directory; the environment wins (ADR-0025). `SEARCH_PASSWORD` is never
written into source.
"""

from __future__ import annotations

import threading

from opensearchpy import OpenSearch
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

UNITS_ALIAS = "statutes_units"
"""The alias every read goes through. It points at a physical index named for
the mapping fingerprint (`ingest.search_sync.index_name_for`)."""

ENV_FILE: str | None = ".env"
"""The file `search_settings()` reads after the environment. `tests/conftest.py`
sets it to None, so a test run reads the process environment only."""


class SearchSettings(BaseSettings):
    search_url: str = "https://localhost:9201"
    """9201, because 9200 on this machine is the US Code site's dev cluster."""

    search_user: str = "admin"
    search_password: str | None = None

    search_verify_certs: bool = True
    """Verify TLS unless `SEARCH_VERIFY_CERTS=false`. The dev and box clusters
    present the self-signed certificate the OpenSearch image generates at first
    boot, so both compose files set it to false and say why. Anything reaching
    a cluster over the public internet must not."""

    disable_search_sync: bool = False
    """`DISABLE_SEARCH_SYNC=1`: `ingest` indexes nothing and reaches no cluster."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("search_verify_certs", "disable_search_sync", mode="before")
    @classmethod
    def _blank_is_the_default(cls, value: object, info: ValidationInfo) -> object:
        """`SEARCH_VERIFY_CERTS=` with no value is the default, not an error."""
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].default
        return value


def search_settings() -> SearchSettings:
    """The settings as they stand now, read on each call."""
    return SearchSettings(_env_file=ENV_FILE)


class SearchNotConfigured(RuntimeError):
    """No cluster is configured: `SEARCH_PASSWORD` is unset or empty.

    Raised rather than falling back to a default password, so a deployment that
    sets neither `SEARCH_URL` nor `SEARCH_PASSWORD` fails instead of trying
    localhost with a published credential. An empty `SEARCH_PASSWORD` in the
    environment wins over a password in `.env`.
    """


_client: OpenSearch | None = None
_client_lock = threading.Lock()


def get_search_client() -> OpenSearch:
    """The process's OpenSearch client, built once.

    A singleton because it holds a connection pool: a client per request is a
    pool and a TLS handshake per search. Double-checked under a lock, since
    FastAPI's sync handlers run in a threadpool and two searches can arrive
    here at once.

    Raises `SearchNotConfigured` when `SEARCH_PASSWORD` is unset or empty.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def _build_client() -> OpenSearch:
    settings = search_settings()
    if not settings.search_password:
        raise SearchNotConfigured(
            "SEARCH_PASSWORD is not set. Set it (and SEARCH_URL) to point at a "
            "cluster, or set DISABLE_SEARCH_SYNC=1 to run without search."
        )
    verify = settings.search_verify_certs
    return OpenSearch(
        hosts=[settings.search_url],
        http_compress=True,
        http_auth=(settings.search_user, settings.search_password),
        use_ssl=True,
        verify_certs=verify,
        # Hostname assertion is part of verification, not a separate knob.
        ssl_assert_hostname=verify,
        ssl_show_warn=verify,
    )


def reset_search_client() -> None:
    """Drop the cached client. For tests that change the settings."""
    global _client
    with _client_lock:
        _client = None
