# BUILDLOG

One entry per session: what was asked, what was decided, what was verified.

## 2026-09-07 — stage 1: schema, repository, STATUTE loader

Asked: build stages 1 and 2 of the statutes API design in a new repository.

Done in this session by the main agent:

- Schema (`db/models.py`, migration `5afe43f05819`), the `Repository` protocol
  and its SQLAlchemy implementation, identifier parsing, `params.py`, the
  citation redirector, the app skeleton.
- The STATUTE volume loader with the section-7 identifier rules, the numbering
  pass for colliding law numbers, and the load report.
- Volumes 64 and 124 loaded into Postgres; reports in `docs/verification/`.
- 64 tests over SQLite and verbatim slices; `make test` and `make test-slow`
  green.

Decisions: ADR-0001 to ADR-0005.

Verified: `make test-all` (64 passed); `python -m ingest statute` over volumes
64, 72, 124, 137 (counts in `docs/verification/README.md`; 72 and 137 parsed
but not committed as reports because only 64 and 124 were asked for).

## 2026-09-07 — stage 2: API routes, COMPS, the two views

Two subagents in worktrees, each with its own tests, merged by the main agent:

- Enacted-view routes (`api/routes.py`, `api/schemas.py`, `api/responses.py`,
  `tests/test_api.py`, 34 tests): `/api/v1/us/pl|pvtl|act`, `/us/stat`,
  `labels`, `status`, `laws/{c}/{n}[/sections/{num}]`; ETag, `If-None-Match`,
  `Cache-Control` per design section 5.
- COMPS (`ingest/govinfo.py`, `ingest/comps.py`, `api/comps.py`, 48 tests):
  the GovInfo client, parser, loader with `comp_versions`, the poller, the
  `comps` CLI, `/us/sComp/…`, `/comps`. Live: four packages loaded, one poll.

Main agent after the merge: `alternatives` for the enacted view
(`api/alternatives.py`), `view=compiled` served through the counterpart,
level-aware note wording in `params.py`, the loader fixes the era sweep found
(Roman chapter numbers, several `pLaw` per component, chapter in the preface,
repeated laws), volumes 26 and 68 loaded so the Sherman Act and the Atomic
Energy Act meet their compilations in tests and in Postgres.

Decisions: ADR-0006 (restated acts), ADR-0007 (compilations).

Verified: `make test` 153 passed; `make test-slow` over volumes 64, 72, 116,
124, 137; the compose stack on :8010 serving both views from Postgres.

## 2026-09-08 — stage 3a: the classifications mirror and `cited-by`

A subagent in a worktree, on top of the main agent's stage-3 base (the
`citations` tables and loader, ADR-0008, the `Repository` index methods):

- `ingest/classifications.py`, `python -m ingest classifications
  [--congress N] [--from-dir PATH] [--force] [--report DIR] [--json]`: the US
  Code site's `classifications/tables` listing and `entries` pages, paced at
  ten requests a second, 429 waited out, 5xx retried; one
  `classification_files` row per `pl` table, replaced wholesale when the
  rows' hash changes, skipped when the listing matches what is stored; a
  `classification_source_checks` row per run. Fixtures in
  `tests/fixtures/classifications/` (the listing and the first 40 rows of
  tables 118-2 and 104).
- `GET /api/v1/cited-by` (`api/cited_by.py`, `CitedByOut`): `identifier`,
  `context`, `limit`, `offset`; ETag and 304; 60 requests then 2 a second.
  `citations` and `classifications` blocks on `/api/v1/status`.
- `tests/test_classifications.py` (18 tests) and `tests/test_cited_by.py`
  (12 tests); `conftest.loaded` loads the classification fixtures.

Verified: `make test` 202 passed in about 2 s, no network.
