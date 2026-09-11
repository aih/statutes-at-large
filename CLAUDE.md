# CLAUDE.md — statutes-linkedlegislation

Statutes at Large and Statute Compilations served at the section level by the
identifiers the US Code cites. Design in
`../statute-pdf-to-xml/docs/plans/2026-09-07-statutes-api-design.md`; conventions
copied from `../uscode-redesign` (its CLAUDE.md is the fuller reference).

## Architecture rules

1. **`api/` talks only to the `Repository`** (`storage/repository.py`). SQL lives in
   `storage/postgres.py` and in `ingest/`, nowhere else. `api/` holds no database
   session; `storage.get_repository` is the FastAPI dependency.
   `tests/test_architecture.py` enforces it.
2. **Sections are the storage atom** (ADR-0001). Levels below a section are stamped
   with identifiers and travel inside the section's XML; a request for
   `/us/pl/81/740/s3/1` returns section 3 with paragraph (1) cut out as `provision`.
   Hierarchy nodes (division, title, chapter, …) are `units` rows without XML.
3. **Identifiers are assigned by rule** (`ingest/identifiers.py`, `rules-1.0`; OCR
   plan section 7). The volume USLM carries none. Stored XML is GPO's text with
   `identifier` attributes added; `provenance` says so on every response.
4. **Every law answers to every alias** (`law_aliases`, ADR-0002). Laws from 1901 to
   1957 have a law number and a chapter; the law number is the primary form.
5. **Shared HTTP helpers live in `params.py`**: `served_note`, `not_found`,
   `cache_control`, `if_none_match`, `rate_limit`, `negotiated_format`, the
   `cite` wording. `api/` and `citation.py` import it and never each other.
   `citeparse.py` (the citation parser) is pure and imports none of them; the
   reader in `frontend/` reads `/api/v1` only and prints the API's sentences
   verbatim (`docs/plans/2026-09-08-reader-contract.md`).
6. The GovInfo key is `GOVINFO_API_KEY` in the environment or in `.env` (gitignored),
   never in source.

## Gotchas

1. **Law components nest inside `component role="statutesPart"`.** A law is a
   role-less `component` whose first child is `pLaw`. `resolution` and
   `presidentialDoc` roots are concurrent resolutions and proclamations; skipped.
2. **The law number of a chapter-era law is in a marginal note**, as text
   (`[Public Law 443]`, OCR variants `Private law`, `Private Lavr`) and as
   `ref/@href` in two shapes: `/us/pl/81/443` and the vendor's `/us/bill/81/pl/500`.
   Read the `sidenote` inside `longTitle` only: the official title often names
   *another* law ("To extend the Rubber Act of 1948 (Public Law 469…)").
3. **Law numbers collide inside a volume** (46 of 481 public laws in vol 64). The
   number that sits between its neighbours in sequence wins; the other claimant is
   stored under its chapter form (`ingest/numbering.py`, ADR-0003). After 1957 there
   is no chapter form and the loser is dropped and reported.
4. **The first section of an act is unnumbered** ("That the Secretary …") and cited
   as section 1. 1,219 of 3,063 sections in vol 64. A later section without a number
   is not addressable and is left inside its neighbour's context.
5. **`<section>` inside `quotedContent` is not a section of this law** (358 in vol
   64, 591 in vol 124). Skipped as units, kept in the enclosing section's XML.
6. **Page labels are lower case**: `/us/stat/64/B3` in one volume, `b3` in another,
   `A12` in the private-law part. Everything is stored and matched as `a12`.
7. **`num/@value` is usually present; the text is the fallback.** `Sec. 12.` → `12`,
   `TITLE I—` → `I`, `(a)` → `a`. The COMPS write `ch1.` with the period in the
   identifier; that is GPO's form and is kept as is on `/us/sComp/…`.
8. **`/us/sComp/{c}/{n}`'s second number is a chapter before 1901** (`/us/sComp/51/647`
   is the Sherman Act, ch. 647). Several COMPS files share one prefix (the Social
   Security Act has one file per title); the section identifiers disambiguate.
   A prefix with no whole-act file answers its bare form with the per-title
   files gathered in title order (ADR-0007, decision 8); the Public Health
   Service Act's titles are under `/us/sComp/78/373`, its chapter number.
