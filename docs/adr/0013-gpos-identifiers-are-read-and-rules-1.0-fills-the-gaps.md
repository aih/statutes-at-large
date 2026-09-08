# ADR-0013: GPO's identifiers are read from a PLAW file; rules-1.0 fills the gaps

Date: 2026-09-08. Status: accepted. Implements design section 2's identifier
column ("GPO's, `/us/pl/118/5/dA/tI/s101/a`") for the PLAW source and
records how the two identifier sets compare.

## Context

The volume loader assigns identifiers by rule (`ingest/identifiers.py`,
`rules-1.0`, written to match GPO's PLAW form) because the volume USLM has
none. A PLAW bulk-data file carries `@identifier` on divisions, titles,
subtitles, chapters, parts, sections and every level below a section. It
does not carry them everywhere: the unnumbered single section of a
disapproval resolution (Public Law 118-1), and the general-provisions sections
that sit inside `level` blocks of appropriations acts (783 of the 801
unidentified sections in the 118th Congress are in three laws), have none.

## Decisions

1. **An identifier GPO wrote is kept as written**, on units and on the
   levels below a section, and `provenance_identifiers` is `gpo-uslm`. The
   section number a unit is indexed by (`units.section_num`, design section 3
   rule 3) is the identifier's `s…` segment, so `/us/pl/118/22/s102` resolves
   to whatever GPO stamped `s102`.

2. **A level with no identifier gets one by rule.** The segment is built from
   `num/@value` (or the `num` text) under the nearest identified ancestor,
   the way the volume loader builds every identifier; the unnumbered first
   section of an act is `s1` (CLAUDE.md gotcha 4); a later unnumbered section
   is not addressable. The count is reported per level
   (`identifiers_assigned`), the law is listed
   (`laws_with_assigned_identifiers`), and the law's
   `provenance_identifiers` becomes `gpo-uslm+rules-1.0`.

3. **Where both sources hold a law, GPO's file wins** (ADR-0011) and the load
   writes the set difference between the volume copy's rules-1.0 identifiers
   and GPO's, per level, into `docs/verification/plaw-{congress}.json`. With
   `--volumes-dir` the comparison reads the volume file on disk, so a re-load
   reproduces it.

4. **A wrong `citableAs` is overridden by the running head.** Five files
   (113-77, 113-78, 116-131, 117-121, 118-79) cite a volume the running head
   on every page contradicts; the volume is taken from the running head and
   the page labels from the markers, and the report lists the warning.

## Measured

Over the 34 laws of the 118th Congress that both the Hub's `STATUTE-137.xml`
and the bulk data hold, 11,840 identifiers on 13 levels, from divisions to
subitems, are in both sets and none is in one set only. Across the 113th to
119th Congresses (2,149 laws), 24,658 identifiers in 133 laws were filled in
by rule; the rest, 2,016 laws, are `gpo-uslm` throughout.

## Consequences

- A US Code source credit written in GPO's form resolves the same way against
  either source; the comparison found no case where the rules would have sent
  a citation elsewhere.
- Three hierarchy identifiers are duplicated inside their laws (115-91
  `dA/tIX/stD`, 117-263 `dG/tLXXII/stA`, 118-35 `dA`); the second occurrence
  is stored with `occurrence = 2`, as the volume loader does.
- `provenance.identifiers` on a response takes three values; a client that
  read only `rules-1.0` needs the other two.
