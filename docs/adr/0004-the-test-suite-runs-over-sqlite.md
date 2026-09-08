# ADR-0004: The test suite runs the repository over SQLite

Date: 2026-09-07. Status: accepted. Departs from the US Code site's convention
of integration tests that skip without a loaded Postgres.

## Context

The US Code site's API tests need a Postgres with Title 16 loaded and skip on a
fresh clone, so `make test` there is green without exercising the routes. This
repository starts with four small verbatim slices of real volumes and four
COMPS files, which load in under a second.

## Decision

`db/models.py` uses portable column types (`Text`, `JSON`, `Date`, `DateTime`),
`db/base.py: make_engine` accepts a SQLite URL, and `tests/conftest.py` builds
an in-memory database, loads every slice through the real loader, and hands the
API client a repository over it. `storage/postgres.py` keeps its name: Postgres
is the deployment database, and the Alembic migrations target it.

## Consequences

- `make test` runs the routes end to end with no service and no network.
- SQL must stay portable: no `JSONB`, `ARRAY`, or `ILIKE` on JSON without a
  cast. The one Postgres-only statement, the per-transaction timeouts in
  `storage/session.py`, is skipped on other dialects.
- Full-volume counts are `@pytest.mark.slow` tests over `data/statute/xmls` and
  skip when the volumes are not downloaded; the committed numbers are in
  `docs/verification/`.
