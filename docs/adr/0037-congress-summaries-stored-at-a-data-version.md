# ADR-0037: The Congress summaries are stored at a data version that triggers move

Date: 2026-10-20. Status: accepted. Amends ADR-0033.

## Context

`/api/v1/congress` computed every Congress's counts on each request
(`_congress_summaries`): eleven aggregate queries over `laws`, `units`,
`citations`, `law_aliases`, `comps`, `classifications`,
`classification_files` and `pending_laws`. On the box it answered in 9.4 s
and `/app/congress` in 11.1 s. `/api/v1/congress/{n}` ran the same queries
for one Congress, then the law list; `/api/v1/congress/81` answered in 1.8 s.

Over the dev database (8,052 laws, 75,237 units, 1,081,463 citations) the
overview took 10.6 s cold: 6.1 s counting cited laws and citing sections per
Congress, 3.6 s counting sections, each a scan of the table's heap.

The counts change only when a load writes one of those tables: weekly, plus
the daily run for the current Congress (ADR-0036).

## Decision

1. A one-row table `data_version` (`version`, `changed_at`). A trigger on
   each of the eight tables moves it: in Postgres an `AFTER … FOR EACH
   STATEMENT` trigger on insert, update, delete and truncate, which bumps the
   row once per transaction (a transaction-local setting,
   `statutes.data_version_bumped`, marks the bump); in SQLite, for the test
   suite, a row trigger per operation. The bump commits or rolls back with
   the load. A statement that matches no rows also bumps it.
2. `congress_summaries` holds one row per Congress: the `CongressSummary` as
   JSON and the `(version, changed_at)` stamp it was computed at.
   `python -m ingest congress-summaries` reads the stamp, computes the
   summaries, and replaces the rows; it does nothing when the stored rows
   are at the current stamp (`--force` recomputes anyway). A load that
   commits during the computation leaves the rows behind the stamp.
3. `PostgresRepository.congress_summaries()` reads the stamp, then returns,
   in order: the set this process last read or computed at that stamp; the
   stored rows at that stamp; a set computed live. While one request
   computes, others in the process are served the set it held before. The
   overview and the detail route both take their summaries from it; the
   detail route's latest Congress is the number of summaries.
4. `update-sources.sh` runs `congress-summaries` after its loads in every
   mode but `--check-only`; `deploy-on-box.sh` runs it after the migration.
5. Two indexes for the live computation and the detail route's law rows:
   `ix_units_level_law` (`level`, `law_id`) and `ix_citations_to_law_from`
   (`to_law`, `from_identifier`, `from_title`), so the section and citation
   counts are index-only scans.

## Consequences

Over the dev database: the overview 6 ms from the stored rows, 1 ms to 2 ms
from memory, 0.4 s to 0.8 s computed live with the indexes;
`congress_detail(81)` 36 ms and `congress_detail(117)` 62 ms, from 0.33 s
and 0.25 s.

Any write to a counted table recomputes every Congress, not only the
Congress the write touched. The live computation runs once per load, after
the update's last step, and not on a reader's request.

Two writers to the counted tables in concurrent transactions wait on the
`data_version` row until the first commits. The loaders run one at a time
under the update's `flock`.

A table added to `_congress_summaries` needs its trigger, in a migration and
in `db.models.DATA_VERSION_TABLES`.
