# ADR-0009: The classification tables are mirrored through the US Code site's API

Date: 2026-09-08. Status: accepted. Implements design section 6
(`classifications`: "mirror of the US Code site's classification rows").

## Context

OLRC publishes one classification table per session as fixed-width text in
`<PRE>` (31 files, 1996 onward). The US Code site scrapes them, derives
`usc_identifier` with the en-dash fold and the appendix and range rules of its
ADR-0067, and serves the rows at
`/api/v1/classifications/tables/{congress}/{session}/entries` (rate limited,
no key). Scraping the files again here would mean a second parser for the
same 28 unmeasured vintages and a second copy of the identifier rules.

## Decisions

1. **The rows come from the site's API, not from uscode.house.gov.** The
   listing (`/classifications/tables`) names the documents; each `pl` file is
   paged at 500 rows per request, sequentially, at most ten requests a
   second, with a descriptive `User-Agent`. ECCT files are listed and skipped.
   The 104th Congress's whole-congress table is session `0`.

2. **Columns mirror the site's entry shape**, one table per file
   (`classification_files`) and one row per entry (`classifications`), keyed
   `(file, row_seq)` and indexed by `(pl_congress, pl_num, pl_section_num)`
   and `usc_identifier`. `pl_section_num` is the section designator of
   `pl_section_raw` (`101(3)` → `101`, `''` → null), in the form
   `units.section_num` uses, so a classification row joins a stored section.

3. **A file is replaced wholesale, in one transaction.** The site's ADR-0067
   decision 3 applies unchanged: the rows have no identity. A file is skipped
   without paging when the listing's `fetched_at`, `row_count` and
   `covered_laws_text` match the stored file; a paged file whose row hash
   matches is not rewritten.

4. **A check row per run**, in `classification_source_checks`, on success and
   on failure, with the site's own `last_checked_at` and covered-law sentence.
   Separate from `source_checks` so `/status`'s answer about the source
   collections does not flap (the site's ADR-0067 decision 4).

5. **`--from-dir` reads saved JSON pages**, which is how the tests run: the
   listing and the first page of two tables, fetched once from the live API
   and committed verbatim.

## Consequences

- The mirror is as current as the site's own scrape; `/status` reports both
  the mirror's check and the site's.
- A row is evidence for `currency.amended` (ADR-0010) in two directions:
  what this law's section did to the Code, and what later laws did to the
  same Code sections.
- If the site changes its entry shape, the mirror's loader is the one place
  that reads it.
