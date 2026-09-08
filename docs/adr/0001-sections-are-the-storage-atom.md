# ADR-0001: Sections are the storage atom; lower levels are cut at request time

Date: 2026-09-07. Status: accepted. Departs from design section 6.

## Context

Design section 6 gives `units` one row per section *and lower level*, each with
its verbatim XML fragment. A subsection's XML is contained in its section's, so
that stores every byte of statutory text once per depth (three to five times
for a modern law), and a request for `…/s814/e/1` still has to find and serve
the enclosing section for context.

The US Code site keeps the section as the atom and cuts the provision from the
section's XML at request time by `@identifier` (its ADR-0001).

## Decision

`units` holds one row per hierarchy node (division, title, subtitle, chapter,
subchapter, part, subpart) and per section. Sections carry XML, text, hash and
pages; hierarchy nodes carry heading, order and ancestors, and their XML is cut
from the law's when asked for. Every level below a section is stamped with its
identifier during the load and stays inside the section's XML.

`Repository.get_unit` resolves a path below a section to the section and
returns the sub-level as `provision` (`identifier`, `found`, `xml`, `text`).
Rule 2 of design section 3 (longest stored prefix) then applies naturally: a
path that exists inside the section is `exact` with a provision; one that does
not is `prefix` with `provision.found = false`, and the note says so.

## Consequences

- The section-number index (rule 3) is a column on the section row.
- `?format=xml` on a sub-section path returns the stamped fragment cut from the
  section, not a stored row.
- The whole law's XML is stored on `laws.xml`, so `/us/pl/{c}/{n}?format=xml`
  serves the `pLaw` element as GPO published it, with identifiers added.
