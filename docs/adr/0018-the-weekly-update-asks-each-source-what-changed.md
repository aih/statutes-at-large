# ADR-0018: The weekly update asks each source what changed

Date: 2026-09-08. Status: accepted. Implements the deployment plan's
section 6 and section 2 item 6; follows the US Code site's ADR-0036
(record every check) and departs from its daily cadence.

## Context

Five sources change at different rates: GovInfo's PLAW bulk data (new
laws weekly in session), the COMPS collection (a few packages a week),
the volume files on the Hub (reprocessed rarely, design stage 6), the
`dreamproit/uscode` dataset (a new release point a few dozen times a
year; a reload is seven minutes), and the classification tables mirrored
from the US Code site (edited as OLRC classifies). Before this ADR
`fetch-statute` skipped any file already on disk and `citations
--from-hub` reloaded 1,081,463 rows on every run.

## Decisions

1. **Each step asks its source and writes a `source_checks` row either
   way.** `deploy/update-sources.sh` runs, inside the `api` container and
   in this order: `plaw poll`; `comps poll --since` the day before the
   last COMPS check; `fetch-statute 1-137 --if-changed` then `statute
   --volumes 1-137 --changed-only`; `citations --from-hub --if-changed`;
   `classifications`. A step that finds nothing costs one listing call
   and one row, so `/api/v1/status`'s `stale` (a week without a check)
   is the signal that the schedule stopped running, not that the sources
   stopped changing.

2. **`fetch-statute --if-changed` compares the Hub's tree listing with
   the file on disk.** One call to
   `/api/datasets/dreamproit/us-statutes-at-large/tree/main/xmls`
   (`ingest/hub.py: list_volume_files`, following `Link: rel="next"`).
   A file stored through LFS is compared by `lfs.oid`, the sha256 of its
   content; a file kept in git by its blob id (`git_blob_sha1`); the size
   is checked first. What differs or is missing is downloaded. The check
   row has collection `STATUTE`, `packages_seen` the listing's count,
   `new_packages` the volumes fetched, `newest_package` null (a
   `STATUTE-{n}` there is read by `law_sources` as the volume having been
   loaded), and `ok` false when the listing could not be read.

3. **`statute --changed-only` compares the file with the one its last
   load read.** `load_volume` records the file's sha256 in a new column
   `source_checks.source_sha256` (migration `9c1f2b7d3e40`). A file whose
   sha256 equals the recorded one is skipped; a volume never loaded, or a
   file whose name carries no volume number, is loaded. When nothing was
   loaded one `STATUTE` row records the files looked at. The two
   comparisons are separate on purpose: the first says whether the Hub
   differs from disk, the second whether disk differs from the database,
   so a manual download or an interrupted load is caught by the next run.

4. **`citations --from-hub --if-changed` compares the dataset revision.**
   One call to the dataset record; when `sha` equals the last `USCODE`
   check's `newest_package` the shards are neither downloaded nor loaded
   and a `USCODE` row with `packages_seen` 0 records the check.
   `/api/v1/status` `citations` gains `checked_at` (the last check, loaded
   or not) beside `loaded_at` (the last row that loaded shards), so a
   skipped check moves one and not the other.

5. **The dump follows the data.** `pg_dump` to
   `s3://statutes-linkedlegislation/db/statutes-<date>.dump` runs only
   when a step wrote rows: `/api/v1/status` is read before and after the
   steps with `checks`, `stale`, `citations.checked_at` and
   `classifications.last_check` removed (the members every check moves),
   and a difference, or an unreadable status, means a dump. Both halves
   of the pipe are checked through `PIPESTATUS`. The bucket's lifecycle
   expires `db/` after 60 days. A week with nothing loaded uploads
   nothing.

6. **Two schedules, failing independently.**
   `.github/workflows/update-sources.yml` Mondays 07:53 UTC (one SSM
   command, `executionTimeout` 4 hours, polled 5.5 hours) and
   `/etc/cron.d/statutes` Thursdays 06:41 UTC, both running the same
   script with no arguments. The US Code site polls daily because a
   release point changes what its pages say the same day; here a week is
   the bound `SOURCE_CHECK_STALE_AFTER` already encodes, and the two runs
   keep every check under it.

7. **`--check-only` and `--force`.** `--check-only` runs `plaw poll
   --limit 0` and `comps poll --limit 0` (each writes its check row and
   fetches nothing; the PLAW walk stops before reading a listing and
   leaves `newest_last_modified` null, which `default_since` ignores) and
   `fetch-statute --if-changed` (a changed volume file is downloaded, not
   loaded); steps 4 to 7's loads and the dump are skipped, so a check-only
   run records no `USCODE` or classification check. `--force` runs `plaw
   poll --force`, `comps poll --force`, `statute` without
   `--changed-only`, `citations` without `--if-changed` and
   `classifications --force`: the backstop for a load that half finished.
   A run that finds the lock held exits 0 with a message; a step that
   fails is logged with its exit status and time and the run continues,
   exiting 1 at the end.

## Consequences

- A typical week is under a minute and about ten requests: eight PLAW
  listings, one COMPS collection call, one Hub tree listing, one dataset
  record, one classification listing.
- `source_checks` gains rows that loaded nothing; readers of the table
  tell them apart by `newest_package` (null on a listing check) and
  `packages_seen` (0 on a skipped citations check).
- A run interrupted by a deploy resumes on the next schedule: every
  loader is idempotent per volume, package or file, and the dump happens
  only after a pass that loaded something.
- `make load-prod` is the first load (plan section 5) with the same
  compose prefix; `make update-prod` and `make update-prod-check` are the
  script's two modes.
