# ADR-0010: `currency.amended` is decided from three indexes, and the classification rule is a join

Date: 2026-09-08. Status: accepted. Implements design section 4's table and
settles what it leaves open.

## Context

Design section 4 gives three kinds of evidence for `known_amended`: a US Code
source credit that cites this section and lists a later law; "a classification
row naming this law's section as amended"; a compilation current through a
later law whose section text differs. A classification row names the *amending*
law and its section (`118-35 §101(3) → 18 U.S.C. 3551 nt`), so no row ever
names an earlier law's section as amended; the second kind needs a rule.

## Decisions

1. **source_credit.** `Repository.source_credit_evidence` returns every US Code
   section whose source credit cites this section (through every alias, by
   section number) and the laws that credit names in order. A credit that
   names a law later than this one is evidence; the later law is a candidate
   for `latest`, with the date the credit gives it (ADR-0008, decision 4).

2. **classification is a join.** The rows of this law's section name the US
   Code sections it was classified to. Rows of *later* public laws that
   classify to any of those sections, with an action other than `new`, are
   evidence that the codified text was amended since
   (`Repository.classification_amendments`). Note rows and the table's blank
   action (amended) count; `new` does not.

3. **compilation.** A compiled counterpart (ADR-0007, decision 4) current
   through a later law, whose section text differs from the enacted text after
   whitespace normalization, is evidence. At law level the root's text is not
   comparable and "current through a later law" alone fires. In `labels` the
   text comparison is skipped.

4. **"Later" is by (congress, number) when both sides have them, else by date.**
   The chapter alias of a numbered law is the law itself. A candidate that can
   be ordered neither way does not fire.

5. **`no_record` needs the indexes to know the law**: a citation row targets
   it, a classification row has it as its public law, or a mirrored table's
   covered ranges include its number. Private laws and laws in none of the
   indexes are `unknown`.

6. **`latest`** is the newest firing candidate, `{pl, identifier, label,
   enacted}`; `evidence` lists the kinds that fired in the order above. The
   note's amended sentence per status is `params.amended_sentence`.

## Consequences

- An enacted section that itself amended the Code (most sections of a modern
  law) is `known_amended` when the Code section it touched was touched again
  later; the status is about the codified text derived from the section.
- A section repealed and restated into positive law (36 U.S.C. § 70902 from
  the 1950 Future Farmers of America charter) is cited only in a revision
  note, so it is `no_record`, and the note says amendment may still have
  occurred.
- The codified alternative of an enacted section now also names the US Code
  sections whose source credits cite it (ADR-0007, decision 4's deferral).
