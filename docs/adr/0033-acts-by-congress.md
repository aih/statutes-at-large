# ADR-0033: Acts by Congress

Date: 2026-10-19. Status: accepted.

## Context

Issue #19 asks for the laws of every Congress from the 1st to the 119th, with
public and private counts before 1901, and each law's compilation, US Code
citations and classification table.

Before the 57th Congress every law is a chapter act (`kind` `act`), and the
loaders did not keep the source's `meta/publicPrivate`. A volume's
`meta/congress` names the wrong Congress for 450 of the 2,101 laws in volume
26 (tagged 52; approved between March 1890 and March 1891, in the 51st) and
518 of the 3,145 in volume 6.

## Decision

1. `laws.public_private` holds `public` or `private` from each law's
   `meta/publicPrivate`; a PLAW package's is its kind.
2. A chapter act's `congress` is the Congress sitting on its approval date
   (`ingest.identifiers.congress_of_act`): a term began on March 4 of an odd
   year until 1935 and on January 3 since. `meta/congress` is kept when the
   act has no date, and on the March 4 a term ended when it names the
   outgoing Congress. A law whose congress is changed carries the warning
   `congress taken from the approval date, not meta/congress`.
3. Migration `e4a1c9d27b63` adds the column, fills it from the stored XML, and
   applies 2 to the acts already loaded. `tests/test_migration_act_congress.py`
   checks its SQL against `congress_of_act` on a throwaway Postgres.
4. `GET /api/v1/congress` lists every Congress from the 1st to the latest
   with a loaded or a pending law. `GET /api/v1/congress/{congress}` answers
   for each of them, and 404 past the latest.
5. Every count is of loaded laws and equals the total of its filter on the
   detail route: `public_private` (`public`: public laws and public acts;
   `private`: private laws and private acts), `kind`, `has_comp`, `cited`
   (the citation index), `classified` (the OLRC tables). `compilations_count`
   counts compilation files, loaded laws or not.
6. Each index is matched as the rest of the API matches it:
   - a compilation to `Comp.law_id`, else the law `_law_by_congress_number`
     finds (the `/us/pl/{c}/{n}` alias, else the act with that chapter);
   - a classification row to the public law with its congress and number;
   - a citation to the law through its aliases, counted once per law and
     once per citing section, as the law page's cited-by panel counts it.
7. A law's table link is the US Code site's
   `/app/classification/{congress}/{session}?pl={n}` for the session whose
   table lists it; session 0, the 104th's whole-congress table, is `all`.
8. A law's `url`, `stat_url` and compilation `url`s are citation URLs.
   `volume_starts` gives, per volume, the lowest numeric first page of the
   Congress's laws in it.
9. `/app/congress` shows the totals, a chart of laws per Congress (public,
   private, and acts marked neither) and a table of every Congress. The
   chart is hidden from assistive technology; the table holds the same
   counts and links. `/app/congress/{congress}` shows the Congress's facts,
   its pending laws, the filters with their totals, the three sorts, a word
   filter, and one page of 100 laws.

## Consequences

`ingest statute` changes the congress of laws in volumes 1 to 31 on the next
load, and the migration changes it for laws already loaded. The search index
keeps the congress each law had when it was indexed until
`python -m ingest reindex-search` rebuilds it; `--if-changed` does not see
the change.

A `/us/sComp/{c}/{n}` prefix of a chapter act now finds an act whose
`meta/congress` was wrong.

The overview reads every `units` row of level `section` and every citation
row with a law target on each request; the route's `max-age` is 300 seconds.
