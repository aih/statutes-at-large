# The dev-environment session: search settings from `.env`, one compose project per repository

Date: 2026-09-10. The prompt for a separate session in its own worktree.
Two things the compilations session met (BUILDLOG 2026-09-09, "the
compiled side of ADR-0019").

## Found

1. `storage/search.py` reads `SEARCH_URL`, `SEARCH_USER`, `SEARCH_PASSWORD`
   and `SEARCH_VERIFY_CERTS` with `os.environ.get`, module constants at
   import. Its docstring says `SEARCH_PASSWORD` "comes from the environment
   or `.env`"; only the environment counts. `db/config.py: Settings` and
   `api/comps.py: _Origins` read `.env` through pydantic-settings
   (`env_file=".env"`), so `DATABASE_URL` and the origins work under a plain
   `make dev` and the search route does not: `GET /api/v1/search` answers
   503 `search is unavailable; try again shortly`, the log says `search is
   not configured: SEARCH_PASSWORD is unset`, and seven of the 74 browser
   tests fail (`tests/e2e/search.spec.ts`). The session ran the servers with
   `set -a; . ./.env; set +a; make -j2 dev-api dev-web`. `DISABLE_SEARCH_SYNC`
   is read the same way in `ingest/search_sync.py` and
   `ingest/reindex_search.py`.

2. `docker-compose.yml` has no `name:`. The compose project is named after
   the directory, so the main checkout's containers are
   `statutes-linkedlegislation-*` (the directory's earlier name) and a
   worktree's `make dev` (`dev-up` is `docker compose up -d db`) creates a
   second project, `statutes-wt-compiled`, whose `db` fails to bind host port
   5434: `Bind for 0.0.0.0:5434 failed: port is already allocated`. The
   container and an empty `pgdata` volume are left behind. `make up` and the
   `opensearch` service on 9201 have the same exposure.

## The prompt

Make `make dev` and `make test-e2e` work from any checkout of the
repository, including a git worktree, with nothing exported by hand, in the
repository statutes-linkedlegislation, in this worktree, on this branch.

Read first: `CLAUDE.md`, `~/.claude/CLAUDE.md` (prose), `BUILDLOG.md` (the
entry of 2026-09-09 "the compiled side of ADR-0019", its "Verified"
paragraph), `docs/adr/0023` (decisions 2 and 9), `docs/adr/0024`,
`storage/search.py`, `db/config.py`, `api/comps.py` (`_Origins`, and why
`api/` reads `.env` on its own), `ingest/search_sync.py`
(`_disabled`), `ingest/reindex_search.py`, `docker-compose.yml`,
`docker-compose.prod.yml`, `docker-compose.edge.yml`,
`tests/test_compose_networks.py`, `deploy/deploy-on-box.sh`,
`deploy/update-sources.sh`, `.env.example`, `.env.prod.example`, the
`Makefile` (`dev`, `dev-up`, `dev-api`, `up`, `reindex-search`,
`test-e2e`), `tests/test_architecture.py`, and `README.md` "Running it".

Then, with `make test`, `make test-web` and `make test-e2e` over `make dev`
green after each step:

1. **The search settings read `.env`.** Replace the module constants and
   `os.environ.get` calls in `storage/search.py` with one pydantic-settings
   class (`env_file=".env"`, `extra="ignore"`, the same shape as
   `db/config.py: Settings`): `search_url` defaulting to
   `https://localhost:9201`, `search_user` to `admin`, `search_password` to
   `None`, `search_verify_certs` to `True`. The process environment still
   wins over the file, which is what the compose files and the box rely on.
   `SearchNotConfigured` keeps its sentence. `DISABLE_SEARCH_SYNC` may move
   into the same class or stay as it is; say which in the ADR.
   `tests/test_search_route.py` gets its 503 by `monkeypatch.delenv
   ("SEARCH_PASSWORD")`, which a class that reads `.env` would defeat on a
   machine whose `.env` sets it: give the test a way to say "no password"
   that wins over the file (an empty string in the environment, or the
   settings built with `_env_file=None` under `pytest`), and keep a test
   run with no `.env` present cluster-free. Fix the docstring.

2. **The compose project has a fixed name.** Add `name:
   statutes-linkedlegislation` to `docker-compose.yml` (the name the main
   checkout's containers already carry, so `make dev-up` from any checkout
   finds the running `db` rather than starting one). Decide whether
   `docker-compose.prod.yml` and `docker-compose.edge.yml` get a name too:
   the box runs them with `-p` or from a fixed directory
   (`deploy/deploy-on-box.sh`, `deploy/edge/up.sh`), and ADR-0023 decision 2
   and CLAUDE.md gotcha 14 depend on this project's service names not
   answering on `uscode-redesign_default`. `tests/test_compose_networks.py`
   is where a rule about the compose files lives; add the name rule there.
   Confirm from a second worktree that `make dev-up` prints the existing
   container as running and creates nothing.

3. **Docs.** A short ADR (0025) for the two decisions, or an amendment to
   ADR-0023 if the search settings alone are decided and the name goes in
   ADR-0017; README "Running it" says a worktree shares the dev database and
   needs nothing exported; CLAUDE.md gotcha 10 (the ports) gains the project
   name; `.env.example` says the search lines are read from the file; a
   BUILDLOG entry; CLAUDE.md's ADR list if an ADR is filed.

Conventions: `api/` talks only to the `Repository`; SQL in `storage/` and
`ingest/` only; pytest over SQLite with the committed fixtures; commit
messages in the style of `git log` with the attribution lines the session
gives you; prose per `~/.claude/CLAUDE.md`. Ports 8001, 4321 and 5434 are
`make dev`'s; do not start a second OpenSearch (9200 is the US Code site's
dev cluster, 9201 this site's). A push to `main` deploys within three
minutes: push once, when everything is green, then check `/health` and
`GET /api/v1/search?q=rubber` on the box.

Acceptance: from a fresh worktree with the `.env` copied in and nothing
exported, `make dev` starts the API and the reader against the shared
database and `make test-e2e` passes all 74; `make dev-up` from a second
checkout creates no container; `docker ps` shows one `db` and one
`opensearch` for this project; on the box after the push, `/health` reports
the new commit and the search route answers 200; `make test`, `make
test-web` and `make test-e2e` green.
