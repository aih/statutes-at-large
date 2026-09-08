# Stage 4 prompt

Paste from the line after the rule into a fresh session started in
`statutes-linkedlegislation`.

---

Build stage 4 of ../statute-pdf-to-xml/docs/plans/2026-09-07-statutes-api-design.md in this
repository (statutes-linkedlegislation, https://github.com/aih/statutes-at-large): `PLAW`
packages from the 113th Congress onward loaded from GovInfo bulk data USLM, replacing the
volume-derived units for those laws, with a poller and the `PLAW` collection on `/status`.
Stages 1 to 3 are done and pushed to `main`: read CLAUDE.md, README.md, BUILDLOG.md,
docs/adr/0001 to 0010, docs/verification/README.md, then the design in full (sections 2, 6
and 9 are the contract for this stage; section 1's third bullet says what the US Code site
does with a `/us/pl/` ref for the 104th Congress onward), then ingest/statute.py,
ingest/identifiers.py (the `rules-1.0` identifier rules the volume loader assigns, written
to match GPO's PLAW form), ingest/load.py (`_write_law` replaces a law by primary
identifier), ingest/comps.py (the poller, versions, and check-row pattern), and
storage/postgres.py. Keep the conventions: one `Repository` protocol, no SQL outside
storage/ and ingest/, notes and cache headers in params.py, pytest over SQLite with
fixtures of real source data, a Makefile target per step, an ADR for every decision that
departs from the design.

Inputs (measured 2026-09-08):

- GovInfo bulk data, no key: `https://www.govinfo.gov/bulkdata/json/PLAW` lists the
  congresses that have USLM (113 to 119 and `resources`); `…/json/PLAW/{c}/public` lists
  one `PLAW-{c}publ{n}.xml` per public law with `formattedLastModifiedTime` and `size`,
  plus `PLAW-{c}-public.zip` (the 118th: 275 files, 37 MB of XML, 4.8 MB zipped; the 113th:
  296 files, up to `PLAW-113publ171`). A file is `pLaw` root, USLM 2.0.17, with GPO's
  identifiers on every level (`/us/pl/118/5/dA/tI/s101/a`) and the Stat. pages as
  processing instructions (`<?I97 137 STAT. ?>`) and `page` markers. Send the
  User-Agent in `ingest/hub.py`.
- Private laws are not in bulk data and have no USLM rendition on the API
  (`packages/PLAW-118pvtl1/uslm` is a 400); they stay volume-derived. Laws of the 104th to
  112th Congresses have PDF and text only; the design routes them through the pipeline's
  `digital` profile in `../statute-pdf-to-xml`, which is not this stage: they stay
  volume-derived too, and the ADR says so.
- Already loaded in the dev Postgres on :5434: volumes 26, 64, 68, 72, 124 and 137 (the
  137 file holds 34 of the 118th's laws, CLAUDE.md gotcha 9), six COMPS packages, the
  citation index (1,081,463 rows) and the classification mirror (144,885 rows). The
  `laws` table already has `source_collection`, `source_package`, `source_granule`,
  `provenance_text`, `provenance_identifiers`; `api/routes.py` already reports a `PLAW`
  collection on `/status` (empty).

Sequence and delegation:

1. Yourself: the PLAW parser (`ingest/plaw.py`: one `pLaw` file to a `LawRecord` with
   GPO's identifiers read from the XML rather than assigned, `provenance_identifiers =
   "gpo-uslm"`, `source_collection = "PLAW"`, `source_package = "PLAW-118publ5"`, the
   `citableAs` / Stat. citation, `stat_volume`, page labels from the markers, aliases,
   sections as the storage atom with lower levels stamped as they come; `quotedContent`
   sections skipped as in the volume loader), the loader (`python -m ingest plaw load
   118 …` from the per-congress zip or `--from-dir PATH`, replacing the volume-derived
   law of the same identifier and recording which source each law came from), the
   precedence rule (a STATUTE volume load must not overwrite a PLAW-derived law; a PLAW
   load replaces a STATUTE-derived one), and a comparison report: for every law the
   volume file and the PLAW file both hold, the set difference between the `rules-1.0`
   identifiers and GPO's, per level, written to `docs/verification/plaw-{congress}.json`
   with the load counts. Fixtures: verbatim `PLAW-118publ22.xml` and `PLAW-118publ34.xml`
   (both laws are in `statute-137-slice.xml`, so the two sources meet in tests),
   `PLAW-118publ1.xml` (4 KB, one section), and one 119th-Congress law, under
   `tests/fixtures/plaw/` with a README naming the URLs and the fetch date; a cutter is
   not needed, the files are small. Tests: identifiers, sections, pages, the resolution
   rules over PLAW-derived units, replacement and precedence, `provenance.identifiers ==
   "gpo-uslm"`, `/us/stat/137/…` still answering, `currency.amended` and `alternatives`
   unchanged for 118-22 and 118-34. Commit before delegating.
2. Two subagents in worktrees, neither editing storage/, db/ or params.py:
   (a) the poller: `python -m ingest plaw poll [--congress N] [--since YYYY-MM-DD]
   [--force]` over the bulk listings' `formattedLastModifiedTime`, a `source_checks` row
   with collection `PLAW` per run (success and failure), the zip fast path for a whole
   congress, `--from-dir`, the report; tested with respx on saved listing JSON.
   (b) the API side: the `law.source` block and `provenance` say `PLAW`, `/status`'s
   `PLAW` block carries congresses and law counts, `alternatives` on a PLAW-derived
   unit, the enacted note unchanged in wording; `GET /api/v1/laws/{c}/{n}` gains
   `sources` (which collection the law is served from and whether the volume also holds
   it); README's route table and "Not yet served" updated; tests over the fixtures.
3. Yourself: merge, load the 113th to 119th Congresses into the dev Postgres from the
   zips, record counts and identifier agreement in docs/verification/, run the compose
   stack on :8010 and check `/api/v1/us/pl/118/5/dA/tI/s101`, `/api/v1/us/pl/118/22/s101`
   (now PLAW-derived; compare with the answer before the load) and
   `/api/v1/us/stat/137/112`, write the ADRs (precedence between sources, what stays
   volume-derived, how GPO's identifiers and `rules-1.0` differ and which wins),
   BUILDLOG and README, then commit and push.

Constraints: nothing in tests touches the network; the bulk downloads are Makefile targets
(`make fetch-plaw`, `make plaw`) that are not part of `make test`; never write a token
into source; `GOVINFO_API_KEY` in .env is only for the COMPS poller and is not needed for
bulk data. Report faithfully at the end of each step: what passed, what failed with the
output, what was skipped.
