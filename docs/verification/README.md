# Verification

One JSON report per loaded volume, written by `python -m ingest statute
--report docs/verification` and never edited by hand. Regenerate with
`make dev-data` (volumes 64 and 124) or `make load-all`.

| Volume | Laws | pl / pvtl / act | Units | Sections | Quoted sections skipped | Pages | Collisions | Source sha256 |
|---|---|---|---|---|---|---|---|---|
| 64 (1950) | 1,230 | 457 / 722 / 51 | 3,240 | 3,063 | 358 | 2,604 | 46 demoted, 0 dropped | in `statute-64.json` |
| 124 (2010) | 251 | 249 / 2 / 0 | 4,748 | 4,077 | 591 | 4,463 | 0 | in `statute-124.json` |

Fields:

- `laws_loaded`, `laws_by_kind`: `pLaw` components stored. `act` counts chapter-era
  laws whose number could not be kept (ADR-0003) or was never read.
- `units`, `units_by_level`, `sections`: rows in `units`.
- `sections_in_quoted_content_skipped`: `<section>` elements inside `quotedContent`,
  which are text of another act and are not units.
- `stat_pages`: (page, law) rows.
- `aliases`, `aliases_dropped_as_taken`: identifier forms written; forms another law
  of the volume already held.
- `number_conflicts`, `numbers_out_of_sequence`: ADR-0003's decisions and observations.
- `skipped_components`: concurrent resolutions, presidential documents, part prefaces.
- `unidentified`: components with no usable identifier.

The `slow` tests in `tests/test_statute_parser.py` re-derive the law, section and
quoted-section counts from the downloaded volumes (`make test-slow`).
