# The root-TOC session: nothing above a section has an XML representation

Date: 2026-09-10. The prompt for a separate session in its own worktree.
Follows the compilations session (BUILDLOG 2026-09-09, "the compiled side
of ADR-0019"), which took the text out of the JSON answer above a section
and left `format=xml` as it was.

## Measured on the live site, 2026-09-10, commit `9bafd8f`

| Request | Bytes | Time |
|---|---|---|
| `GET /api/v1/us/sComp/74/271` (JSON) | 5,054 | 0.44 s |
| `GET /api/v1/us/sComp/74/271?format=xml` | 20,419,115 | 4.66 s |
| `GET /api/v1/us/sComp/83/703/tI?format=xml` | 1,152,624 | 0.77 s |
| `GET /api/v1/us/sComp/78/373?format=xml` (a gathered root) | a 404 sentence | |
| `GET /api/v1/us/pl/117/328?format=xml` | the whole `pLaw`, about 20 MB | |

`compiled_response` serves `result.xml` for `format=xml`; for the
compilation root that is the whole `statuteCompilation` document and for a
hierarchy node the node cut from it (`_comp_unit_result`, the `wanted ==
"xml"` branch). The enacted side is the same: `_law_result` serves
`Law.xml` and the hierarchy branch of `_unit_result` cuts the node from it
(ADR-0019, decision 2; ADR-0001's consequence "the whole law's XML is
stored on `laws.xml`, so `/us/pl/{c}/{n}?format=xml` serves the `pLaw`
element"). Every `xml_url` on every level points at one of these.

## The model

The US Code site (`../uscode-redesign`, github.com/aih/uscode-redesign;
its ADR-0006 and ADR-0009) has no XML representation of a title or of any
structural node. `api/routes.py: get_by_identifier` negotiates `wanted` and
uses it only in `_section_response`; an identifier that names no section is
tried as a structural node and answers `TocOut` (`node`, `ancestors`,
`children`, `sections`, `release`, `note`) whatever `Accept` or `format=`
said. A title's 32 MB USLM is never served by the API. The reader fetches
`format=xml` for a section only (`fetchToc` for the rest).

## The prompt

Make the compilation root, the enacted law, and every hierarchy node
answer their table of contents for every format, and serve XML only for a
section and a provision, in the repository statutes-linkedlegislation, in
this worktree, on this branch.

Read first: `CLAUDE.md`, `~/.claude/CLAUDE.md` (prose), `BUILDLOG.md` (the
entries of 2026-09-09: "the reader improvements" wave 1, and "the compiled
side of ADR-0019"), `docs/adr/0001`, `0007` (decisions 1 and 8), `0019`
(both sections), `0020` (the stat page reads `Law.xml` for its slice; that
stays), the US Code site's `docs/adr/0006` and `0009` and its
`api/routes.py: get_by_identifier`, `api/responses.py` (`unit_response`,
`xml_url_for`), `api/routes.py` (`enacted_unit`, `compiled_view`),
`api/comps.py` (`compiled_response`, `_etag`, `_xml_url`,
`compiled_unit_out`), `api/schemas.py` (`UnitOut.xml_url`),
`api/comps_schemas.py` (`CompUnitOut.xml_url`, `files`), `params.py`
(`no_whole_document`, `negotiated_format`, `served_note`),
`storage/postgres.py` (`get_unit`, `_law_result`, `_unit_result`,
`get_comp_unit`, `_comp_root`, `_comp_root_result`,
`_gathered_root_result`, `_comp_unit_result`), `storage/repository.py`
(the `wanted` docstrings), `tests/test_api.py` (the `format=xml` assertions
on `/us/pl/81/740` and `/us/pl/111/344/tI`), `tests/test_plaw.py` (the one
on `/us/pl/118/22`), `tests/test_comps_api.py` (`test_format_xml`,
`test_a_hierarchy_node_and_the_compilation_itself`,
`test_no_text_above_a_section`, `test_the_root_of_an_act_served_title_by_title`),
`frontend/src/components/UnitPage.astro` and
`frontend/src/pages/us/sComp/[...identifier].astro` (the three "Source XML"
links and the one `fetchCompUnitXml` call), `frontend/src/lib/types.ts`,
`docs/plans/2026-09-08-reader-contract.md`, and `README.md`'s route tables.

Then, with `make test`, `make test-web` and `make test-e2e` over `make dev`
green after each step:

1. **The API.** `format=xml` and `Accept: application/xml` on a level above
   a section answer the JSON table of contents, the answer the level gives
   for JSON today, with the same ETag, `Cache-Control` and `Vary`. A section
   and a provision keep verbatim USLM for `format=xml`. `xml_url` becomes
   `str | None` on `UnitOut` and `CompUnitOut`, null above a section, with
   the description saying so. `get_unit` and `get_comp_unit` keep `wanted`
   (a section's provision is still cut for both formats) but nothing above
   a section reads `Law.xml` or `CompVersion.xml` at request time for any
   format; `test_no_text_above_a_section` extends its listener to the XML
   request, and an enacted twin of it asserts the same for `laws.xml`.
   `params.no_whole_document` goes: a gathered root answers like every
   other root. `_etag`'s `;xml` suffix applies only where XML is served.
   Decide, and record, whether the answer to `format=xml` above a section
   is a 200 with the JSON body (the US Code site's behaviour, and what
   `negotiated_format`'s "JSON when the client asks for nothing this
   surface serves" already says) or a 406; prefer the 200.

2. **The columns stay.** `Law.xml` and `CompVersion.xml` are still stored
   and deferred: the stat page slice (ADR-0020) reads `Law.xml`, the
   loaders write both, and a later session may cut fragments from them.
   Say so in the ADR.

3. **The reader.** The "Source XML" link is printed only when `xml_url` is
   set; `types.ts` follows the schema; `fetchCompUnitXml` and
   `fetchUnitXml` are already called for sections only, confirm it. The
   contract's enacted and compiled sections say XML is a section's
   representation. No other reader change.

4. **Docs.** ADR-0019 amended with a third section ("XML above a
   section") rather than a new ADR; ADR-0001's consequence about
   `/us/pl/{c}/{n}?format=xml` and ADR-0007 decision 8's sentence about the
   gathered root's 404 struck through with a dated note; the reader
   contract; README's route tables (`?format=xml` on the enacted and the
   compiled rows); a BUILDLOG entry. Verification counts stay generated.

Conventions: `api/` talks only to the `Repository`; SQL in `storage/` and
`ingest/` only; the reader prints the API's sentences verbatim and every
new sentence is built in `params.py`; pytest over SQLite with the committed
fixtures; commit messages in the style of `git log` with the attribution
lines the session gives you; prose per `~/.claude/CLAUDE.md`. Ports 8001,
4321 and 5434 are `make dev`'s; do not start a second OpenSearch (9200 is
the US Code site's dev cluster, 9201 this site's). A push to `main` deploys
within three minutes: push once, when everything is green, and then measure
on the box.

Acceptance, measured on the box after the push: `GET
/api/v1/us/sComp/74/271?format=xml` under 300 KB and 1 s (from 20.4 MB and
4.7 s) and byte-equal to the JSON answer; `GET
/api/v1/us/sComp/83/703/tI?format=xml` under 100 KB; `GET
/api/v1/us/pl/117/328?format=xml` under 300 KB; `GET
/api/v1/us/sComp/83/703/tI/ch1./s1?format=xml` and `GET
/api/v1/us/pl/81/740/s3?format=xml` still start with `<section`;
`/app/us/sComp/83/703/tI/ch1./s1` and `/app/us/pl/81/740/s3` render as
before with their Source XML link; `/app/us/sComp/74/271`, `/app/us/pl/117/328`
and `/app/us/sComp/78/373` render without one; `make test`, `make
test-web`, `make test-e2e` green; the axe scan clean on a compiled root and
an enacted law page.
