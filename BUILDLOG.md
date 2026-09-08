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

## 2026-09-08 — stage 3: the citation index, the classification mirror, `cited-by`, `currency.amended`

Asked: build design stage 3 (sections 4, 5 and 6): the `citations` table from
`dreamproit/uscode`, the `classifications` mirror, `GET /api/v1/cited-by`,
and `currency.amended.status` from evidence.

Main agent first: the schema (`citations`, `classification_files`,
`classifications`, `classification_source_checks`; migration `4381d4019386`),
the `Repository` index methods (`cited_by`, `source_credit_evidence`,
`classification_rows`, `classification_amendments`, `index_coverage`,
`enacted_dates`, the two statuses), the citations loader (`python -m ingest
citations --from-hub | --from-dir`, one row per `<ref href>` and per `<a href>`
in revision-note tables, replaced per US Code title, a `USCODE` source check
with the dataset revision), a 57-row parquet fixture cut by
`scripts/extract_citations_fixture.py`, `amended_sentence` and `cited_by_note`
in `params.py`, pyarrow in a `dataset` dependency group.

Two subagents in worktrees, neither touching `storage/`, `db/` or `params.py`:

- (a) `ingest/classifications.py` (`python -m ingest classifications
  [--congress N] [--from-dir PATH] [--force] [--report DIR]`): the US Code
  site's `classifications/tables` listing and `entries` pages, paced at ten
  requests a second, 429 waited out, 5xx retried; one `classification_files`
  row per `pl` table, replaced wholesale when the rows' hash changes, skipped
  when the listing matches what is stored; a check row per run. `GET
  /api/v1/cited-by` (`api/cited_by.py`), and `citations` and `classifications`
  blocks on `/status`. Fixtures: the listing and the first 40 rows of tables
  118-2 and 104 (`tests/fixtures/classifications/`). 30 tests.
- (b) `api/currency.py`: `decide` over the three evidence calls, `later` by
  (congress, number) then by date, `latest`, the codified alternative from the
  index; `LatestOut`, `AmendedOut.of`, `LabelCurrencyOut.amended`. 18 tests,
  with classification rows inserted for the module.

Main agent after the merge: one ADR-0010 from the two drafts, README,
this entry; the full `current` config and the 31 `pl` tables loaded into the
dev Postgres (`docs/verification/citations.json`, `classifications.json`);
the compose stack on :8010 checked on `/us/pl/83/703/s1`,
`/us/act/1890-07-02/ch647/s1` and `cited-by?identifier=/us/pl/104/333/s814`.

Decisions: ADR-0008 (the citation index: `current` config, one row per ref,
replaced per title), ADR-0009 (the tables mirrored through the US Code
site's API), ADR-0010 (`currency.amended` at request time; the classification
rule is a join).

Verified: `make test` 220 passed, 5 deselected, no network; the citation load
over Postgres in 405 s (1,081,463 rows); the mirror in 78 s (144,885 rows,
31 files, 104th to 119th Congress).

## 2026-09-08 — stage 4: public laws from PLAW bulk data

Asked: build design stage 4 (sections 2, 6 and 9): PLAW packages from the
113th Congress onward from GovInfo bulk-data USLM, replacing the
volume-derived units for those laws, with a poller and the PLAW collection on
`/status`.

Main agent first: `ingest/plaw.py` (one `pLaw` file to a `LawRecord` with
GPO's identifiers read from the XML, `provenance_identifiers = "gpo-uslm"`,
the rules-1.0 fallback for levels the file leaves unidentified, counted per
level; the citation, volume and pages from `citableAs`, the running-head
instruction and the page markers; quoted sections skipped; `python -m ingest
plaw fetch | load` from the per-congress zip, a directory, or files;
`make fetch-plaw`, `make plaw`), the precedence in `ingest/load.py:
_write_law` (`SOURCE_PRECEDENCE`, `WriteOutcome`, `laws_kept_from_plaw`,
compilations re-pointed), the identifier comparison per level written to
`docs/verification/plaw-{congress}.json`, `Repository.law_sources` and the
PLAW `collection_status` by congress. Fixtures: four whole bulk-data files and
the listings (`tests/fixtures/plaw/`); the 137 slice gains 118-3 so one law
stays volume-derived in the test database. 20 tests.

Two subagents in worktrees, neither touching `storage/`, `db/` or `params.py`:

- (a) `ingest/plaw_poll.py` (`python -m ingest plaw poll [--congress N]
  [--since YYYY-MM-DD] [--force] [--limit N] [--from-dir PATH] [--report DIR]
  [--json]`): the bulk listings against the stored `laws` rows; a file is due
  when no PLAW-derived row has its package id, when the listing time is later
  than `loaded_at`, or under `--force`; a congress with nothing PLAW-derived
  or more than half its files due is loaded from its zip, otherwise file by
  file with a commit per law; one `PLAW` check row per run. `make plaw-poll`.
  17 tests over respx and the fixture directory.
- (b) the API side: `ProvenanceOut` names the three identifier provenances,
  `CollectionStatusOut` gains `congresses` and `laws_by_congress`,
  `GET /api/v1/laws/{c}/{n}` gains `sources` (`LawSourcesOut`), README's
  route table, stage 4 paragraph and "Not yet served". 6 tests, including
  `alternatives` and `view=compiled` over a PLAW-derived unit with a
  compilation inserted for the module.

Main agent after the merge: the running head settles the volume when
`citableAs` disagrees (five files); `--volumes-dir` makes the comparison
reproducible on a re-load; the 113th to 119th Congresses loaded into the dev
Postgres from the zips (2,149 laws, 55,897 units, 63 s; 34 laws of volume
137 replaced; 11,840 identifiers on 13 levels compared, all agree); a live
poll (2,149 listed, none due, 12 s); the compose stack on :8010 checked on
`/us/pl/118/5/dA/tI/s101`, `/us/pl/118/22/s101` (same served identifier,
text, pages and alternatives as before the load; `law.source` and
`provenance` now PLAW and `gpo-uslm`, and the latest amending law 118-35
carries its date now that it is loaded), `/us/stat/137/112`,
`/laws/118/22` and `/status`; ADRs, README, CLAUDE.md, this entry.

Decisions: ADR-0011 (a PLAW package outranks the volume file), ADR-0012 (what
stays volume-derived: private laws, the 104th to 112th), ADR-0013 (GPO's
identifiers are read; rules-1.0 fills the gaps; the running head wins over a
wrong `citableAs`).

Verified: `make test` 263 passed, 5 deselected, no network; the seven
reports in `docs/verification/`.