9. **The Hub's `STATUTE-137.xml` holds 34 public laws** (12 MB). The loader loads
   what the file holds.
11. **One `component` can hold many `pLaw` elements** (vol 116 packs 47 consecutive
    laws into one). Every `pLaw` is a law; `merged_components` counts them.
12. **The first volumes print chapter numbers in Roman numerals** (`docNumber` `I`,
    `CXLVII`); `parse_doc_number` reads both.
10. **Host ports are 5434 and 8010.** 5432, 5433 and 8000 belong to sibling
    projects on the same machine. The dev compose project is named
    `statutes-linkedlegislation` in `docker-compose.yml`, so every checkout and
    worktree shares one `db` and one `opensearch`; the box's is
    `statutes-at-large` (ADR-0025).
13. **The proxy trusts only the edge subnet.** `deploy/Caddyfile` has
    `trusted_proxies static 10.83.0.0/24` and `header_up X-Forwarded-For
    {client_ip}`; the `edge` network is created with that subnet by
    `deploy/edge/up.sh`. A workstation's forged header is dropped on the dev
    stack; the edge's forwarded address survives on the box (ADR-0017). The
    reader forwards `Astro.clientAddress` on every API call, so `cite` and
    `cited-by` are limited per reader.
14. **The production search cluster is the US Code site's**, reached through
    `search-relay` (ADR-0023, ADR-0024); this site runs no OpenSearch container
    of its own on the box. That relay is the only service of this project on
    the external network `uscode-redesign_default`: Docker registers a service
    name as a DNS alias on every network its container joins, so a service
    named `db`, `opensearch`, `redis`, `api`, `frontend` or `proxy` would
    answer there for the US Code site's own. `SEARCH_PASSWORD` is the cluster's
    admin password, typed into this site's `.env` on the box by the user, never
    generated or rotated here.

## Fixtures

Verbatim slices, regenerated by `make fixtures`:

- `tests/fixtures/statute-64-slice.xml` — 10 laws of 1950: an unnumbered single
  section, a private law on page A12, the Rubber Act extension (number in the
  title), the vendor href form, a law with titles (ch. 1212), a quoted section.
- `statute-72-slice.xml` — 6 laws of 1958, the first year without chapters.
- `statute-124-slice.xml` — 4 laws of 2010 with titles and subtitles, one private.
- `statute-137-slice.xml` — 3 laws of 2023: 118-3 (one section), 118-22 (divisions
  and subtitles), 118-34 (titles).
- `statute-116-slice.xml` — one component holding three laws (2002).
- `statute-26-slice.xml` — the Sherman Act (1890, chapter only); `statute-68-slice.xml`
  — the Atomic Energy Act of 1954 (Public Law 83-703, chapter 1073 in the preface).
  Both have compilations among the COMPS fixtures, so the two views meet in tests.
- `tests/fixtures/comps/` — COMPS-3055 whole (Sherman Act), slices of COMPS-1630
  (Atomic Energy Act), COMPS-973 (FD&C Act), COMPS-8755 (Social Security Act
  title II), and their GovInfo summaries.
- `tests/fixtures/plaw/` — whole GovInfo bulk-data files: `PLAW-118publ1.xml` (one
  unnumbered section, no identifiers), `PLAW-118publ22.xml` and `PLAW-118publ34.xml`
  (both also in the 137 slice, so the two sources meet), `PLAW-119publ1.xml`, and the
  bulk listings as JSON (its README has the URLs). Loaded after the volume slices, so
  118-22 and 118-34 are PLAW-derived in the test database and 118-3 stays
  volume-derived.
- `tests/fixtures/uscode-current-slice.parquet` — 57 rows of the `dreamproit/uscode`
  `current` config (`scripts/extract_citations_fixture.py`): the US Code sections
  whose source credits cite the laws above, plus 16 U.S.C. §§ 1 and 45f.
- `tests/fixtures/classifications/` — the US Code site's tables listing and the
  first 40 rows of tables 118-2 and 104, verbatim JSON (its README has the URLs).

