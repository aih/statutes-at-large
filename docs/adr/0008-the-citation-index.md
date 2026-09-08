# ADR-0008: The citation index is built from the `current` config, one row per ref, replaced per title

Date: 2026-09-08. Status: accepted. Implements design section 6 (`citations`)
and departs from its ingest line ("from `dreamproit/uscode` (`versions`
config) on each new release point").

## Context

The US Code site's `docs/citation-index-plan.md` designs an index keyed by
section *version* so that "what cites X at release R" is answerable for every
release point. This site needs the reverse question at the current text only:
which US Code sections cite a law or a section of it, and what those sections'
source credits say about later laws. The `current` config of
`dreamproit/uscode` is 65,938 rows (one per section at the newest release
point of its title, ~190 MB); the `versions` config is 489,738 rows (3 GB).

## Decisions

1. **Source: the `current` config.** One row per US Code section. Each title
   carries its own release label (`119-102not101` for title 16, `119-83` for
   title 10), and a few sections inside a title carry an older label. The
   label is stored on every row and reported on every `cited-by` answer, which
   is what "with the release point checked" means here. Per-release answers
   are the `versions` config's job and are not built.

2. **One row per ref, every context.** Every `<ref href>` whose target starts
   with `/us/pl/`, `/us/pvtl/`, `/us/act/`, or `/us/stat/` is a row, with
   `context` (`sourceCredit`, `note`, `text`) from the nearest enclosing
   element and `note_topic` from the note's `topic`. Refs to `/us/usc/` are
   counted in the report and not stored. The revision notes of positive-law
   titles hold XHTML tables whose citations are `<a href>` rather than `<ref>`;
   those are rows too (`Aug. 30, 1950, ch. 823, § 3` under 36 U.S.C. § 70902).

3. **The target is parsed into law and section number at load.**
   `/us/pl/104/333/dI/tVIII/s814/e/1` and `/us/pl/104/333/s814` both index
   under (`/us/pl/104/333`, `814`), so a section is matched by number whatever
   hierarchy the citing text wrote (design section 3, rule 3), and a law is
   matched through every alias it answers to (ADR-0002: the Code cites the
   Atomic Energy Act of 1954 as `/us/act/1954-08-30/ch1073`). An act cited by
   date alone (`/us/act/1934-06-18/s3`, no chapter) is kept under the date and
   matches no alias. `/us/stat/68A/…` and `/us/stat/70A/…` (the lettered
   volumes) do not parse and are stored verbatim with no law.

4. **A public law's date comes from the text.** A `<date>` that immediately
   follows a law ref with only punctuation between (`Pub. L. 95–625, § 314,
   <date>Nov. 10, 1978</date>`) is the law's enactment date and is stored as
   `to_date`; a date further on in prose is not. An act's date is in its
   identifier.

5. **Rows are replaced per citing title.** A load deletes every row whose
   citing section is in a title the export holds, then inserts the export's
   rows, committing every 20,000 rows. Re-running over the same export leaves
   the same rows. A `source_checks` row with collection `USCODE` records the
   run and the dataset revision (the Hub commit sha).

## Consequences

- `Repository.cited_by` answers for a law, a section, a path below a section,
  a hierarchy node (refs written with that hierarchy only), or a Stat. page,
  paged over distinct citing sections, with counts per context and the
  release labels seen.
- `Repository.source_credit_evidence` returns, per citing source credit, every
  law the credit names in order, which is what `currency.amended` reads
  (ADR-0010).
- The full `current` config loads in about a minute; the counts are in
  `docs/verification/citations.json`.
