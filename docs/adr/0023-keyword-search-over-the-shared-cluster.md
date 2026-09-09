# ADR-0023: Keyword search over the shared cluster

Date: 2026-09-09. Status: accepted. Implements
`docs/plans/2026-09-09-reader-improvements-plan.md`, package E (E1 to E3).
Follows the US Code site's ADR-0028, 0031, 0049 and 0051; the mapping,
fingerprint and rebuild in `ingest/search_sync.py` and the query builder in
`storage/searchquery.py` predate this ADR and are covered by it retroactively.

## Context

Nothing in this site answers "which sections mention wild horses"; every
route needs a citation already in hand. The corpus is small next to the US
Code site's — a few million units, not tens of millions of section versions —
and the box has no memory for a second OpenSearch JVM: the US Code site's
cluster already runs at a 2 GB heap beside about 5 GB of that site and 1.3 GB
of this one on an 8 GB `t4g.large`.

## Decisions

1. **One document per unit that carries text or a heading, in one index
   behind an alias.** A section is indexed with its text; a hierarchy node
   (division, title, chapter, …) with its heading and no text. A `<section>`
   inside `quotedContent` is not a unit (gotcha 5) and is not indexed on its
   own — its text stays inside the enclosing section's document. Every
   compiled section of every compilation's current version is a second
   document, `view: compiled`; `view: all` filters neither, so an enacted and
   a compiled section of the same law are two answers, never collapsed into
   one.

2. **The production cluster is the US Code site's, shared.** This site's
   `api` container joins the US Code compose project's default network,
   `uscode-redesign_default`, as an external network in
   `docker-compose.prod.yml`, and reaches the cluster at
   `SEARCH_URL=https://opensearch:9200`. Nothing in `../uscode-redesign`
   changes. The dev stack runs its own single-node cluster
   (`docker-compose.yml`, `opensearch`), published on host port 9201 — 9200 on
   this machine is the US Code site's dev cluster. `SEARCH_VERIFY_CERTS=false`
   on both stacks: the OpenSearch image's self-signed certificate cannot be
   verified.

3. **`law:` filters the whole identifier, normalised from a bare law
   number.** `law:117-328` becomes `law_identifier: /us/pl/117/328`; a private
   law or a chapter-era act is filtered by writing its identifier out
   (`law:/us/pvtl/81/375`, `law:/us/act/1890-07-02/ch647`) — one scope word
   answers for every kind, and the bare number form is public-law-only
   because that is the form a reader writes.

4. **An enacted document's `_id` is its identifier; a second occurrence is
   distinguished.** `units.occurrence` numbering two units alike under one
   identifier is the only way one identifier is two documents
   (`/us/pl/81/740/s3~2`); a rebuild otherwise overwrites by `_id` rather than
   duplicating. A compiled document's `_id` carries its package
   (`{identifier}@{package_id}`): several COMPS files share one identifier
   prefix (gotcha 8 — the Social Security Act has a file per title), and the
   package is what tells their documents apart.

5. **`citation_sort` orders the Statutes at Large as printed**: the volume
   zero-padded, then the page (its letter prefix kept, lower case per gotcha
   6, its number padded), then `seq` — a unit's position within its law. A
   document with no volume (a compilation matched to no loaded law) carries no
   `citation_sort` and sorts last under `?sort=citation`.

6. **Matching is strict** (the US Code site's ADR-0031): `simple_query_string`
   with `default_operator: and` and no `fuzziness`. A phrase match on `text`
   and on `heading` is a `should` clause, never a `must`, so it reorders
   results and never removes one. The scope words (`law:`, `congress:`,
   `year:`, `vol:`, `kind:`, `view:`, `heading:`) are lifted out of the query
   string before it reaches `simple_query_string`, which has no notion of a
   field and throws on syntax it does not parse.

7. **The mapping carries a fingerprint; a rebuild is a deploy step, not a
   runbook line** (the US Code site's ADR-0051, adopted here in full). The
   mapping is not additive — OpenSearch will not add a field type to a live
   index — so a field the code queries and the index lacks is absent rather
   than broken: `congress:117` matches nothing, which reads exactly like a
   congress with nothing in it. `mapping_fingerprint()` is stamped into the
   index's `_meta`; `alias_is_current` compares it against what the code
   declares; `reindex-search --if-changed` rebuilds only when they differ,
   building beside the live alias and moving it in one `update_aliases` call.
   A failure part-way leaves the alias where it was.

8. **`resync_since` adds and replaces; it does not delete.** It re-syncs the
   laws whose `laws.loaded_at`, and the compilation versions whose
   `fetched_at`, are at or after a date, writing through the live alias. A
   document whose unit no longer exists in Postgres is not removed —
   `--recreate` is what drops those, by rebuilding from nothing.

9. **`DISABLE_SEARCH_SYNC=1` keeps `make test` and every load cluster-free.**
   `ingest/reindex_search.py` is the only thing in `ingest/` that reaches a
   cluster; `sync()` and `rebuild()` no-op under the flag rather than raising,
   so a load or a test run that sets it needs no cluster at all.

10. **The route is rate-limited at 120, 10 a second** (`params.rate_limit`),
    sized as a server's budget the way `labels` is, not a person's: a page
    that lists a search box calls `/api/v1/search` once per request it
    renders. A cluster exception is logged (`log.exception`) and answered 503
    with `search is unavailable; try again shortly` — the exception itself
    goes to the log, not to the caller, because an opensearch-py error
    stringifies to the cluster's internal hostname and port. `MAX_OFFSET =
    1000`: past `max_result_window` (10,000 by default) the cluster throws,
    so an unbounded offset is a 500 from a query string.

## The reader

Not in this ADR: `/app/search`, `/app/search/syntax`, and the `/app/goto`
fallback for a query that is not a citation are package E4, added by a later
session appending to this ADR.

## Consequences

- Deploys that change the mapping take longer on the box (a rebuild of the
  live corpus, which is small next to the US Code site's); deploys that do
  not are two HEAD requests, wrapped in `|| echo` so a rebuild failure never
  fails a deploy (`deploy/deploy-on-box.sh`).
- `deploy/update-sources.sh` runs `reindex-search --if-changed` then
  `reindex-search --since <the day before the run started>` after the
  classification step and before the dump, in `auto` and `force` modes.
- `SEARCH_PASSWORD` is the US Code site's OpenSearch admin password, typed
  into this site's `.env` by hand rather than generated here — this site does
  not own the cluster and cannot rotate its credential.
- A gap of one round trip exists only on the migration from a concrete index
  named for the alias to the alias itself, which this site has never had
  (its index has never existed under any name but the alias); every rebuild
  here is gapless from the first one.
