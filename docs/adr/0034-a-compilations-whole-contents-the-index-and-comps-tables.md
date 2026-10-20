# ADR-0034: A compilation's whole table of contents, the compilations index, and COMPS tables

Date: 2026-10-20. Status: accepted. Amends ADR-0027 (decision 1 now covers
the compiled view) and ADR-0007.

## Context

The reader's compiled view built its rail and its Contents disclosure from the
unit's `children`. A compiled section has none, and the root and a hierarchy
node have only their direct children, so `/app/us/sComp/119/24/s2` showed no
contents in the rail and `/app/us/sComp/80/758/tII/s205` did not list title
II. No endpoint returned a compilation's units at every level.

`GET /api/v1/comps` builds each row with several queries; a request for 200
rows to the production site took 1.35 seconds, and the box holds 2,698
compilation files.

The COMPS XML carries GPO's CALS tables (`table`, `tgroup`, `colspec`,
`thead`, `tbody`, `tfoot`, `row`, `entry`, `ttitle`) in the namespace
`http://schemas.gpo.gov/xml/comps-dtd`, inside `foreign`. The renderer matched
elements by local name, so `table`, `thead` and `tbody` became HTML table
elements and `row` and `entry` became `div`. Section 205 of the Federal Water
Pollution Control Act (`/us/sComp/80/758/tII/s205`) printed its allotment
table as one column of text.

## Decision

1. `Repository.comp_toc(prefix, through=)` returns every unit under a prefix
   in reading order: the whole-act file's units, or every per-title file's
   in title order when the act has no whole-act file (the files ADR-0007,
   decision 8 gathers). It selects identifiers, levels, numbers and headings
   only.
2. `GET /api/v1/comps/{c}/{n}/toc[?through=]` serves it with `units_count`,
   `sections_count` and the version's `current_through.pl`; 404 when no
   compilation has the prefix or no version matches `through`.
3. The compiled view fetches the table of contents beside the unit. The rail
   is titled "In this compilation", lists every unit under the bound of
   `railNodes` (300 units), opens the branch holding the current unit, and
   keeps `through=` on every link. The Contents disclosure renders `open` and
   lists the whole compilation on the root and the node's subtree on a
   hierarchy node. A section gets previous and next links and the `j` and
   `k` keys. When the table of contents cannot be fetched the page falls
   back to the unit's `children`.
4. `Repository.comp_titles()` returns every file in one query with its
   current version's `current_through_pl`. `GET /api/v1/comps/titles` serves
   it with the identifier each file is read at: the prefix for a whole-act
   file, `{prefix}/t{partial_of}` for a per-title file.
5. `/app/comps` lists every file A to Z under a letter bar, one entry per
   file. `q=` filters on the server; an inline script runs the same filter as
   the box is typed into. The landing page links to it from the examples and
   from the Statute Compilations row. Its inline script ceiling is 5,000
   bytes (`docs/js-budgets.json`).
6. The renderer handles every element in the `comps-dtd` namespace in
   `renderCals` (`lib/uslm.ts`). `table` is a scrolling region holding one
   HTML table per `tgroup`, captioned by `ttitle`; `row` is `tr`; `entry` is
   `th` in `thead` and `td` elsewhere; `namest` and `nameend` give `colspan`
   through the `colspec` names, or `colN` when there is no `colspec`; the last
   entry of a row with fewer cells than `tgroup/@cols` spans the rest;
   `align` is kept; `tfoot` follows `tbody`. `italic`, `bold`, `superscript`,
   `subscript` and `quote` are `i`, `b`, `sup`, `sub` and `q`.

## Consequences

- Every compiled page makes one more API call. For a compilation of
  thousands of units the root page lists every unit in its Contents, as a
  public law's page does.
- The rail of a compilation over 300 units shows the hierarchy and the open
  branch's sections only, as for a law.
- `/app/comps` is one page holding every file.
