# statutes-linkedlegislation

Public laws from the Statutes at Large at the section level, addressed by the
identifiers the US Code writes in its source credits, plus the Statute
Compilations the House Office of the Legislative Counsel maintains. Design:
`../statute-pdf-to-xml/docs/plans/2026-09-07-statutes-api-design.md`.

## What is served

Stage 1 (this repository, enacted view):

| Identifier | Answer |
|---|---|
| `/us/pl/{congress}/{num}` | the public law: summary, table of contents, verbatim USLM |
| `/us/pl/{congress}/{num}/{path}` | a section or a level below it, `{path}` in GPO's PLAW form (`/tI/s101`, `/s3/1`) |
| `/us/pvtl/{congress}/{num}[/{path}]` | a private law |
| `/us/act/{YYYY-MM-DD}/ch{n}[/{path}]` | a chapter-numbered act; laws from 1901 to 1957 answer to this form and to their law number |
| `/us/stat/{volume}/{page}` | every law that starts on or spans the page, with the unit the page marker falls in and the text it prints there |

Resolution: exact match; otherwise the longest stored prefix, with a path below a
section cut from the section's XML; otherwise the section number under the law,
ignoring hierarchy. The response says which rule answered (`note`,
`served_identifier`).

## Routes

All under `/api/v1`. The bare identifier URL (`/us/pl/81/740/s3`) is a 307 to
`/api/v1/…` for a program and to `/app/…` for a browser.

| Route | Answer |
|---|---|
| `GET /us/pl/{c}/{n}[/{path}]`, `/us/pvtl/…`, `/us/act/{date}/ch{n}[/{path}]` | the unit: `identifier`, `served_identifier`, `view`, `resolution`, `law`, `currency`, `alternatives`, `note`, `provenance`, `pages`, `text`, `xml_url`, `level`, `num`, `heading`, `ancestors`, `children`, `provision`, `occurrences` |
| `GET /us/stat/{volume}/{page}[?format=xml]` | `{page, identifier, volume, documents: [{identifier, kind, title, label, citation, enacted, starts_here, unit_on_page, units, text}], pdf}`; `text` and `units` are what the law prints on the page, the slice between its page markers (ADR-0020), and `format=xml` serves the slices as USLM |
| `POST /labels` `{"identifiers": […]}`, `GET /labels?identifier=…` | per identifier: `{exists: true, served_identifier, resolution, num, heading, level, kind, law_identifier, law_label, currency}`, for a `/us/stat/{vol}/{page}` identifier `{exists: true, level: "page", kind: "stat", volume, page, documents: [{identifier, label, kind, starts_here}], pdf}`, or `{exists: false}`; 1 to 100 per request; 300 requests then 30 per second per address |
| `GET /cite?q=Pub. L. 104-333, § 814` | a written citation parsed (`citeparse.py`) and checked: `{query, kind, identifier, section_identifier, law_identifier, label, exists, served_identifier, resolution, level, num, heading, law_label, url, stat_page, hierarchy, note, message}`; 422 when the text is not a citation, `exists: false` when nothing is loaded at the identifier, `exists: true` with the citation URL; `kind: "usc"` with the US Code site's URL and `exists: null` for a US Code citation; `max-age=300`, ETag; 60 requests then 2 per second per address |
| `GET /status` | `{collections: {STATUTE, COMPS, PLAW}, checks: {…}, stale, citations, classifications}`; the `PLAW` block adds `congresses` and `laws_by_congress` |
| `GET /laws/{c}/{n}` | `{law, toc, section_count, compilations, sources}`; `sources` is `{served_from, package, identifiers, volume: {package, loaded, govinfo}, plaw: {package, uslm, loaded, govinfo}}` |
| `GET /laws/{c}/{n}/sections/{num}` | the section by number, ignoring hierarchy; same body as the identifier routes |

Query parameters on the identifier routes: `view=enacted` (default) or
`view=compiled` (a 404 with `alternatives` when the unit has no compiled counterpart),
`format=json` or `format=xml` (otherwise `Accept:`; XML is the stamped USLM
element, the provision alone when the path went below a section), `through`
(a compilation version; ignored on the enacted view).

Headers on a unit: `ETag` (the content hash; a found provision appends a hash
of its identifier), `Cache-Control: public, max-age=31536000, immutable`,
`Vary: Accept`, `X-Served-Identifier`. `If-None-Match` answers 304. A stat page
is immutable with an `ETag` over its documents and their slices. `labels`, `status`, and the law
summary are `public, max-age=300`. `HEAD` is not registered and answers 405.

