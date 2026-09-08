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

Stage 2 (in progress): the `COMPS` poller, `comp_versions`, `/us/sComp/…`, the
compiled view, and `alternatives` between the two views.

## Not yet served

- `PLAW` packages (the 104th Congress onward) as a separate source; those laws
  come from the volume USLM until design stage 4.
- Concurrent resolutions, proclamations, treaties, and agreements printed in
  the volumes. They are counted in the load report and skipped.
- `citations`, `cited-by`, `amended.status` from evidence (design stage 3):
  `currency.amended.status` is `unknown`.
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
```

`make test` needs no database and no network: the suite loads verbatim slices
of the source files (`tests/fixtures/`) into SQLite. `make test-slow` parses
the downloaded volumes under `data/statute/xmls`.

## Layout

```
ingest/      statute.py (volume USLM → laws and units), identifiers.py (the rules),
             numbering.py (law-number collisions), load.py, hub.py, __main__.py
storage/     repository.py (the Repository protocol), postgres.py (the only SQL),
             identifiers.py (parsing served identifiers), session.py
api/         /api/v1 routes and response models
db/          SQLAlchemy models and Alembic migrations (db/migrations)
params.py    served_note, not_found, cache_control, ETag, rate limits, Accept
citation.py  the /us/… redirector
uslmtext.py  reading text and fragment extraction from stored USLM
docs/adr     decisions that depart from the design
docs/verification  per-volume load reports
```
