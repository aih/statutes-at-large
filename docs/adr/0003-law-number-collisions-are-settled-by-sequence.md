# ADR-0003: Law-number collisions inside a volume are settled by sequence

Date: 2026-09-07. Status: accepted. Not in the design.

## Context

In the chapter era the law number is read from a marginal note by GovInfo's
digitization vendor. Loading vol 64 (1950) with the number taken at face value
gave 49 pairs of laws with the same primary identifier, and the second of each
pair silently replaced the first.

Two causes. The official title of a law often names another law ("To extend
the Rubber Act of 1948 (Public Law 469, Eightieth Congress)"), and a regex over
the whole long title picked that number up. After restricting the read to the
`sidenote` inside `longTitle`, 46 collisions remain, all OCR misreadings of the
note (`835` for `535`, `560` for `590`).

## Decision

1. The number is read from the marginal note only (text first, `ref/@href`
   second, including the vendor's `/us/bill/{c}/pl/{n}` form).
2. Before anything is stored, a light pass over the volume collects every law's
   claim (`ingest/statute.py: iter_claims`) and `ingest/numbering.py` plans the
   collisions. Law numbers run in enactment order inside each series (public,
   private), so among the claimants of one number the one whose number lies
   between its uncontested neighbours' numbers keeps it. The others are stored
   under their chapter form, which comes from the printed chapter heading and is
   certain (`action = "demote"`). When neither fits, the first keeps it.
3. After 1957 there is no chapter form. A losing claimant is not stored
   (`action = "drop"`), and its citation and title go into the report.
4. Uncontested numbers that are out of sequence are reported
   (`numbers_out_of_sequence`) and left alone.

## Consequences

- Vol 64: 46 laws stored under their chapter form, 23 numbers reported as out
  of sequence, none lost. Vol 72: 3 laws dropped (`72 Stat. 412`, `605`,
  `1571`), each with a document number equal to its page number in the source.
- A demoted law is reachable by its chapter identifier and by `/us/stat/`;
  a source credit citing it by number resolves to the law that kept the number,
  which in the measured cases is the right one.
- The reprocessing run (OCR plan, section 7) is where these numbers get
  corrected at the source; the report lists exactly which.
