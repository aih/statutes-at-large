# Verification

One JSON report per loaded volume, written by `python -m ingest statute
--report docs/verification` and never edited by hand. Regenerate with
`make dev-data` (volumes 64 and 124), `python -m ingest statute --volumes 72,137
--report docs/verification`, or `make load-all`. The full sha256 of each source
file is in its report.

The Hub's `STATUTE-137.xml` (12 MB) holds 34 public laws and 183 proclamations;
the volume as printed has more laws. The report describes the file as fetched.

| Volume | Laws | pl / pvtl / act | Units | Sections | Quoted sections skipped | Pages | Collisions (ADR-0003) | Source sha256 |
|---|---|---|---|---|---|---|---|---|
| 64 (1950) | 1,230 | 457 / 722 / 51 | 3,240 | 3,063 | 358 | 2,604 | 46 demoted, 0 dropped | `af5a4384ba30…` |
| 72 (1958) | 1,061 | 618 / 443 / 0 | 4,145 | 3,852 | 871 | 2,787 | 0 demoted, 3 dropped | `e41347d1031e…` |
| 124 (2010) | 251 | 249 / 2 / 0 | 4,748 | 4,077 | 591 | 4,463 | 0 demoted, 0 dropped | `021704863305…` |
| 137 (2023) | 34 | 34 / 0 / 0 | 1,512 | 1,291 | 175 | 1,113 | 0 demoted, 0 dropped | `ef857f483fbf…` |

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
