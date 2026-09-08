# Verification

One JSON report per loaded volume, written by `python -m ingest statute
--report docs/verification` and never edited by hand. Regenerate with
`make dev-data` (volumes 64 and 124), `python -m ingest statute --volumes 26,68,72,137
--report docs/verification`, or `make load-all`. Volumes 26 and 68 are loaded because
the Sherman Act and the Atomic Energy Act of 1954 have compilations among the COMPS
fixtures (ADR-0006). The full sha256 of each source
file is in its report.

The Hub's `STATUTE-137.xml` (12 MB) holds 34 public laws and 183 proclamations;
the volume as printed has more laws. The report describes the file as fetched.

| Volume | Laws | pl / pvtl / act | Units | Sections | Quoted sections skipped | Pages | Collisions (ADR-0003) | Source sha256 |
|---|---|---|---|---|---|---|---|---|
| 26 (1890) | 2,093 | 0 / 0 / 2093 | 3,461 | 3,459 | 44 | 3,165 | 0 demoted, 0 dropped | `901ba30a7986…` |
| 64 (1950) | 1,230 | 457 / 722 / 51 | 3,240 | 3,063 | 358 | 2,604 | 46 demoted, 0 dropped | `af5a4384ba30…` |
| 68 (1954) | 1,268 | 493 / 772 / 3 | 3,746 | 3,538 | 367 | 2,579 | 3 demoted, 1 dropped | `bff979fa9b33…` |
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

## Citation index (stage 3)

`citations.json` is written by `python -m ingest citations --from-hub --report
docs/verification` (`make citations`) and describes the `dreamproit/uscode`
`current` config as loaded (ADR-0008). Dataset revision
`a34c462ae07710fcc3854016130d83f01df1317e` (2026-08-14), three shards, 182 MB.

| | |
|---|---|
| US Code sections read | 65,938 (56 titles, 103 release labels) |
| `ref` elements seen | 1,327,967; 10,554 without `href` |
| refs to `/us/usc/` (counted, not stored) | 271,849 |
| rows stored | 1,081,463 (`pl` 637,838, `stat` 368,124, `act` 75,501) |
| by context | `note` 748,915, `sourceCredit` 312,334, `text` 20,214 |
| `<a href>` citations from revision-note tables | 35,899 |
| public-law rows with a date from the text | 304,888 |
| acts cited by date alone | 1,137 |
| unparsed (`/us/stat/68A/…`, `/us/stat/70A/…`) | 5,357 |
| distinct targets / laws / (law, section) pairs | 479,904 / 19,246 / 141,201 |
| target laws in a loaded volume | 1,046 of 19,246 (six volumes loaded) |

Fields: `refs_by_prefix` and `rows_by_context_and_kind` are the cross-tabs;
`by_title` has rows, sections and release labels per citing title;
`unparsed_samples` lists twenty of the hrefs that did not parse.

## Classification tables mirror (stage 3)

`classifications.json` is written by `python -m ingest classifications --report
docs/verification` (`make classifications`) and describes one run of the
mirror over the US Code site's API (ADR-0009). On 2026-09-08: 31 `pl` tables
seen and loaded (2 ECCT files skipped), 144,885 rows, 78 s; the site's own
check of uscode.house.gov was at 06:41 UTC that day and covered "Public Law
119-70 and Public Laws 119-74 through 119-103".

| Congress | Tables | Rows |
|---|---|---|
| 104 | 1 (whole congress) | 11,737 |
| 105 to 118 | 2 each | 4,478 (118th) to 13,948 (105th) |
| 119 | 2 | 3,614 |

Fields: `files[]` has one line per table with `action` (`loaded`, `unchanged`,
`skipped`), the rows held, pages fetched, the row hash and the covered-law
sentence; `upstream_checked_at` and `upstream_covered_text` are the site's.
