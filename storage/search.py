"""The OpenSearch connection and the index name both surfaces agree on.

The alias lives here rather than in `ingest.search_sync` so `api/` can name an
index without importing the ingest layer: the dependency runs
ingest → storage ← api (architecture rule 1).

The cluster is the US Code site's, shared (the plan's section E1). On the box
this site's container joins that compose project's network and reads
`SEARCH_URL=https://opensearch:9200`; the dev stack publishes its own cluster
on host port 9201. `SEARCH_PASSWORD` comes from the environment or `.env` and
is never written into source.
"""

from __future__ import annotations

import os
import threading

from opensearchpy import OpenSearch

UNITS_ALIAS = "statutes_units"
"""The alias every read goes through. It points at a physical index named for
the mapping fingerprint (`ingest.search_sync.index_name_for`)."""

SEARCH_URL = os.environ.get("SEARCH_URL", "https://localhost:9201")
"""9201, because 9200 on this machine is the US Code site's dev cluster."""

SEARCH_USER = os.environ.get("SEARCH_USER", "admin")


class SearchNotConfigured(RuntimeError):
    """No cluster is configured: `SEARCH_PASSWORD` is unset.

    Raised rather than falling back to a default password, so a deployment that
    sets neither `SEARCH_URL` nor `SEARCH_PASSWORD` fails instead of trying
    localhost with a published credential.
    """


def _verify_certs() -> bool:
    """Verify TLS unless `SEARCH_VERIFY_CERTS=false`.

    The dev and box clusters present the self-signed certificate the OpenSearch
    image generates at first boot, so both compose files set this to false and
    say why. Anything reaching a cluster over the public internet must not.
    """
    return os.environ.get("SEARCH_VERIFY_CERTS", "true").strip().lower() != "false"


_client: OpenSearch | None = None
_client_lock = threading.Lock()


def get_search_client() -> OpenSearch:
    """The process's OpenSearch client, built once.

    A singleton because it holds a connection pool: a client per request is a
    pool and a TLS handshake per search. Double-checked under a lock, since
    FastAPI's sync handlers run in a threadpool and two searches can arrive
    here at once.

    Raises `SearchNotConfigured` when `SEARCH_PASSWORD` is unset.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def _build_client() -> OpenSearch:
    password = os.environ.get("SEARCH_PASSWORD")
    if not password:
        raise SearchNotConfigured(
            "SEARCH_PASSWORD is not set. Set it (and SEARCH_URL) to point at a "
            "cluster, or set DISABLE_SEARCH_SYNC=1 to run without search."
        )
    verify = _verify_certs()
    return OpenSearch(
        hosts=[SEARCH_URL],
        http_compress=True,
        http_auth=(SEARCH_USER, password),
        use_ssl=True,
        verify_certs=verify,
        # Hostname assertion is part of verification, not a separate knob.
        ssl_assert_hostname=verify,
        ssl_show_warn=verify,
    )


def reset_search_client() -> None:
    """Drop the cached client. For tests that change the environment."""
    global _client
    with _client_lock:
        _client = None
