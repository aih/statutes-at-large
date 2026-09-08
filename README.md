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
| `/us/stat/{volume}/{page}` | every law that starts on or spans the page, with the unit the page marker falls in |

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
| `GET /us/stat/{volume}/{page}` | `{page, identifier, volume, documents: [{identifier, kind, title, label, citation, enacted, starts_here, unit_on_page}], pdf}` |
| `POST /labels` `{"identifiers": […]}`, `GET /labels?identifier=…` | per identifier: `{exists: true, served_identifier, resolution, num, heading, level, kind, law_identifier, law_label, currency}` or `{exists: false}`; 1 to 100 per request; 300 requests then 30 per second per address |
| `GET /status` | `{collections: {STATUTE, COMPS, PLAW}, checks: {…}, stale}` |
| `GET /laws/{c}/{n}` | `{law, toc, section_count, compilations}` |
| `GET /laws/{c}/{n}/sections/{num}` | the section by number, ignoring hierarchy; same body as the identifier routes |

Query parameters on the identifier routes: `view=enacted` (default) or
`view=compiled` (a 404 with `alternatives` until stage 2 loads compilations),
`format=json` or `format=xml` (otherwise `Accept:`; XML is the stamped USLM
element, the provision alone when the path went below a section), `through`
(a compilation version; ignored on the enacted view).

Headers on a unit: `ETag` (the content hash; a found provision appends a hash
of its identifier), `Cache-Control: public, max-age=31536000, immutable`,
`Vary: Accept`, `X-Served-Identifier`. `If-None-Match` answers 304. A stat page
is immutable with an `ETag` over its documents. `labels`, `status`, and the law
summary are `public, max-age=300`. `HEAD` is not registered and answers 405.

`currency.amended.status` is `unknown` on every enacted unit in stage 1, and the
note's amended sentence is "Whether this section has been amended since is not
recorded here."

Source: GovInfo `STATUTE` volume USLM from the Hub dataset
`dreamproit/us-statutes-at-large` (`xmls/STATUTE-{n}.xml`). The volume files
carry no identifiers; the loader assigns them by the rules in the OCR plan,
section 7 (`ingest/identifiers.py`, version `rules-1.0`), and stamps them into
the stored XML. `provenance` on every response records `gpo-uslm` text and
`rules-1.0` identifiers.

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
Loaded so far: COMPS-1630 (Atomic Energy Act of 1954), COMPS-973 (Federal
Food, Drug, and Cosmetic Act), COMPS-3055 (Sherman Act), COMPS-8755 (Social
Security Act, title II), and two packages a poll since 2026-09-04 found.

Stage 3 (the indexes):

| Route | Answer |
|---|---|
| `GET /api/v1/cited-by?identifier=/us/pl/104/333/s814` | the US Code sections whose source credits, notes, or text cite the law, the section (by number, whatever hierarchy the ref wrote), a path below it, or a Statutes at Large page; `context` (`sourceCredit`, `note`, `text`, repeatable), `limit` (1–200), `offset`; `law` is null when the law is not loaded; 404 when the index holds nothing for an unloaded law; ETag and `If-None-Match`; `max-age=300`; 60 requests then 2 per second |

Sources: the citation index is built from the `dreamproit/uscode` dataset's
`current` config (`python -m ingest citations --from-hub`, ADR-0008); the
classification tables are mirrored from the US Code site's API
(`python -m ingest classifications`, one `classification_files` row per
table, replaced wholesale when its rows change).

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

- `PLAW` packages (the 104th Congress onward) as a separate source; those laws
  come from the volume USLM until design stage 4.
- Concurrent resolutions, proclamations, treaties, and agreements printed in
  the volumes. They are counted in the load report and skipped.
- `amended.status` from evidence (design stage 3): `currency.amended.status`
  is `unknown`.
- The reader at `/app` and the citation parser (design stage 5). The citation
  URL already redirects browsers there.
- The reprocessed OCR text (design stage 6). The text is GPO's digitization
  vendor's, errors included.

## Running it

```
cp .env.example .env            # DATABASE_URL, GOVINFO_API_KEY
make dev-up                      # Postgres on :5434
make migrate                     # alembic upgrade head
make dev-data                    # volumes 64 and 124 from the Hub, with reports
make dev                         # the API on :8001
make test                        # pytest over SQLite and the committed slices
make up                          # docker compose: Postgres, API, Caddy on :8010
python -m ingest comps load COMPS-1630 COMPS-3055   # fetch and load packages
python -m ingest comps poll --since 2026-09-01      # walk the collection
python -m ingest comps report
python -m ingest citations --from-hub --report docs/verification    # the citation index
python -m ingest classifications --report docs/verification         # the classification tables
```

`make test` needs no database and no network: the suite loads verbatim slices
of the source files (`tests/fixtures/`) into SQLite. `make test-slow` parses
the downloaded volumes under `data/statute/xmls`.

## Layout

```
ingest/      statute.py (volume USLM → laws and units), identifiers.py (the rules),
             numbering.py (law-number collisions), load.py, hub.py, comps.py (the
             COMPS parser, loader and poller), govinfo.py (the API client), __main__.py
storage/     repository.py (the Repository protocol), postgres.py (the only SQL),
             identifiers.py (parsing served identifiers), session.py
api/         routes.py (enacted view, stat pages, labels, status, laws), comps.py
             (the compiled view, /comps), alternatives.py, schemas, responses
db/          SQLAlchemy models and Alembic migrations (db/migrations)
params.py    served_note, not_found, cache_control, ETag, rate limits, Accept
citation.py  the /us/… redirector
uslmtext.py  reading text and fragment extraction from stored USLM
docs/adr     decisions that depart from the design
docs/verification  per-volume load reports
```
