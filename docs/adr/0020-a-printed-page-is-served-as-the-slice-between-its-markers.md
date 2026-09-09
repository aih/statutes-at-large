# ADR-0020: A printed page is served as the slice between its markers

Date: 2026-09-09. Status: accepted. Implements package B1 of
`docs/plans/2026-09-09-reader-improvements-plan.md`.

## Context

`GET /api/v1/us/stat/{volume}/{page}` named the laws on a printed page, said
which of them start there, and named the unit each page marker falls in. It
carried none of the text the page prints.

Nothing stored holds a page. Sections are the storage atom (ADR-0001) and a
page cuts across them: 64 Stat. 564 begins in the middle of section 3 of Public
Law 81-740 and ends in the middle of section 4. What the page prints is the run
of a law's stored XML between the `page` marker that names it and the next
marker in document order.

## Decision

1. **A page is the range between two markers.** `uslmtext.slice_between(root,
   start, end)` walks a deep copy of the law with
   `etree.iterwalk(root, events=("start", "end"))` and an `inside` flag: the
   start marker's `start` event opens the range and the end marker's `end`
   event closes it. An element's text is kept when the range is open at its
   start and its tail when the range is open at its end; an element is kept
   when it or a descendant is inside, and its ancestors are kept as containers.
   Comments and processing instructions are dropped.

   `uslmtext.page_slice(xml, page)` picks the markers: the one whose
   `@identifier` names the page, matched case-insensitively through
   `page_label` (gotcha 6), and the next `page` element in document order,
   whichever page that one names — a marker inside `quotedContent` ends the
   range like any other. A law that starts on the page carries no marker for
   it; the range then starts at the root, so the slice opens with the preface
   ("[CHAPTER 823] AN ACT"). A range with no later marker runs to the end of
   the law. The law's `meta` is dropped from the slice.

   `page_label` moved from `ingest/statute.py` to `uslmtext.py`, which both
   `ingest/` and `storage/` import.

2. **The answer carries the slice.** Each document of
   `GET /api/v1/us/stat/{volume}/{page}` gains `text`, the reading text of its
   slice, and `units`, the units the page touches: `unit_on_page` first, then
   every unit of the law whose `first_page` is the page, in reading order.
   `?format=xml` answers with one `slice` element per document inside a
   `statPage` element:

   ```xml
   <statPage identifier="/us/stat/64/564" volume="64" page="564">
     <slice law="/us/pl/81/740" from="/us/stat/64/564" to="/us/stat/64/565">…</slice>
   </statPage>
   ```

   `to` is the identifier of the marker the range ends at, absent at the end of
   the law. A page shared by two laws has two slices. The ETag covers the
   documents and the hash of each slice.

3. **The slice is computed per request and cached.**
   `functools.lru_cache(maxsize=256)` in `storage/postgres.py`, keyed on the
   law's id, its `content_hash` and the page, holding the slice's strings; a
   reload of the law changes the hash and the entry is not read again. The law
   is passed to the cached function through a `ContextVar`, so its XML is read
   on a miss only.

4. **`Repository.stat_page` computes the slice when it is asked to.**
   `stat_page(volume, page, *, with_slices=False)`. The stat route asks for the
   slices; `POST /labels`, which resolves a `/us/stat/` reference through the
   same method, does not, and parses no law XML.

## Consequences

- Measured on the dev database (volumes 26, 64, 68, 72, 124 and the PLAW
  congresses), `GET /api/v1/us/stat/136/5000`, a page inside Public Law
  117-328, whose XML is 11.3 MB: 1.41 s on the first hit, 0.16 s on a repeat,
  0.11 s for the 304. The plan's threshold for computing slices at load time
  into a `stat_page_slices` table is 2 s, so slices stay a request-time
  computation.
- A repeat spends its time loading `laws.xml` for the row, not slicing;
  package A's deferred `laws.xml` column (ADR-0019) takes that away.
- The stat page answer grows by the text of one page, about 3 KB.
