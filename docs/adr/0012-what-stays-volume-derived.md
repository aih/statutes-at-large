# ADR-0012: What stays volume-derived after the PLAW load

Date: 2026-09-08. Status: accepted. Narrows design section 2 ("PLAW: 104th
Congress onward; USLM from the 113th") and section 6 ("104th to 112th: PDF
through the pipeline's `digital` profile").

## Context

GovInfo's PLAW collection starts with the 104th Congress (1995). Bulk-data
USLM exists for the 113th Congress onward and for public laws only:
`bulkdata/PLAW/{c}/public` lists one file per public law and no `private`
folder, and the API's `packages/PLAW-118pvtl1/uslm` answers 400. Laws of the
104th to 112th Congresses have PDF and text renditions only. The design routes
those PDFs through the pipeline's `digital` profile in
`../statute-pdf-to-xml`, which is a later stage.

## Decision

1. **Public laws of the 113th Congress onward come from PLAW bulk data**
   (`python -m ingest plaw load`, `make plaw`) and replace the volume-derived
   copies (ADR-0011).

2. **Private laws stay volume-derived** in every Congress. They are served
   from `STATUTE-{vol}` with `rules-1.0` identifiers, and `law_sources` names
   their PLAW package (`PLAW-118pvtl1`) with `plaw_uslm = false`.

3. **Public laws of the 104th to 112th Congresses stay volume-derived** until
   the pipeline's `digital` profile produces USLM for them. `law_sources` names
   the PLAW package with `plaw_uslm = false`. Nothing in this repository reads
   a PLAW PDF.

4. **Laws before the 104th Congress have no PLAW package**; `law_sources`
   reports `plaw_package = null`.

## Consequences

- After `make plaw`, the `PLAW` collection on `/status` holds the 113th to
  119th Congresses; every other law on the site is `STATUTE`-derived.
- The reader link rule in design section 1 (govinfo's `link/plaw` for the
  104th onward) is unchanged by which source serves the text.
- When the reprocessed volume USLM lands (design stage 6), it replaces
  STATUTE-derived laws only; PLAW-derived laws keep GPO's text and
  identifiers.
