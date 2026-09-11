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
   column, not the column itself. Amended 2026-09-10: nothing above a section
   reads `law.xml` for either format ("XML above a section" below).

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
   name. Amended 2026-09-10: nothing above a section reads the column for
   either format ("XML above a section" below).

3. **The ETag is unchanged.** `_etag` hashes `content_hash`, a stored
   column; a root gathered from per-title files (ADR-0007, decision 8)
   hashes the files' hashes.

`tests/test_comps_api.py: test_no_text_above_a_section` asserts the empty
`text` on the root and on a title, the populated `xml` for
`wanted="xml"`, and, through a `before_cursor_execute` listener, that no
statement of a JSON answer selects `comp_versions.xml`.

## XML above a section

Amended 2026-09-10. Measured on the live site at `9bafd8f`: `GET
/api/v1/us/sComp/74/271?format=xml` 20,419,115 bytes in 4.66 s,
`/us/sComp/83/703/tI?format=xml` 1,152,624 bytes, `/us/pl/117/328?format=xml`
the whole `pLaw`, about 20 MB. Every level's `xml_url` pointed at one of
these. The US Code site serves no XML for a title or a structural node (its
ADR-0006 and ADR-0009): an identifier that names no section answers its
table of contents whatever `Accept` or `format=` said.

1. **XML is a section's representation.** `format=xml` and an XML
   `Accept:` on a section serve its stamped USLM, and on a path below a
   section the provision cut from it. On a law, a compilation root
   (gathered or not) and a hierarchy node they answer the JSON the level
   gives for JSON: the same body, `ETag`, `Cache-Control`, `Vary` and
   `X-Served-Identifier`, with `Content-Type: application/json`.
   `params.serves_xml` holds the rule; `api/responses.py: unit_response`
   and `api/comps.py: compiled_response` apply it.

2. **The answer is a 200, not a 406.** `negotiated_format` answers JSON
   when the client asks for nothing the surface serves, and the US Code
   site answers a structural node the same way.

3. **`xml_url` is `str | None`** on `UnitOut` and `CompUnitOut`, null above
   a section. The reader prints its "Source XML" link only when it is set,
   and fetches `format=xml` for a section only.

4. **Nothing above a section reads `Law.xml` or `CompVersion.xml` at
   request time.** `get_unit` and `get_comp_unit` keep `wanted`; a
   section's provision is cut for both formats, and a law's, a
   compilation's and a node's `xml` is empty for both.
   `params.no_whole_document` is gone. `_etag`'s `;xml` suffix applies only
   where XML is served, so the XML request of a root carries the JSON
   answer's ETag.

5. **The columns stay.** `Law.xml` and `CompVersion.xml` are still stored
   and deferred. The stat page slice reads `Law.xml` (ADR-0020); the
   volume, PLAW and COMPS loaders write both; a later change may cut
   fragments from them. No migration.

`tests/test_api.py: test_no_law_xml_is_read_above_a_section` and
`tests/test_comps_api.py: test_no_text_above_a_section` listen on
`before_cursor_execute` over the JSON and the XML requests and assert that
no statement selects `laws.xml` or `comp_versions.xml`. On the dev
database: `/us/sComp/74/271?format=xml` 2,308 bytes in 18 ms, byte-equal
to the JSON; `/us/sComp/83/703/tI?format=xml` 4,590 bytes;
`/us/pl/117/328?format=xml` 146,580 bytes in 0.20 s.

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
