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

Source: GovInfo `STATUTE` volume USLM from the Hub dataset
`dreamproit/us-statutes-at-large` (`xmls/STATUTE-{n}.xml`). The volume files
carry no identifiers; the loader assigns them by the rules in the OCR plan,
section 7 (`ingest/identifiers.py`, version `rules-1.0`), and stamps them into
the stored XML. `provenance` on every response records `gpo-uslm` text and
`rules-1.0` identifiers.

Loaded and verified so far: volumes 64 and 124 (`docs/verification/`). The
loader handles all 137 volumes (`make load-all`).

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
