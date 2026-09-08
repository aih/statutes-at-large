# Era sweep

Eleven volumes from different eras fetched from the Hub and run through the
loader over SQLite on 2026-09-07 (`scratch`, not committed as JSON because only
64, 72, 124 and 137 are loaded into the deployment database). The point of the
sweep is that the loader runs over every era without an exception, and what it
reports for each.

| Volume | Year | Size | Laws | Kinds | Sections | Quoted skipped | Collisions | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 1789–1799 | 5.4 MB | 458 | act 458 | 2,397 | 6 | 0 | chapter numbers in Roman numerals; 1 unidentified |
| 12 | 1859–1863 | 11.0 MB | 721 | act 721 | 2,523 | 13 | 0 | 19 acts printed twice in the file (`repeated_laws`); 1 unidentified |
| 30 | 1897–1899 | 16.2 MB | 1,329 | act 1,329 | 3,433 | 74 | 0 | 288 unnumbered later sections (appropriations paragraphs) not addressable |
| 45 | 1927–1929 | 30.2 MB | 1,722 | pl 1,028 / pvtl 562 / act 132 | 3,985 | 180 | 12 demoted | |
| 60 | 1946 | 13.1 MB | 966 | pl 440 / pvtl 526 | 2,556 | 245 | 0 | |
| 90 | 1976 | 21.6 MB | 496 | pl 382 / pvtl 114 | 3,633 | 939 | 1 dropped | |
| 100 | 1986 | 31.9 MB | 448 | pl 424 / pvtl 24 | 5,960 | 1,409 | 0 | 118 unnumbered later sections |
| 110 | 1996 | 31.5 MB | 243 | pl 239 / pvtl 4 | 6,557 | 1,056 | 0 | before the merged-component fix: 299 repeated section identifiers |
| 116 | 2002 | 17.5 MB | 246 | pl 241 / pvtl 5 | 3,918 | 569 | 0 | one component holds 47 laws (`merged_components`) |
| 120 | 2006 | 29.8 MB | 313 | pl 312 / pvtl 1 | 4,157 | 1,076 | 0 | |
| 132 | 2018 | 45.3 MB | 326 | pl 325 / pvtl 1 | 7,550 | 553 | 0 | |

Before the fixes made after the first pass, volumes 1 and 12 loaded no laws
(Roman numerals) and volume 116 loaded 200 (first `pLaw` of each component
only). Volume 110's repeated identifiers come from the same merged-component
shape and were not re-measured.

Reproduce one row:

```
uv run python -m ingest fetch-statute 30
uv run python -m ingest statute data/statute/xmls/STATUTE-30.xml --json
```
