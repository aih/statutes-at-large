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
   Amended 2026-09-09: the "Compiled" section below settles it.

## Compiled

Amended 2026-09-09. `GET /api/v1/us/sComp/74/271` (the Social Security
Act's whole-act file) measured at 8,385,144 bytes and 4.58 s, `text` being
`plain_text()` over the whole compilation on every request;
`/us/sComp/83/703/tI` at 540,777 bytes, the title cut from the document.
`CompVersion.xml` was an eager column, so every `CompVersion` row read
loaded the document.

1. **`CompUnitOut.text` is empty for `level: "compilation"` and for a
   hierarchy level.** `_comp_root_result` and the hierarchy branch of
   `_comp_unit_result` set `text=""` without parsing the document. A section
   and a `provision` are unaffected: `CompUnit.xml` and `CompUnit.text` are
   stored per section and stay eager.

2. **`CompVersion.xml` is `mapped_column(Text, nullable=False,
   deferred=True)`.** `Repository.get_comp_unit` takes `wanted: str =
   "json"`; the compilation's and a node's `xml` is read only for `wanted ==
   "xml"`. `api/comps.py: compiled_response` negotiates the format before
   the repository call and passes it down. No migration. No other reader of
   the column exists in `storage/` or `api/`: `_version_of`,
   `compilations_for_law`, `compiled_counterparts`, `api/currency.py` and
   `api/cite.py` read the version's metadata only, and
   `ingest/search_sync.py: comp_documents` selects the unit's columns by
   name.

3. **The ETag is unchanged.** `_etag` hashes `content_hash`, a stored
   column; a root gathered from per-title files (ADR-0007, decision 8)
   hashes the files' hashes.

`tests/test_comps_api.py: test_no_text_above_a_section` asserts the empty
`text` on the root and on a title, the populated `xml` for
`wanted="xml"`, and, through a `before_cursor_execute` listener, that no
statement of a JSON answer selects `comp_versions.xml`.

## Consequences

- `unit_etag` is unchanged: it hashes `content_hash`, a stored column, not the
  XML.
- `amended_for_unit` passes `result.text` into `api/currency.py: decide()`
  regardless of level; the compiled-text comparison there only fires when
  `level == "section"`, so an empty `text` on a law or a node changes nothing
  it decides.
- `Repository` still has one method, `get_unit`, for resolution; `wanted` is a
  parameter of it, not a second surface. The same holds for `get_comp_unit`.
- Measured on the dev database after the compiled amendment:
  `/us/sComp/74/271` 2,340 bytes in 19 ms; `/us/sComp/83/703/tI` 4,625
  bytes in 19 ms.
