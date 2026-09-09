# ADR-0019: A law answer carries no `text`; `Law.xml` is a deferred column

Date: 2026-09-09. Status: accepted. Implements
`docs/plans/2026-09-09-reader-improvements-plan.md`, package A.

## Context

`GET /api/v1/us/pl/117/328` measured at 4,748,777 bytes and 4.8 s. `UnitOut.text`
carried the law's whole plain text, computed by `plain_text()` over the law's
20 MB USLM on every request. The hierarchy branch of `_unit_result` (a
division, title, chapter, and so on) did the same over its own fragment,
smaller but still parsed on every request. `Law.xml` was an eager column, so
even a JSON request that never used it loaded the whole `pLaw` element from
Postgres.

## Decision

1. **`UnitOut.text` is empty for `level: "law"` and for a hierarchy level.**
   `_law_result` sets `text=""` without parsing the law's XML. The hierarchy
   branch of `_unit_result` sets `text=""` without parsing the law's XML
   either. A section and a `provision` are unaffected: `Unit.xml` and
   `Unit.text` are stored per section and stay eager.

2. **`Law.xml` is `mapped_column(Text, deferred=True)`.** A query for a `Law`
   row does not fetch it. `PostgresRepository.get_unit` takes `wanted: str =
   "json"`; `_law_result` and the hierarchy branch of `_unit_result` load
   `law.xml` only when `wanted == "xml"`. `api/routes.py` computes the
   negotiated format before calling `get_unit`, so it can pass `wanted`
   through. No Alembic migration: `deferred` changes how SQLAlchemy reads the
   column, not the column itself.

3. **`pages` is unchanged.** A law still lists every Statutes at Large page it
   spans.

4. **The compiled side is out of scope here.** `CompUnitOut.text` and whether
   `CompVersion.xml` becomes deferred are left for the compilations session.

## Consequences

- `unit_etag` is unchanged: it hashes `content_hash`, a stored column, not the
  XML.
- `amended_for_unit` passes `result.text` into `api/currency.py: decide()`
  regardless of level; the compiled-text comparison there only fires when
  `level == "section"`, so an empty `text` on a law or a node changes nothing
  it decides.
- `Repository` still has one method, `get_unit`, for resolution; `wanted` is a
  parameter of it, not a second surface.
