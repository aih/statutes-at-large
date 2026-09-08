# ADR-0011: A PLAW package outranks the volume file for the same law

Date: 2026-09-08. Status: accepted. Implements design section 9, step 4
("replacing the volume-derived units for those laws").

## Context

From the 113th Congress on, a public law is in two GovInfo sources: the
volume file (`STATUTE-137.xml`, no identifiers, stamped by `rules-1.0`) and
the bulk-data package (`PLAW-118publ22.xml`, GPO's identifiers on every
level). Both parse into the same `laws` row shape and the same primary
identifier. `laws.identifier` is unique, so a load has to decide which copy a
stored law is.

## Decision

1. **`ingest/load.py: SOURCE_PRECEDENCE` ranks `PLAW` above `STATUTE`.**
   `_write_law` reads the stored copy's `source_collection` before writing.
   A PLAW load replaces a STATUTE-derived law (units, aliases, pages) and
   re-points compilations that were linked to the old row. A STATUTE load
   that meets a PLAW-derived law writes nothing and lists the identifier under
   `laws_kept_from_plaw` in the volume report. A load from the same collection
   replaces its own copy, so both loaders stay idempotent.

2. **The law's source is recorded on the row and served.** `source_collection`
   and `source_package` say where the text came from; `provenance_identifiers`
   says who wrote the identifiers (ADR-0013). `Repository.law_sources` answers
   which collection serves a law, whether its volume is loaded, and what its
   PLAW package is called, and `GET /api/v1/laws/{c}/{n}` carries that as
   `sources`.

3. **Stat. pages follow the copy.** `stat_pages` rows are rewritten from the
   PLAW file's page markers; `/us/stat/137/112` answers from the PLAW-derived
   law once it is loaded, with the same page set the volume gave.

4. **A PLAW load records a `source_checks` row** with collection `PLAW`, the
   newest package by (congress, number), and the packages that were new or
   replaced a volume copy, so `/status` can report the collection and its
   staleness the way it does STATUTE and COMPS.

## Consequences

- The order of loads does not matter: volume then congress, or congress then
  volume, ends in the same state.
- A volume re-load after the congress is loaded reports every law it left
  alone; for volume 137 that is the 34 laws the Hub file holds.
- `seq_in_volume` of a PLAW-derived law is its law number, so page listings
  that mix the two sources order laws by number within a volume.
- The compilation link (`comps.law_id`) survives replacement; the match by
  (congress, number) in `Repository._comps_of` would hold even if it did not.
