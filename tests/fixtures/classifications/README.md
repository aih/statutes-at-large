# Classification table fixtures

Verbatim JSON from the US Code site's API, fetched 2026-09-08 with
`curl -A 'statutes-linkedlegislation/0.1 (+https://statutes.linkedlegislation.org)'`.

| File | URL |
|---|---|
| `tables.json` | `https://uscode.linkedlegislation.org/api/v1/classifications/tables` |
| `entries-118-2-0.json` | `https://uscode.linkedlegislation.org/api/v1/classifications/tables/118/2/entries?sort=pl&limit=40&offset=0` |
| `entries-104-0-0.json` | `https://uscode.linkedlegislation.org/api/v1/classifications/tables/104/0/entries?sort=pl&limit=40&offset=0` |

The listing names 33 files (31 `pl`, 2 `ecct`). The two entry pages hold 40
rows each while their `total` is 2987 and 11737: the loader stores the 40 rows
it holds, records the listing's `row_count` in the report, and ends the file's
paging with a warning when the next page is not in the directory. The other
`pl` files have no page here and are skipped.

`entries-118-2-0.json` covers Public Laws 118-35 to 118-41 (the table covers
118-35 to 118-274); `entries-104-0-0.json` covers Public Law 104-1 of the
whole-congress table (`session` 0).
