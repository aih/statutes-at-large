# ADR-0036: A law's Congress is one its volume prints, and the current Congress is updated daily

Date: 2026-10-20. Status: accepted. Amends ADR-0033 decision 2 and ADR-0018
decision 6.

## Context

A review of `/app/congress` against every law the API lists found laws placed
in a Congress their volume does not print:

| Volume | Laws | Listed under | Cause |
|---|---|---|---|
| 32 | 17 acts, 32 Stat. 1031–1228 | 56th | OCR year 1901 for 1903 |
| 34 | 6 acts | 1st, 9th, 56th | OCR years 1007, 1807, 1900 |
| 37 | Public Nos. 427–430 | 63rd, as `/us/pl/63/427`… | `meta/congress` 63, approved March 4, 1913 |
| 44 | Private Nos. 328–331 | 72nd, as `/us/pvtl/72/328`… | `meta/congress` 72 |
| 46 | ch. 583, 46 Stat. 2159 | 72nd | dated March 5, 1931 |
| 54 | chs. 937, 940, 941 | 77th | acts of the 76th approved January 3–9, 1941 |
| 123 | 123 Stat. 2085 | 110th, as `/us/pl/110/78` | `meta/congress` 110 for Public Law 111-78 |

`congress_of_act` (ADR-0033) took the approval date's Congress for every
chapter act, so an OCR year moved an act across a century. Numbered laws took
`meta/congress`, which built the wrong identifier; Public Laws 62-427 to
62-430, 69-328 to 69-331 and 111-78 had no page. Public Law 110-78 (2007)
had none either: the volume 123 law with the same identifier replaced it.

A volume reload replaced laws by identifier and left a row whose identifier
had changed.

First and last approval dates came from `min` and `max` over every law of
the Congress, so the page showed 32 Stat. 1337's `1110-04-16`, the
placeholder `0001-01-01` (120 Stat. 2641, 138 Stat. 1008), 82 Stat. 123's
`1958-05-17` and 95 Stat. 105's `1979-07-09`.

The weekly update (ADR-0018) ran Mondays and Thursdays, so a public law
published by GovInfo on a Tuesday was listed as pending for up to six days.

## Decision

1. `ingest.identifiers.volume_congresses(volume)` gives the Congresses a
   volume prints: volumes 1–5 and 6 by table, 9–12 by table, 13–49 the
   volume plus 25, 50 the 75th, 51 onward `(volume - 55) // 2 + 77`; volume
   77 adds the 87th (it reprints Public Laws 87-456 and 87-794) and volume 89
   the 93rd (laws approved in January 1975). The treaty volumes 7 and 8 have
   none. Every law the API listed on 2026-10-20 falls in its volume's set
   except the ones in the table above and Public Law 91-696 in volume 89.
2. `congress_in_volume(meta, enacted, volume, act=…)`: a chapter act takes
   `congress_of_act` and a numbered law `meta/congress`, each when the
   volume prints that Congress; else the approval date's Congress when the
   volume prints it; else the volume's one Congress; else `meta/congress`.
   A volume with no set keeps ADR-0033's rule.
3. A numbered law's identifier is built with that Congress, in the light
   pass (`iter_claims`) and the full one, so the collision plan sees the
   corrected numbers. The warning is `congress taken from the approval date,
   not meta/congress` or `congress taken from volume {n}, not meta/congress`.
4. Before writing, `load_volume` deletes the volume's `STATUTE` laws whose
   identifier the file no longer yields and lists them as
   `laws_dropped_as_stale`; a compilation linked to one is unlinked.
5. A Congress's `first_enacted` and `last_enacted` count only dates within
   `storage.identifiers.congress_term`: from the start of its term to the
   start of the next, plus 31 days from the 73rd on.
6. `deploy/update-sources.sh --current` runs `plaw poll` for the current
   Congress and the one before, `plaw pending`, `classifications` for the
   same two Congresses, `reindex-search --since` yesterday, the dump when a
   step wrote rows, and the status. `.github/workflows/update-sources.yml`
   runs it daily at 10:17 UTC; the Monday and Thursday runs are unchanged.
   `workflow_dispatch` takes a `mode` of `auto`, `current` or `check-only`.

## Consequences

The volumes in the table, and volume 121 for Public Law 110-78, change only
on a reload; `statute --changed-only` skips them because their files have not
changed. On the box:

```
docker compose -f docker-compose.prod.yml exec -T api uv run python -m ingest \
  statute --volumes 32,34,37,44,46,54,121,123 --report data/verification
docker compose -f docker-compose.prod.yml exec -T api uv run python -m ingest \
  reindex-search --since <the day of the reload>
```

The four public and four private laws move to `/us/pl/62/427`…`430` and
`/us/pvtl/69/328`…`331`; `/us/pl/111/78` gets a page and `/us/pl/110/78`
names the 2007 law again. The old identifiers answer 404.

The approval dates themselves are not corrected. An act's `/us/act/{date}/ch{n}`
identifier is built from the date, so 32 Stat. 1031 is still
`/us/act/1901-03-03/ch1005`.

The daily run writes a `PLAW` check row each day; its `packages_seen` counts
two Congresses' listings, not every Congress's.
