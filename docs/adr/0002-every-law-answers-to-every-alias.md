# ADR-0002: A `law_aliases` table, and the law number as the primary form

Date: 2026-09-07. Status: accepted. Implements design section 3, rule 4.

## Context

Design section 3, rule 4: a law from 1901 to 1957 answers to both its
public-law and its chapter identifier. OLRC cites those years by chapter
(`/us/act/1947-07-26/ch343`); GovInfo and later source credits cite the number.
The design's `laws` table has one identifier column.

## Decision

`laws.identifier` is the primary form: `/us/pl/{c}/{n}` or `/us/pvtl/{c}/{n}`
when the law has a number and the Congress is the 57th or later; otherwise
`/us/act/{date}/ch{n}`. `law_aliases` holds every identifier the law answers
to, the primary included. `Repository.get_unit` looks the law up by alias and
reports `resolution = "alias"` with the primary form as `served_identifier`
when the request used another one. Unit identifiers are stored under the
primary form only.

A law whose only certain identifier is the chapter form (no number read from
the marginal note, or the number lost to a collision, ADR-0003) is `kind =
"act"` and has one alias.

## Consequences

- Two laws can claim one chapter form when the vendor repeated a chapter
  number on one date (six cases in vol 64). The alias stays with the first law
  and the loss is counted in the report as `aliases_dropped_as_taken`.
- The `/us/sComp/{c}/{n}` prefix of a compilation is matched to a law by the
  `/us/pl/{c}/{n}` alias, or by (congress, chapter) for acts before 1901.
