# ADR-0016: Cross-site links follow the `labels` answer, in both directions

Date: 2026-09-08. Status: accepted. Implements design section 7 and the
reference rule of the reader (design section 1's third bullet); records
what was settled on the US Code site's branch `statutes-links` (not pushed).

## Context

The US Code site's reader (its ADR-0015, decision 3) links `/us/stat/{v}/{p}`
to govinfo, `/us/pl/{c}/{n}` to govinfo from the 104th Congress on, and
renders every other `/us/pl/`, `/us/pvtl/` and `/us/act/` reference as
text. Its `labels` call takes `/us/usc/` identifiers only. This site now
serves those identifiers and answers `POST /api/v1/labels` for them,
including a `/us/stat/{vol}/{page}` page (ADR-0015 here, consequence 2).
This site's own reader renders statutes text whose references point the
other way, at `/us/usc/…`.

## Decisions

1. **The US Code site asks this site once per page.**
   `fetchStatuteLabels` (its `frontend/src/lib/api.ts`) posts the page's
   `/us/pl/`, `/us/pvtl/`, `/us/act/` and `/us/stat/` hrefs
   (`citedStatuteIdentifiers`) to `${STATUTES_ORIGIN}/api/v1/labels`, at
   most 100 per request, capped at the site's existing `LABELS_MAX`
   (1,200). The answers are cached per process for five minutes, 10,000
   entries, `exists: false` included. An unset `STATUTES_ORIGIN` makes no
   request; a failed call (network, non-2xx, 429) returns nothing, logs
   once and caches nothing. The call is server-side and never touches the
   browser's Content-Security-Policy; no header changed.

2. **Its `resolveRef` gains four rows and keeps the old ones as fallback.**

   | `href` | `labels` answer | Link |
   |---|---|---|
   | `/us/pl/`, `/us/pvtl/`, `/us/act/`, `/us/stat/` | `exists: true` | `${STATUTES_ORIGIN}${href}`, the bare citation URL, which redirects a browser to this site's reader; hover text `law_label` then `§ num.` and `heading`, or `{volume} Stat. {page}.` and the first document's `label` for a page; `identifier: null` (no preview card) |
   | `/us/pl/{c}/{n}`, `c` ≥ 104 | `exists: false` or no answer | `https://www.govinfo.gov/link/plaw/{c}/public/{n}` |
   | `/us/stat/{v}/{p}` | `exists: false` or no answer | `https://www.govinfo.gov/link/statute/{v}/{p}` |
   | anything else | `exists: false` or no answer | plain text |

   The preview endpoint asks the same question, so a card's citations link
   where the page's do.

3. **The version timeline links each law to its enacted text.** With
   `STATUTES_ORIGIN` set, a `laws[]` chip is the citation linked to
   `${STATUTES_ORIGIN}/us/pl/{c}/{n}?view=enacted`, one `§ n` link per
   section designator to `…/us/pl/{c}/{n}/s{n}?view=enacted`, and a last
   link to the classification page whose text is the action words or the
   word `classification`. Unset, the chip is what it was.

4. **`pl_sections` on `VersionLawOut`** carries the classification rows'
   `pl_section_raw` values for that law and section, read at request time
   from `classification_entries` scoped by `identifier_variants` and the
   law pair: no column, no backfill, no foreign key (its ADR-0074,
   decision 6). `parseLawSection` in `lib/versions.ts` takes the designator
   (`101(3)` → `101`, `12A(b)` → `12A`; `''`, `title I`, `401-407` → null).

5. **This site's reader applies the same rule from the other side**
   (`frontend/src/lib/refs.ts` here): `/us/usc/…` links to
   `USCODE_ORIGIN{href}` with no hover text; `/us/pl/`, `/us/pvtl/`,
   `/us/act/` and `/us/stat/` hrefs are looked up in this site's own
   `labels` and link to `/app{href}` when they exist, to govinfo when they
   do not and govinfo has them, and are text otherwise. A failed labels
   call renders every reference as text.

## Consequences

- The design's third bullet (the "cited by" panel) is this site's reader's
  panel from `cited-by`, on a law and on a section (ADR-0014). The US Code
  site gains no panel in this stage.
- The US Code site's `make test` (869 passed, 2 skipped) and `make test-web`
  (517 passed) are green on the branch; 13 `astro check` errors pre-exist
  on its `main`. The branch waits for review; its guide chapter and ADR
  index (its documentation duty 6) are for the reviewer of that repository.
- Turning the links on in production is one environment variable on the
  US Code site's `frontend` service.
