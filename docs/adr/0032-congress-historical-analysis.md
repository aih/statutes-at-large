# ADR-0032: Historical data analysis of Acts by Congress

Date: 2026-10-19. Status: accepted.

## Context

GitHub Issue #19: Readers and researchers need an index and historical overview
of Acts by Congress from the 1st to the 119th Congress, with cross-references to
the US Code site (`uscode.linkedlegislation.org`) and the Statutes at Large site
(`statutes.linkedlegislation.org`).

Prior to this change, the reader and API provided lookup of laws by individual
citation (volume and page, public law number, private law number, or chapter),
but lacked an overview of legislative volume across Congresses, a per-Congress
catalog of enacted laws, and aggregate cross-references to US Code classifications
and citations.

## Decision

1. Pure Congress metadata helpers live in `storage/identifiers.py`:
   - `congress_ordinal(c)` produces ordinals ("1st", "2nd", "119th").
   - `congress_years(c)` computes the two-year span starting at 1789.
   - `congress_of_date(enacted)` calculates the Congress number for any enactment date.
2. Index `ix_citations_to_congress` on `citations.to_congress` (migration
   `d8e3c7b1a209_ix_citations_to_congress.py`) accelerates per-Congress citation counts.
3. Storage protocol and dataclasses in `storage/repository.py` and implementation in `storage/postgres.py`:
   - `CongressSummary`, `CongressesOverview`, `CongressLawComp`, `CongressLawItem`, `CongressDetail`.
   - `Repository.congresses_overview()` computes summary statistics for Congresses 1 through 119:
     volumes covered, public/private/act law counts, total laws, total sections, and whether loaded.
   - `Repository.congress_detail()` retrieves summary statistics, pending laws from `pending_laws`,
     and paginated laws filtered by kind, compilation presence, citation presence, and text query,
     sorted by sequence, enactment date, or section count. Section counts, compilations, citations,
     and classification sessions are batch-fetched to avoid N+1 queries.
4. API endpoints in `api/congress.py` (mounted at `/api/v1/congress`):
   - `GET /api/v1/congress` returns `CongressesOverviewOut`.
   - `GET /api/v1/congress/{congress}` returns `CongressDetailOut`.
   - Wording helpers `congresses_note` and `congress_note` reside in `params.py`.
   - Absolute URLs to `uscode.linkedlegislation.org` and `statutes.linkedlegislation.org` use `OriginsSettings`.
5. Frontend reader routes:
   - `/app/congress` (`frontend/src/pages/congress/index.astro`): summary facts `<dl>`,
     pure SVG bar chart timeline linking to each Congress, and master table of all 119 Congresses.
   - `/app/congress/[congress]` (`frontend/src/pages/congress/[congress].astro`): Congress facts,
     pending laws callout, filter pills (`kind`, `has_comp`, `cited`), sort pills (`sequence`, `date`, `sections`),
     search input, paginated laws table with cross-links to statute text, compilations, and US Code
     classifications and citations, and `KeyboardNav`.
   - Header navigation in `SiteHeader.astro` and home page links in `index.astro` include Congresses.
6. Per-route JavaScript byte budget in `docs/js-budgets.json`:
   - `/app/congress` set to 3500 bytes (3139 bytes measured).

## Consequences

Congresses without loaded laws appear in the overview and detail views with zero counts
and are marked as not loaded. The overview covers all 119 Congresses up to the present.
Indexed lookups on `citations.to_congress` keep detail aggregation fast.
