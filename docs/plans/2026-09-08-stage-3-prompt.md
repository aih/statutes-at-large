# Stage 3 prompt

Paste from the line after the rule into a fresh session started in
`statutes-linkedlegislation`.

---

Build stage 3 of ../statute-pdf-to-xml/docs/plans/2026-09-07-statutes-api-design.md in this
repository (statutes-linkedlegislation, https://github.com/aih/statutes-at-large): the
`citations` table from the `dreamproit/uscode` dataset, the `classifications` mirror,
`GET /api/v1/cited-by`, and `currency.amended.status` from evidence. Stages 1 and 2 are done
and pushed: read CLAUDE.md, README.md, BUILDLOG.md, docs/adr/0001 to 0007, and
docs/verification/README.md first, then the design in full (sections 4, 5 and 6 are the
contract for this stage), then the US Code site's plan for the same index,
../uscode-redesign/docs/citation-index-plan.md, and its ADR-0067 and ADR-0074 (what a
classification row is, and how a law is attributed to a text change). Keep the conventions:
one `Repository` protocol, no SQL outside storage/ and ingest/, notes and cache headers in
params.py, pytest over SQLite with fixtures of real source data, a Makefile target per step,
an ADR for every decision that departs from the design.

Inputs:

- `dreamproit/uscode` on the Hub, config `current` (65,938 rows, three parquet shards,
  ~190 MB; columns `identifier`, `xml`, `source_credit`, `notes`, `release_label`,
  `release_seq`, `content_hash`, `text_since`; the card lists the rest). The `xml` column is
  the section's verbatim USLM; every cross reference in it is a `<ref href="…">`. Read the
  shards with pyarrow in a `dataset` dependency group (as ../uscode-redesign/pyproject.toml
  does); do not add `datasets` or `huggingface_hub` to the API image.
- OLRC's classification tables, mirrored from the US Code site's API rather than scraped
  again: `GET https://uscode.linkedlegislation.org/api/v1/classifications/tables` lists the
  documents; `…/classifications/tables/{congress}/{session}/entries?sort=pl&page=…` pages one
  document's rows; `…/classifications/pl/{congress}/{law_num}` is one law's rows. A row
  carries `pl_congress`, `pl_num`, `pl_section_raw` (`'101(3)'`, `''` for the whole law),
  `usc_identifier`, `is_note`, `action` (`''` amended, `new`, `repealed`, `tr to`, …),
  `stat_volume`, `stat_page_labels`. That API is rate limited (burst 120, 10/s) and public;
  send a descriptive User-Agent and page sequentially. No key is needed.
- The enacted and compiled units already loaded (volumes 26, 64, 68, 72, 124, 137 and six
  COMPS packages in the dev Postgres on :5434; the slices in tests/fixtures/).

Sequence and delegation:

1. Yourself: the schema (`citations`, `classifications`, `classification_source_checks`, an
   Alembic migration under db/migrations), the `Repository` methods the evidence needs
   (`citations_to(identifier_prefix)`, `classification_rows(law, section_num)`,
   `amendment_evidence(law, section_num)` or the shape you decide), and the `citations`
   loader: `python -m ingest citations --from-hub | --from-dir PATH` reading the `current`
   shards, extracting every `ref/@href` that starts with `/us/pl/`, `/us/pvtl/`, `/us/act/`
   or `/us/stat/` with its context (`sourceCredit`, `note`, `text`, decided from the ref's
   ancestors in the XML) and the row's `release_label`; idempotent per release label (a new
   dataset export replaces the rows of the old label). Count what the index holds per
   context and per target kind, and write `docs/verification/citations.json`. Then commit
   before delegating. Test fixture: a small parquet file cut from the `current` shard
   holding the rows whose `source_credit` cites the laws in the loaded slices (Public Law
   81-740, 83-703, 85-910, 111-344, 118-22, 118-34, the Sherman Act by `/us/act/1890-07-02/ch647`)
   plus 16 U.S.C. § 45f; write the cutter as scripts/extract_citations_fixture.py.
2. Two subagents in worktrees, each writing its own tests, neither editing storage/, db/ or
   params.py (they report the change they need instead):
   (a) the classifications mirror: `python -m ingest classifications [--congress N]
   [--from-dir PATH]` over the US Code site's API with a check row per run
   (ADR-0036's shape from ../uscode-redesign: a row on success and on failure), keyed
   `(pl_congress, pl_num, pl_section_raw)`, plus `GET /api/v1/cited-by?identifier=…`
   (design section 5: US Code sections whose source credits or notes cite this unit, with
   the release label checked; rule 2's prefix logic applies, so `cited-by` for a law lists
   what cites any of its sections; rate limit sized for a person; `max-age=300`; ETag).
   Test fixture: verbatim JSON pages saved from the live API for the 118th's second
   session and the 104th (a few dozen rows each), with the key-free URL recorded in a
   comment.
   (b) `currency.amended` from evidence, design section 4's table, in one module
   (api/currency.py or storage-side if it needs SQL): `known_amended` when a US Code source
   credit that cites this section lists a later law, or a classification row names this
   law's section with an action other than `new`, or the compiled counterpart is current
   through a later law and its normalized text differs from the enacted text;
   `no_record` when the indexes cover the law's era and nothing matched; `unknown` when
   they do not (private laws, acts before the 104th Congress with no citation rows). `latest`
   is the newest law among the evidence with its enactment date when known; `evidence`
   lists which of `source_credit`, `classification`, `compilation` fired. The note's
   amended sentence follows: design section 4's "{amended sentence}" for each status,
   replacing `params.amended_unknown_sentence`. Labels' `currency` carries the same block.
3. Yourself: merge, resolve the note wording once in params.py, load the full `current`
   config and the classification tables for the 104th to 119th Congresses into the dev
   Postgres, record the counts in docs/verification/, run the compose stack on :8010 and
   check `/api/v1/us/pl/83/703/s1`, `/api/v1/us/act/1890-07-02/ch647/s1` and
   `/api/v1/cited-by?identifier=/us/pl/104/333/s814`, write the ADRs (the evidence rules,
   the mirror-through-the-site decision, anything that departs), BUILDLOG, README ("what
   is served" gains `cited-by` and `amended.status`), then commit and push.

Constraints: nothing in tests touches the network (respx for the classification client;
committed parquet and JSON for the rest); the Hub download and the classification mirror
are Makefile targets (`make citations`, `make classifications`) that are not part of
`make test`; never write a token into source. `GOVINFO_API_KEY` in .env is only for the
COMPS poller and is not needed for this stage.

Report faithfully at the end of each step: what passed, what failed with the output, what
was skipped. Deliverables: tests green under `make test`, docs/verification counts for the
citation index and the classification mirror, the README and ADRs updated, and the branch
pushed to origin.
