# PLAW fixtures

Verbatim files from GovInfo bulk data, fetched 2026-09-08 with no API key. Not
cut: each is a whole public law.

| File | URL | Shape |
|---|---|---|
| `PLAW-118publ1.xml` | https://www.govinfo.gov/bulkdata/PLAW/118/public/PLAW-118publ1.xml | one unnumbered inline section with no identifier anywhere; 137 Stat. 3 |
| `PLAW-118publ22.xml` | https://www.govinfo.gov/bulkdata/PLAW/118/public/PLAW-118publ22.xml | divisions, titles, subtitles, GPO's identifiers on every level, nine sections in `quotedContent`; 137 Stat. 112–124 |
| `PLAW-118publ34.xml` | https://www.govinfo.gov/bulkdata/PLAW/118/public/PLAW-118publ34.xml | two titles; 137 Stat. 1112–1116 |
| `PLAW-119publ1.xml` | https://www.govinfo.gov/bulkdata/PLAW/119/public/PLAW-119publ1.xml | the Laken Riley Act, sections only; 139 Stat. 3 |

Public Laws 118-22 and 118-34 are also in `../statute-137-slice.xml`, so the
volume-derived and the PLAW-derived forms of the same laws meet in the tests.
Public Law 118-3 is in the volume slice only.

Listings, saved with `Accept: application/json` for the poller's tests:

| File | URL |
|---|---|
| `PLAW.json` | https://www.govinfo.gov/bulkdata/json/PLAW |
| `PLAW-118.json` | https://www.govinfo.gov/bulkdata/json/PLAW/118 |
| `PLAW-118-public.json` | https://www.govinfo.gov/bulkdata/json/PLAW/118/public (275 entries: 274 laws and the zip) |
| `PLAW-119-public.json` | https://www.govinfo.gov/bulkdata/json/PLAW/119/public (103 entries: 102 laws and the zip) |
