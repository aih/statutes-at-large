# ADR-0015: The citation parser is pure; `cite` answers in three shapes

Date: 2026-09-08. Status: accepted. Implements design section 5's `cite`
route; follows the US Code site's ADR-0023 and records where this site's
identifiers make the rules differ.

## Context

The design lists the forms `GET /api/v1/cite?q=` accepts: `Pub. L. 104-333,
§ 814`, `110 Stat. 4196`, `Act of Aug. 25, 1916, ch. 408`, `43 U.S.C. 1701`.
The source credits in the citation index add the full form (`Pub. L.
104–333, title VIII, § 814(e)(1), Nov. 12, 1996, 110 Stat. 4196`), the
chapter-era forms (`Aug. 30, 1954, ch. 1073, § 2`; `ch. 823, 64 Stat. 563`)
and private laws. The US Code site's parser (`citeparse.py`, ADR-0023) is
pure, has an accepted-forms table that runs without a database, and answers
a 422, `exists: false`, or `exists: true`.

## Decisions

1. **`citeparse.py` is pure.** It imports no `storage`, `db`, `fastapi`,
   `sqlalchemy`, `httpx`, `api` or `params`; `tests/test_architecture.py`
   fails if that changes. The accepted-forms table in
   `tests/test_citeparse.py` (125 cases) runs in `make test` with no
   fixtures. `parse_citation` returns a `ParsedCitation` (`kind`,
   `identifier`, `section_identifier`, `label`, the numbers, `hierarchy`,
   `stat_page`, `note`) or `None`.

2. **The forms.** A public or private law by number (`Pub. L.`, `Public
   Law`, `P.L.`, `PL`, `Pub. L. No.`, `Private Law`, `Priv. L.`, `Pvt. L.`;
   hyphen, en dash or em dash), with an optional tail of hierarchy words,
   a section (`§`, `§§`, `sec.`, `section`) with subdivisions, a date, a
   year in parentheses, a Stat. page, `note`, and the source-credit phrases
   `as amended`, `as added`, `formerly`. `section 3 of Public Law 81-740`.
   An act by date and chapter (`Act of Aug. 25, 1916, ch. 408`, `Aug. 30,
   1954, ch. 1073, § 2`, `1954-08-30, ch. 1073`), with the same tail. A
   Stat. page (`110 Stat. 4196`, `64 Stat. A12`, `113 Stat. 1501A-594`,
   trailing pages and a year ignored). A chapter with a page (`ch. 823, 64
   Stat. 563`, either order). An identifier typed in (`/us/pl/…`,
   `/us/act/…`, `/us/stat/…`, `/us/sComp/…`, `/us/usc/…`). A US Code
   citation in the standard, inverted and trailing-title forms, with
   `App.`, `note` and `et seq.` A bare section number, a chapter alone, a
   date alone, or a law followed by words the tail does not know is not a
   citation.

3. **Hierarchy words are read and dropped from a section's identifier.**
   `Pub. L. 118-5, div. A, title I, § 101` names `/us/pl/118/5/s101` and
   carries `hierarchy: ("dA", "tI")`. The section number is the join
   (design section 3, rule 3; ADR-0008 decision 3), and the API reports the
   stored form as `served_identifier`. A citation that names a level and
   no section keeps the level (`/us/pl/104/333/tVIII`).

4. **Subdivision case is kept**, and a four-digit parenthetical after a
   section is a year, not a subdivision.

5. **A chapter cited with a page names the page.** `ch. 823, 64 Stat. 563`
   has no `/us/act/` identifier without a date. The parse is `kind: "stat"`
   with `chapter: 823`; `api/cite.py` reads the page's documents and answers
   with the law whose chapter matches (and its section when one was cited).
   When the page is loaded and no law on it has the chapter, the page is
   the answer and `message` says so.

6. **Existence is answered with what exists.** `Repository.labels` for a
   law, an act, a section or a provision (the same rules a unit request
   follows, so `Aug. 30, 1950, ch. 823, § 3` resolves through its alias to
   `/us/pl/81/740/s3` with `resolution: "alias"`), `stat_page` for a page,
   `get_comp_unit` for a compilation. No new `Repository` method. A
   provision the section does not have is `exists: true` at the section
   with `resolution: "prefix"` and a `message`.

7. **A US Code citation is handed off.** `kind: "usc"`, `url` is
   `USCODE_ORIGIN` plus the identifier, `exists` is null, and nothing is
   looked up: that site's parser is the authority on its own forms.

8. **Three shapes.** 422 with `params.cite_not_a_citation` (the detail names
   the six forms of `params.CITE_FORMS`); 200 `exists: false` with a `note`
   saying nothing is loaded at the identifier (or on the page); 200
   `exists: true` with `served_identifier`, `resolution`, `url` (the bare
   citation URL, which redirects a browser to the reader) and a `note` from
   `params.cite_note` that repeats the resolution rule in `served_note`'s
   words.

9. **A person's budget and a short cache.** 60 requests then 2 a second per
   address; `max-age=300`; an ETag over the body and `If-None-Match`.

## Consequences

- `Pub. L. 104-333, § 814` answers `exists: false` until the 104th Congress
  is loaded (ADR-0012); the identifier is right and the reader says so.
- `POST /labels` also answers a `/us/stat/{vol}/{page}` identifier
  (`LabelPageOut`: the page's documents and PDF link), so the reader and
  the US Code site can link a page reference the same way they link a law.
- `make cite Q="…"` runs the parser and the live route.
