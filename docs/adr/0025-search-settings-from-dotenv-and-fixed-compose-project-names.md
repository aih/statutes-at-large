# ADR-0025: Search settings from `.env`, and fixed compose project names

Date: 2026-09-10. Status: accepted. Amends ADR-0023 (decision 9) and records
the compose project names ADR-0017 and ADR-0024 assumed.

## Context

`storage/search.py` read `SEARCH_URL`, `SEARCH_USER`, `SEARCH_PASSWORD` and
`SEARCH_VERIFY_CERTS` with `os.environ.get`, and `ingest/` read
`DISABLE_SEARCH_SYNC` the same way. `db/config.py: Settings` and
`api/comps.py: _Origins` read `.env` through pydantic-settings, so under a plain
`make dev` the database and the origins were configured and search was not:
`GET /api/v1/search` answered 503 and seven of the 74 browser tests failed
until the shell exported the password.

`docker-compose.yml` had no `name:`. Compose named the project after the
directory, so a worktree's `make dev-up` created a second project whose `db`
failed to bind host port 5434 (`Bind for 0.0.0.0:5434 failed: port is already
allocated`) and left an empty `pgdata` volume behind. The main checkout's
containers carry `statutes-linkedlegislation`, the directory's earlier name.
On the box the checkout is `~/statutes-at-large`, run without `-p`, and every
container there is `statutes-at-large-*`.

## Decisions

1. **One pydantic-settings class holds the search settings.**
   `storage.search.SearchSettings`, `env_file=".env"`, `extra="ignore"`:
   `search_url` (default `https://localhost:9201`), `search_user` (`admin`),
   `search_password` (`None`), `search_verify_certs` (`True`),
   `disable_search_sync` (`False`). The process environment wins over the
   file, so the compose files' `environment:` blocks and the box are read as
   before. `search_settings()` builds the class on each call: the client is
   built once per process and `reset_search_client()` re-reads the settings.
   A blank `SEARCH_VERIFY_CERTS` or `DISABLE_SEARCH_SYNC` is the default. The
   two booleans parse as pydantic booleans (`false`, `0`, `no`, `off`); an
   unparseable value is a validation error, where before anything but
   `false` verified.

2. **`DISABLE_SEARCH_SYNC` moves into the same class.** `_disabled()` in
   `ingest/search_sync.py` and the check in `ingest/reindex_search.py` read
   `search_settings().disable_search_sync`, so the line `.env.example` offers
   takes effect from the file. ADR-0023 decision 9 is unchanged in what the
   flag does.

3. **A test run reads no `.env` for search.** `tests/conftest.py` sets
   `storage.search.ENV_FILE = None`; the settings then come from the process
   environment alone. The two tests that need "no password"
   (`tests/test_search_route.py`, `tests/test_reindex_search_cli.py`) set
   `SEARCH_PASSWORD` to an empty string, which wins over a shell export as
   well; `SearchNotConfigured` treats an empty password as unset.
   `tests/test_search_settings.py` covers the file, the precedence, and the
   empty password against a file that sets one.

4. **`docker-compose.yml` is project `statutes-linkedlegislation`.** Every
   checkout and worktree addresses the same `db`, `opensearch`, volumes and
   host ports. `make dev-up` from a worktree reports the running `db` and
   creates nothing. `make up` from a worktree recreates the `api` container
   with that checkout's directory mounted at `/app`, since the project is one.

5. **`docker-compose.prod.yml` is project `statutes-at-large`**, the name the
   box already runs under, so the deploy that adds it recreates nothing. A
   checkout in another directory then addresses the same containers instead
   of starting a second project whose proxy would also answer as
   `statutes-proxy` on `edge`. The name prefixes the relay's container name
   on `uscode-redesign_default` (`statutes-at-large-search-relay-1`,
   ADR-0024 decision 2). A project named `uscode-redesign` would put every
   service on that network as its default.

6. **`docker-compose.edge.yml` carries no name.** It is layered over
   `docker-compose.yml` and takes that project; a name in the override would
   move the dev proxy to another project. `deploy/edge/docker-compose.yml`
   stays project `edge` through `-p edge` in `deploy/edge/up.sh`.

`tests/test_compose_networks.py` asserts decisions 4 to 6.

## Consequences

- `make dev` and `make test-e2e` run from any checkout with `.env` copied in
  and nothing exported.
- Two checkouts running `make dev-api` at once still collide on port 8001;
  the database is shared, the servers are not.
- The worktree containers and volumes created before this change
  (`statutes-wt-*-db-1`, `statutes-wt-*_pgdata`) are not removed by it.