`currency.amended` is decided from the stage 3 indexes (below); `labels`
carries the same block, without the compiled-text comparison.

Source: GovInfo `STATUTE` volume USLM from the Hub dataset
`dreamproit/us-statutes-at-large` (`xmls/STATUTE-{n}.xml`). The volume files
carry no identifiers; the loader assigns them by the rules in the OCR plan,
section 7 (`ingest/identifiers.py`, version `rules-1.0`), and stamps them into
the stored XML. `provenance` on every response records `gpo-uslm` text and
where the identifiers came from: `rules-1.0` (assigned by the volume loader),
`gpo-uslm` (read from a PLAW file, stage 4), or `gpo-uslm+rules-1.0` (a PLAW
file with some levels filled in by rule).

Loaded and verified so far: volumes 26, 64, 68, 72, 124 and 137
(`docs/verification/`), and eleven more volumes from every era run through the
loader (`docs/verification/era-sweep.md`). The loader handles all 137 volumes
(`make load-all`).

Stage 2 (compiled view):

| Identifier | Answer |
|---|---|
| `/us/sComp/{congress}/{num}[/{path}]` | a Statute Compilation unit in GPO's identifier form (`/tI/ch1./s1`); `?through=118-67` selects a stored version |
| `/us/pl/…?view=compiled` (also `/us/pvtl`, `/us/act`) | the compiled counterpart of the enacted unit, matched by section number; 404 with `alternatives` when there is none |
| `GET /api/v1/comps?law=/us/pl/83/703&q=atomic` | compilations for a law, or by title search |
| `GET /api/v1/comps/{fileId}` | a compilation's summary, version list, and table of contents |

Every unit response carries `alternatives`: the compiled counterpart with its
`current_through`, the codified US Code section the compilation's editorial
note names, and, on a compiled unit, the enacted section. The note names them
in the words of design section 4.

