# ADR-0027: Contents open, a lone section shown on its parent's page, and the note's source sentence

Date: 2026-09-11. Status: accepted. Amends ADR-0014 (the reader) and design
section 4 (the as-enacted note).

## Context

A law page and a hierarchy-node page list their contents in a
`details#contents` disclosure, which rendered closed. The page for a law of
one section, such as Public Law 104-33, was a closed disclosure holding one
link.

The as-enacted note gave the currency of the text and where to check for
amendments. The source was in `provenance` only, as codes (`gpo-uslm`,
`rules-1.0`).

GovInfo's Statutes at Large USLM comes from two converters. `meta/processedBy`
is `Digitization Vendor` on every law in volumes 1 to 116, and `GPO Locator to
USLM Converter {version}` from volume 117 and in every PLAW file. The Hub
dataset `dreamproit/us-statutes-at-large` mirrors GovInfo's volume files:
`STATUTE-51.xml` fetched from `api.govinfo.gov/packages/STATUTE-51/uslm` has
the sha256 the dataset's `metadata.jsonl` records (`7511d02e…`).

## Decisions

1. **`details#contents` renders `open`** on a law and on a hierarchy node.

2. **A law or a node whose contents are one section shows that section.**
   The section is the unit's only child when that child is a section, or the
   one section of a public law whose summary has `section_count` 1
   (`lib/toc.ts: onlySection`). The reader fetches its XML and renders it
   below the Contents disclosure as `#text.section-body--whole`, with the
   section's own number and heading. "Text" joins the rail's "On this page"
   list. The section's own page is unchanged.

3. **The section page's h1 carries `smallCaps`** when the section's own
   `heading` has that class (`lib/uslm.ts: titleClass`). A heading with class
   `centered` renders as a block.

4. **`enacted_note` ends with `source_sentence`** (`params.py`): the GovInfo
   package, the converter, and who wrote the identifiers. The converter is
   GPO's digitization vendor for a volume up to `LAST_DIGITIZED_VOLUME` (116)
   and GPO's locator converter otherwise. The identifier clause follows
   `provenance_identifiers`. For `/us/pl/81/740/s3`:

   > The text is from GovInfo package STATUTE-64, converted to USLM from the
   > scanned volume by GPO's digitization vendor; the identifiers below the
   > law are assigned here by rule (rules-1.0).

## Consequences

- A law or node page with one section makes two more API calls: the
  section's XML, then the labels of the laws it cites.
- The table of contents, the rail and the breadcrumbs print the API's
  heading text, which has no classes. A heading GPO types in lower case and
  marks `smallCaps` is lower case there.
- The converter is decided from the volume number, not read from
  `processedBy`, which the loader does not store.