Known-good: `/us/pl/81/740/s3` is 64 Stat. 563–564, and `/us/act/1950-08-30/ch823/s3`
is the same section.

## Commands

```
make dev-up / migrate / dev      Postgres on :5434, alembic, uvicorn on :8001 and the reader on :4321
make dev-web / test-web / test-e2e   the reader alone; vitest; Playwright and axe over BASE_URL
make cite Q="Pub. L. 81-740, § 3"    the parser, then GET /api/v1/cite on the running site
make dev-data                    load volumes 64 and 124 with reports
make load-all                    all 137 volumes (resumable per volume)
make test / test-slow / test-all pytest over SQLite; the slow set parses whole volumes
make fixtures                    regenerate the committed slices
make up                          the compose stack with Caddy on :8010
python -m ingest statute PATH… --report docs/verification
python -m ingest fetch-statute 64 72 [--if-changed]   the Hub tree listing against the files on disk
python -m ingest statute --volumes 1-137 --changed-only   files that differ from their last load
python -m ingest comps poll [--since YYYY-MM-DD] [--limit N] [--force]
python -m ingest comps load COMPS-1630 …   |   comps load-file PATH [--summary PATH]
python -m ingest comps report [--list]
python -m ingest citations --from-hub [--if-changed] | --from-dir data/uscode [--report docs/verification]
python -m ingest classifications [--congress N] [--from-dir PATH] [--force] [--report DIR]
make citations / classifications     the two above, into the dev Postgres
python -m ingest plaw fetch 113-119              the per-congress bulk-data zips into data/plaw
python -m ingest plaw load 118 … [--from-dir PATH] [--report DIR]   public laws from the zips
python -m ingest plaw poll [--congress N] [--since YYYY-MM-DD] [--force] [--from-dir PATH]
make fetch-plaw / plaw / plaw-poll   the three above, congresses 113 to 119
python -m ingest reindex-search [--if-changed] [--since YYYY-MM-DD] [--recreate]   the OpenSearch index (ADR-0023)
make reindex-search              reindex-search --if-changed against the dev cluster
make load-prod / update-prod / update-prod-check   on the box: the first load; the weekly update; the checks only
bash deploy/deploy-on-box.sh <sha> / deploy/edge/up.sh   the deploy; the shared edge (plan sections 4 to 7)
bash deploy/deploy-gate.sh <sha> [health-url]   deploy=true|false: false for docs only since /health's commit
```

Sources have a precedence (ADR-0011): a PLAW load replaces the volume-derived
copy of the same law; a volume load leaves a PLAW-derived law alone and lists
it under `laws_kept_from_plaw`. Private laws and laws before the 113th
Congress stay volume-derived.

The GovInfo client (`ingest/govinfo.py`) puts the key in the query string,
strips it from error messages, redacts it in the httpx log line, and never
prints a URL that carries it.

## Branches and pull requests

Work is done on a branch cut from `origin/main`, pushed, and opened as a pull
request against `main` with `gh pr create`. The user merges it. Nothing is
pushed to `main` directly; a merge to `main` deploys (`deploy.yml`).

## Documentation duties

An ADR in `docs/adr/` for every decision that departs from the design (0001
storage atom, 0002 aliases, 0003 number collisions, 0004 SQLite tests, 0005
what a load keeps, 0006 restated acts, 0007 compilations, 0008 the citation
index, 0009 the classification mirror, 0010 `currency.amended`, 0011 PLAW outranks
the volume file, 0012 what stays volume-derived, 0013 GPO's identifiers and
rules-1.0, 0014 the reader, 0015 the citation parser, 0016 cross-site links,
0017 two sites one edge, 0018 the weekly update, 0019 a law answer carries no text
and its XML is deferred, 0020 a printed page is served as the slice between its
markers, 0021 the reader's chrome, 0022 one keyboard map, 0023 keyword search
over the shared cluster, 0024 a relay to the shared cluster and a quieter site-down
alarm, 0025 search settings from `.env` and fixed compose project names,
0026 a deploy skips a documentation-only change). A BUILDLOG entry per session. Verification counts in `docs/verification/`
are regenerated by the loader, not edited. Prose follows `~/.claude/CLAUDE.md`.
