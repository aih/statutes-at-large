# ADR-0034: The lettered volumes 68A and 70A

Date: 2026-10-20. Status: accepted.

## Context

Volume 68A of the Statutes at Large prints the Internal Revenue Code of 1954
(Act of August 16, 1954, ch. 736). Volume 70A prints titles 10 and 32 of the
United States Code as enacted by the Act of August 10, 1956, ch. 1041. US Code
source credits cite both (`68A Stat. 483`, `/us/stat/70A/641`). The parser
and the identifier patterns took a volume as digits only, so
`parse_citation("68A Stat. 3")` returned None, `/api/v1/cite` answered 422,
and the citation index stored the hrefs as unparsed rows (issue #14).

Neither volume is in the Hub dataset `dreamproit/us-statutes-at-large`, and
GovInfo publishes no USLM or PDF package file for either. GovInfo's details
pages `https://www.govinfo.gov/app/details/STATUTE-68A` and `STATUTE-70A`
answer 200; its link service answers 400 for
`https://www.govinfo.gov/link/statute/68A/3`.

## Decision

1. `citeparse` reads `68A` and `70A`, in either case, as a volume. The
   identifier keeps the letter upper case (`/us/stat/68A/3`). `ParsedCitation`
   carries it in `lettered_volume`; `volume` is None for these pages. Any
   other lettered volume (`69A Stat. 3`) is not a citation.
2. `storage.identifiers.parse_lettered_page` parses `/us/stat/68A/{page}` and
   `/us/stat/70A/{page}`. `parse_stat_page` still answers None for them, so no
   caller looks up volume 68 for a page of 68A.
3. The citation loader stores a lettered page's ref as parsed, with
   `to_page` set, `to_volume` null and `to_identifier` in the canonical form.
   `cited_by` matches these rows by `to_kind = 'stat'` and `to_identifier`.
   No migration: `to_identifier` is already indexed.
4. `/api/v1/cite` answers a page of either volume with `exists: false` and a
   `message` (`params.lettered_volume_note`) that names what the volume prints
   and its GovInfo details page. A law cited with such a page and not loaded
   gets the same message when it has no pending-law message.
   `/api/v1/us/stat/68A/{page}` is a 404 with that sentence as its detail; a
   volume that is neither digits nor 68A or 70A is a 404, not a 422.
5. The reader links a ref to a page of either volume to GovInfo's details
   page for the volume.

## Consequences

Citation rows loaded before this change are marked unparsed, with `to_page`
null; `cited_by` finds them by `to_identifier` all the same. The next
`ingest citations` run rewrites them.

Hyphenated section numbers (`Pub. L. 94-579, § 204-1`, `§ 254b-2`), the
issue's second item, were already parsed before this change; the parser
tests cover them.