Source: the GovInfo API (`collections/COMPS/{since}`, `packages/{id}/summary`,
`packages/{id}/uslm`) with `GOVINFO_API_KEY` from the environment. Each fetch
that changes a package's content hash is a new `comp_versions` row; GovInfo
keeps only the current text, so the history starts at the first ingest.
The first walk of the whole collection (2026-09-09, `make comps-walk` hourly
under the API's 1,000 calls an hour) saw 2,685 packages and loaded 2,675.
The 10 it could not load fail the same way on every poll and are listed in
`checks.COMPS.error` on `/status`:

- Four have no USLM on GovInfo, only a PDF; the `uslm` endpoint answers 400:
  COMPS-1826 (Railway Labor Act), COMPS-17514 (Consolidated Appropriations
  Act, 2023), COMPS-15409 (Indian Tribal Energy Development and
  Self-Determination Act Amendments of 2017), COMPS-10414 (flexible
  regulation of interest rates on deposits).
- Five are USLM files of 2 to 7 KB holding a `meta` block and no `main`:
  COMPS-305, 332, 3061, 3126, 5336. The loader reports `no /us/sComp/
  identifier in the document and no law in the summary`.
- COMPS-77777777 is the whole Public Health Service Act in one 13 MB file
  whose identifiers have an empty law slot (`/us/sComp//tI/s1`) and whose
  summary names no law. The act is served title by title from its per-title
  packages under `/us/sComp/78/410`.

A poll counts a failed package as fetched, so `deploy/comps-walk.sh` ends the
walk on a run that reports `0 new, 0 new versions`, not on one that reports
0 fetched.

Stage 3 (the indexes):

| Route | Answer |
|---|---|
| `GET /api/v1/cited-by?identifier=/us/pl/104/333/s814` | the US Code sections whose source credits, notes, or text cite the law, the section (by number, whatever hierarchy the ref wrote), a path below it, or a Statutes at Large page: `{identifier, law_identifier, law, aliases, section_num, below, contexts, total, limit, offset, release_labels, index, sections: [{identifier, citation, heading, release_label, url, refs: [{href, context, note_topic, date}]}], note}`; `context` (`sourceCredit`, `note`, `text`, repeatable), `limit` (1 to 200), `offset`; `law` is null when the law is not loaded and the index answers alone; 404 when the index holds nothing for an unloaded law; ETag and `If-None-Match`; `max-age=300`; 60 requests then 2 per second |
| `currency.amended` on every enacted unit and label | `{status, latest, evidence}`: `known_amended` when a US Code source credit that cites the unit names a later law, when a classification row of a later law amends a US Code section the unit was classified to, or when a compilation current through a later law has different section text; `no_record` when the indexes know the law and none of that matched; `unknown` for a private law or a law in no index. `latest` is `{pl, identifier, label, enacted}` of the newest law that matched; `evidence` lists `source_credit`, `classification`, `compilation` in that order. The note's amended sentence says the same (`params.amended_sentence`; ADR-0010) |

The codified alternative of an enacted section names the compilation's own
`uscRef` sections and then the US Code sections whose source credits cite it,
at most 20.

Sources: the citation index is the `dreamproit/uscode` dataset's `current`
config, one row per `<ref href>` to `/us/pl/`, `/us/pvtl/`, `/us/act/` or
`/us/stat/` with its context, replaced per US Code title
(`python -m ingest citations --from-hub`, `make citations`, ADR-0008); the
classification tables are mirrored from the US Code site's API, one
`classification_files` row per table, replaced wholesale when its rows change
(`python -m ingest classifications`, `make classifications`, ADR-0009).
Loaded: the whole `current` config (1,081,463 rows from 65,938 sections) and
the 31 `pl` tables from the 104th to the 119th Congress
(`docs/verification/citations.json`, `classifications.json`).

Stage 4 (public laws from `PLAW`):

Public laws of the 113th Congress onward are loaded from GovInfo's PLAW bulk
data (`https://www.govinfo.gov/bulkdata/PLAW/{congress}/public/`, no key), one
USLM file per law with GPO's own identifiers on every level. A PLAW load
replaces the volume-derived copy of the same law; a volume load leaves a
PLAW-derived law alone and lists it in its report (`laws_kept_from_plaw`).
`law.source` on a unit names the collection and package the served copy came
from, and `provenance.identifiers` is `gpo-uslm` for a PLAW-derived law. The
`/us/stat/{volume}/{page}` routes, `alternatives`, `currency.amended` and the
enacted note are the same over either source. Private laws are not in bulk
data and stay volume-derived; so do laws of the 104th to 112th Congresses,
which GovInfo holds as PDF and text only, until the pipeline's digital profile
(`../statute-pdf-to-xml`) lands.

`GET /api/v1/laws/{c}/{n}` carries `sources`: `served_from` (`STATUTE` or
`PLAW`), the `package`, the `identifiers` provenance, `volume` (the
`STATUTE-{n}` package, whether it is loaded, the GovInfo link to the law's
first page) and `plaw` (the `PLAW-{c}publ{n}` package, whether GovInfo has USLM
for it, whether the law is served from it, the GovInfo link; `package` is
null before the 104th Congress). `/status`'s `PLAW` block carries
`congresses` and `laws_by_congress` (`{"118": 274}`, one package per law), and
`volumes` lists the volumes its laws print in.

`python -m ingest plaw poll` keeps the collection current from the bulk
listings (`https://www.govinfo.gov/bulkdata/json/PLAW` and `…/PLAW/{c}/public`):
a file is due when no PLAW-derived copy is stored, when the listing shows it
modified after the stored copy's `loaded_at`, or under `--force`. A congress
with nothing PLAW-derived stored, or with more than half its files due, is
loaded from its zip (`data/plaw/PLAW-{c}-public.zip`, re-downloaded when the
listing's zip is newer); otherwise the due files are fetched one by one.
Options: `--congress N` (repeatable), `--since YYYY-MM-DD` (default: the newest
listing time the last poll saw, less a day), `--force`, `--limit N`,
`--from-dir PATH` (listings and files from a directory, no network),
`--report DIR` (writes `DIR/plaw-poll.json`), `--json`. Every run writes a
`source_checks` row with collection `PLAW`; `ok` is false only when a listing
could not be read.

```
python -m ingest plaw fetch 113-119                    # the per-congress zips into data/plaw
python -m ingest plaw load 118 --report docs/verification
python -m ingest plaw poll --report docs/verification  # what changed on GovInfo
make fetch-plaw / make plaw / make plaw-poll           # the three above, congresses 113 to 119
```

Loaded: the 113th to 119th Congresses, 2,149 public laws, 55,897 units
(`docs/verification/plaw-{congress}.json`); the 34 laws of volume 137 the Hub
file holds are now served from their PLAW packages, and on those laws GPO's
identifiers and the rules-1.0 set agree on every level (ADR-0013). Where a
PLAW file leaves a level unidentified, the rules fill it in and
`provenance.identifiers` says `gpo-uslm+rules-1.0` (133 laws). Precedence
between the sources is ADR-0011; what stays volume-derived is ADR-0012.

Other routes: `POST /api/v1/labels` (up to 100 identifiers, existence and
heading, what the US Code site's reference resolver calls), `GET /api/v1/status`
(what is loaded per collection, the last poll, `stale` after a week;
`citations`: the index's rows, citing sections, titles, release labels, and
the dataset revision; `classifications`: the tables mirrored with their
covered laws and row counts, and the last mirror run with `stale` after a
week), `GET /api/v1/laws/{c}/{n}` and `/sections/{num}`.

Caching (design section 5): enacted units and Statutes at Large pages are
`immutable`; a compiled unit is `immutable` only when pinned with `through=`;
`labels`, `status` and unpinned compiled views are `max-age=300`. Every unit
response carries an `ETag` and answers `If-None-Match` with 304. `HEAD` is not
routed (405).

## Not yet served

- Laws of the 104th to 112th Congresses from `PLAW` (PDF and text only; they
  come from the volumes until the pipeline's digital profile lands).
- Private laws from `PLAW` (no USLM on GovInfo); they come from the volumes.
- Concurrent resolutions, proclamations, treaties, and agreements printed in
  the volumes. They are counted in the load report and skipped.
- The reprocessed OCR text (design stage 6). The text is GPO's digitization
  vendor's, errors included.

## Reader

The reader at `/app` (`frontend/`, Astro 5 with TypeScript and USWDS 3,
server-rendered on Node behind Caddy) reads `/api/v1` and prints the API's
`note`, `message` and `detail` sentences verbatim
(`docs/plans/2026-09-08-reader-contract.md`, ADR-0014). A sticky header, a
rail listing the page's own panels and the law's contents, and disclosures
for Contents and Pages sit around that text (ADR-0021); each page carries
one small inline script, under the ceiling `docs/js-budgets.json` states for
its route. Pages:

| Page | Shows |
|---|---|
| `/app/` | what is loaded, from `/status`; the citation box; the forms it accepts |
| `/app/goto?q=` | the box's target: 307 to the unit on a hit, 307 to the US Code site for a US Code citation, 404 with the note for a citation naming nothing loaded, 422 with the detail for text that is not a citation |
| `/app/us/pl/{c}/{n}`, `/us/pvtl/…`, `/us/act/…` | the law: titles, dates, citation, aliases, sources, table of contents, the "cited by" panel |
| `/app/us/pl/{c}/{n}/{path}` (and the other kinds) | a hierarchy node's contents, or a section's text rendered from `?format=xml` with a provision marked, the note, the currency line, alternatives, Stat. pages with govinfo links, breadcrumbs, previous and next, cross references resolved through `/labels`, the "cited by" panel, provenance |
| `/app/us/sComp/{c}/{n}[/{path}]` | the compiled view with the version picker (`?through=`) and the enacted counterpart |
| `/app/us/stat/{vol}/{page}` | the documents on the page |

Cross references: `/us/usc/…` links to the US Code site (`USCODE_ORIGIN`);
`/us/pl/`, `/us/pvtl/`, `/us/act/` and `/us/stat/` links stay on this site
when `/labels` says they exist, go to govinfo for a public law of the 104th
Congress onward or a Stat. page that does not, and are text otherwise. The
US Code site applies the same rule towards this site (ADR-0016).

## Running it

```
cp .env.example .env            # DATABASE_URL, GOVINFO_API_KEY
make dev-up                      # Postgres on :5434
make migrate                     # alembic upgrade head
make dev-data                    # volumes 64 and 124 from the Hub, with reports
make dev                         # the API on :8001 and the reader's dev server on :4321
make dev-web                     # the reader alone
make test                        # pytest over SQLite and the committed slices; no Node
make test-web                    # vitest over the reader's renderer, ref rules, client
make test-e2e                    # Playwright and axe over a running site (BASE_URL)
make cite Q="Pub. L. 81-740, § 3"   # the parser, then GET /api/v1/cite on the running site
make up                          # docker compose: Postgres, API, reader, Caddy on :8010
python -m ingest comps load COMPS-1630 COMPS-3055   # fetch and load packages
python -m ingest comps poll --since 2026-09-01      # walk the collection
python -m ingest comps report
python -m ingest citations --from-hub --report docs/verification    # the citation index
python -m ingest classifications --report docs/verification         # the classification tables
python -m ingest plaw fetch 113-119                 # PLAW bulk-data zips into data/plaw
python -m ingest plaw load 118 --report docs/verification           # public laws from the zip
python -m ingest plaw poll --report docs/verification               # what changed on GovInfo
python -m ingest fetch-statute 1-137 --if-changed   # the Hub's tree listing against the files on disk
python -m ingest statute --volumes 1-137 --changed-only             # only files that differ from their last load
python -m ingest citations --from-hub --if-changed  # skip the reload when the dataset revision is the recorded one
python -m ingest reindex-search [--if-changed] [--since YYYY-MM-DD] [--recreate]   # the OpenSearch index (ADR-0023)
make reindex-search                                 # reindex-search --if-changed against the dev cluster
```

On the box (`docs/plans/2026-09-08-deployment-plan.md`, sections 4 to 6):

```
bash deploy/deploy-on-box.sh <sha>       # what continuous deploy runs: pull, migrate, up, the proxy recreated
make load-prod                           # the first load: volumes, PLAW, the indexes, the first 400 COMPS packages
sudo systemd-run --unit statutes-comps-walk --uid ec2-user --working-directory $PWD bash deploy/comps-walk.sh
                                         # the rest of the COMPS walk: `make comps-walk` hourly until a run loads nothing
make update-prod                         # the weekly update (deploy/update-sources.sh); update-prod-check records the checks only
bash deploy/watchdog.sh                  # one probe; cron runs it every minute
bash deploy/edge/up.sh                   # the shared edge proxy (once per box)
ALERT_EMAIL=<address> bash deploy/alarms.sh <instance-id>
                                         # the SNS topic and the two alarms; re-run it to apply a change of shape
```

`make test` needs no database, no network and no Node: the suite loads
verbatim slices of the source files (`tests/fixtures/`) into SQLite, and the
citation parser's accepted-forms table runs with no fixtures at all.
`make test-slow` parses the downloaded volumes under `data/statute/xmls`.
`make test-web` and `make test-e2e` are the reader's suites.

## Deployment

`statutes.linkedlegislation.org` runs on the US Code site's box as a
second compose project behind one edge Caddy that terminates TLS for both
hostnames (ADR-0017). The plan and runbook is
`docs/plans/2026-09-08-deployment-plan.md`: what is measured, the AWS
resources, the box, the first load, the weekly update (ADR-0018),
continuous deploy and the alarms. `deploy/` holds the scripts it names;
`deploy/edge/` the edge and its README (the rehearsal on a workstation);
`.github/workflows/` CI, the deploy and the weekly update.

Search runs on the US Code site's OpenSearch cluster, reached through
`search-relay` — the only service of this project attached to that project's
Docker network, and named nothing that project names (ADR-0024). The watchdog
publishes `Statutes/SiteUp`, `ApiUp`, `AppUp` and `EdgeUp` every minute;
`statutes-site-down` alarms on five of the last seven minutes of `SiteUp`
below 1.

## Layout

```
ingest/      statute.py (volume USLM → laws and units), identifiers.py (the rules),
             numbering.py (law-number collisions), load.py, hub.py, comps.py (the
             COMPS parser, loader and poller), govinfo.py (the API client),
             citations.py (the citation index from the uscode dataset),
             classifications.py (the classification tables mirror), plaw.py (the
             PLAW bulk-data parser and loader), plaw_poll.py (its poller), __main__.py
storage/     repository.py (the Repository protocol), postgres.py (the only SQL),
             identifiers.py (parsing served identifiers), session.py
api/         routes.py (enacted view, stat pages, labels, status, laws), comps.py
             (the compiled view, /comps), cited_by.py, cite.py (GET /cite),
             currency.py (currency.amended from the indexes), alternatives.py,
             schemas, responses
db/          SQLAlchemy models and Alembic migrations (db/migrations)
params.py    served_note, not_found, cache_control, ETag, rate limits, Accept, the cite wording
citation.py  the /us/… redirector
citeparse.py the citation parser (pure; tests/test_citeparse.py is its accepted-forms table)
uslmtext.py  reading text and fragment extraction from stored USLM
frontend/    the reader: src/pages (the routes), src/lib (api, types, url, refs, uslm), src/components,
             tests (vitest), tests/e2e (Playwright, axe)
deploy/      Caddyfile, the box scripts (provision, bootstrap, deploy-on-box, update-sources,
             watchdog, alarms, install-crons, admin-grant), edge/ (the shared proxy)
docs/adr     decisions that depart from the design
docs/verification  per-volume load reports, the citation index and mirror counts
```
