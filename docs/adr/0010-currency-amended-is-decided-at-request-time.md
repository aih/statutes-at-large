# ADR-0010: `currency.amended` is decided at request time from three indexes

Date: 2026-09-08. Status: accepted. Implements design section 4's
`currency.amended` table; records what the implementation settles.

## Context

Design section 4 gives three kinds of evidence for `known_amended`: a US Code
source credit that cites this section and lists a later law; "a classification
row naming this law's section as amended"; a compilation current through a
later law whose section text differs. A classification row names the *amending*
law and its section (`118-35 §101(3) → 18 U.S.C. 3551 nt`), so no row ever
names an earlier law's section as amended; the second kind needs a rule, and
decision 3 below is it: the rows of this law's section name the US Code
sections it was classified to, and a row of a later public law on any of those
sections, with an action other than `new`, is the evidence
(`Repository.classification_amendments`).

## Decisions

1. **Nothing is precomputed.** `api/currency.py` decides the status per
   request from `Repository.source_credit_evidence`,
   `classification_amendments`, `compiled_counterparts` and, when nothing
   fired, `index_coverage`. `enacted_dates` fills the dates of candidate laws
   the store holds. A US Code load, a classification mirror, or a compilation
   poll changes the answer on the next request.

2. **"Later than this law" is by number, then by date.** A candidate and the
   law compare on `(congress, number)` when both carry them and either the
   kinds agree or the congresses differ; otherwise on enactment dates;
   otherwise the candidate does not count. A public law and a private law of
   one congress are numbered in separate sequences, so that pair falls to
   dates. A candidate equal to the law under any alias never counts. `latest`
   is the candidate no other fired candidate is later than; the first wins an
   incomparable pair.

3. **A classification row with any action but `new` is an amendment.** A
   blank action is the tables' "amended"; `repealed`, `tr to` and note rows
   count. A `new` row of a later law on the same US Code section is not
   evidence about this unit.

4. **Compilation evidence for a section needs different text.** The
   counterpart's text and the enacted text are compared after whitespace is
   collapsed. For the law itself and for hierarchy nodes the compilation root
   is not comparable, and "current through a later law" alone fires.
   `labels` skips the comparison for every identifier: at label time
   compilation evidence is "current through a later law" alone.

5. **Hierarchy nodes use the law-wide evidence.** A title or division is
   judged on every section of the law; the sentence names the level.

6. **`unknown` is a private law or a law in no index.** `no_record` needs
   `index_coverage` to say the law is cited, classified, or inside a mirrored
   table's range, and `kind != 'pvtl'`. A private law with evidence that
   fired is `known_amended`.

7. **The codified alternative reads the index.** For a section or the law,
   the US Code sections whose source credits cite it follow the compilation's
   own `uscRef` identifiers, deduplicated, in identifier order, at most 20 in
   all (ADR-0007, decision 4).

## Consequences

- A section response makes up to five repository calls for `currency` (the
  three evidence calls, `enacted_dates` when a candidate has no date,
  `index_coverage` when nothing fired) and one `get_comp_unit` per compiled
  counterpart. `labels` makes the same calls per identifier without
  `get_comp_unit`.
- `latest` is `{pl, identifier, label, enacted}`; `pl` is null for an act and
  `enacted` is null when no index and no loaded law records a date.
- A section repealed and restated into positive law (36 U.S.C. § 70902 from
  the 1950 Future Farmers of America charter) is cited only in a revision
  note, so it is `no_record`, and the note says amendment may still have
  occurred.
- Over the fixtures: the Sherman Act's section 1 is `known_amended` by
  `source_credit` and `compilation` with `latest` Public Law 108-237;
  `/us/pl/81/740/s3` (cited in notes only) is `no_record`; `/us/pvtl/81/375`
  is `unknown`.
