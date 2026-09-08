# ADR-0006: A restated act stays inside its amending section

Date: 2026-09-07. Status: accepted. Qualifies design section 4's example.

## Context

The design's example resolves `/us/pl/83/703/s1` to `/us/pl/83/703/tI/ch1/s1`,
the Atomic Energy Act of 1954's own section 1. In the volume USLM (68 Stat.
919), Public Law 83-703 has three sections; its section 1 amends the Atomic
Energy Act of 1946 "to read as follows" and the whole 1954 act, titles,
chapters and 117 sections, is `quotedContent` inside that section. The
Sherman Act and most laws are not like this; restating amendments are.

`<section>` inside `quotedContent` is text of another act and is never a unit
of the enacting law (the US Code site's ADR-0005; here 358 such sections in
vol 64 and 591 in vol 124 are amendments to other laws, quoted). Treating the
restatement's sections as units of PL 83-703 would need a rule that tells a
full restatement from an ordinary quoted amendment, and the volume USLM does
not mark the difference.

## Decision

The enacted view keeps the rule: PL 83-703 has sections 1, 2 and 3, and
`/us/pl/83/703/s1` is the amending section, whose XML and text carry the
restated act. The restated act's own sections are addressable in the compiled
view, `/us/sComp/83/703/tI/ch1./s1`, which is what the House compilation
numbers them by; `enacted_counterpart` of that compiled section is the
amending section 1, and the note says which section is served.

## Consequences

- A US Code source credit of the form `Aug. 30, 1954, ch. 1073, § 2, 68 Stat.
  921` resolves to `/us/pl/83/703/s2` of the amending act, not to the restated
  section 2. The compiled alternative on that answer points at the right text.
- Addressing restated sections in the enacted view is left to the reprocessing
  run (OCR plan, WP12), which builds the USLM and can mark a restatement.
