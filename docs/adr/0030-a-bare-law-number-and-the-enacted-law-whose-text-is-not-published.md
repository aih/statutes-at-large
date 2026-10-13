# ADR-0030: A bare law number, and the enacted law whose text is not published

Date: 2026-10-13. Status: accepted.

## Context

The citation box read `PL 119-111` and turned `119-111` away as words, so the
search page answered it. A public law is enacted days or weeks before GPO
publishes its text in GovInfo's PLAW collection; until then `plaw poll` has
nothing to load, and `/app/us/pl/119/120` answered a bare 404 for a law that
exists.

## Decision

1. `citeparse` reads `{congress}-{number}`, with an optional tail as after
   `Pub. L.`, as a public law. The form is tried after every other form, so
   `64 Stat. 563-564` stays a Stat. page and `42 USC 2000e-2` a US Code
   section. A zero congress or number is not a citation.
2. `python -m ingest plaw pending` asks the Congress.gov API which bills
   became public laws (`GET https://api.congress.gov/v3/law/{c}/pub`, paged
   by 250) and writes a `pending_laws` row (migration `b7e2c4a91f05`) for each
   listed public law with no `laws` row or alias at its identifier. Each run
   replaces the congress's rows, so a law that has since been loaded drops
   out. The default congresses are the current one and the one before.
3. The key is `GOVINFO_API_KEY`: GovInfo and Congress.gov both take
   api.data.gov keys. The call goes through `GovInfoClient`, which keeps the
   key out of what is printed.
4. `Repository.pending_law(identifier)` returns the row. On an `exists: false`
   answer for a public law, `/api/v1/cite` adds `pending` (the bill as
   Congress.gov prints it, its title, its latest action date, the bill's page
   on www.congress.gov, and when Congress.gov was asked) and a `message`
   (`params.cite_pending`). The unit route's 404 is unchanged.
5. The reader prints the `message` in a warning on `/app/goto` and, after a
   404 on `/app/us/pl/…`, asks `/cite` for the identifier and prints the same
   warning under the 404. The Congress.gov URL in the sentence is a link.
6. The weekly update (`deploy/update-sources.sh`) runs `plaw pending` after
   `plaw poll`, in `auto` and `force` modes. `pending_laws` is not part of
   `/api/v1/status`, so a run that changes only these rows takes no dump.

## Consequences

A law enacted after the weekly run gets no warning until the next one; a
reader still sees the 404. `make plaw-pending` refreshes the rows by hand.

The Congress.gov response shape is taken from the API's documentation. The
session that wrote this could not reach api.congress.gov, and
`tests/fixtures/congress-gov/law-119-pub.json` is hand-written in that shape,
not a capture. The first run on the box is the check.
