# Stage 5 prompt

Paste from the line after the rule into a fresh session started in
`statutes-linkedlegislation`.

---

Build stage 5 of ../statute-pdf-to-xml/docs/plans/2026-09-07-statutes-api-design.md in this
repository (statutes-linkedlegislation, https://github.com/aih/statutes-at-large): the reader
at `/app`, the citation parser behind `GET /api/v1/cite`, and the US Code site integration.
Stages 1 to 4 are done and pushed to `main`: read CLAUDE.md, README.md, BUILDLOG.md,
docs/adr/0001 to 0013, then the design in full (sections 3, 4, 5 and 7 are the contract for
this stage; section 1 says what the US Code site does today with a `/us/pl/`, `/us/stat/` or
`/us/act/` ref, and section 7 is the change that stage makes there), then citation.py (the
`/us/…` redirector: a browser is already sent to `/app/us/…`, which the proxy answers with a
503), deploy/Caddyfile, docker-compose.yml, api/routes.py, api/comps.py, api/cited_by.py,
api/schemas.py (`UnitOut`, `CompUnitOut`, `StatPageOut`, `LawSummaryOut`, `CitedByOut`),
params.py (`served_note`, `enacted_note`, `amended_sentence`: the reader says the same
sentences), storage/identifiers.py (`parse_identifier`, `law_label`, `long_date`), and
uslmtext.py. Then, in the sibling repository ../uscode-redesign, read docs/adr/0010 (reader
and API behind a redirecting citation URL), 0011 (Astro 5 + TypeScript + USWDS at `/app`,
SSR on Node behind Caddy), 0015 (the typed USLM renderer, `frontend/src/lib/uslm.ts`), 0023
(`citeparse.py`: a pure citation parser, `GET /api/v1/citation?q=`, three failure shapes,
`/app/goto`), 0029 (rate limits), 0074 (version transitions attributed to public laws), and
`frontend/src/lib/refs.ts` (`resolveRef`, `citedIdentifiers`), `frontend/src/lib/api.ts`
(`labels` batched at 100), `frontend/src/components/Timeline.astro`, and
`frontend/src/pages/us/usc/[...identifier].astro`. Keep the conventions: the API has no
frontend dependency and `api/` imports nothing from the reader; one `Repository` protocol, no
SQL outside storage/ and ingest/; the citation parser is pure, in its own module, and its
accepted-forms table runs in `make test` with no database; notes and cache headers in
params.py; pytest over SQLite with the committed fixtures; a Makefile target per step; an ADR
for every decision that departs from the design or from the US Code site's conventions.
Prose follows ~/.claude/CLAUDE.md.

Inputs (measured 2026-09-08):

- The API. `/api/v1/us/pl/{c}/{n}[/{path}]`, `/us/pvtl/…`, `/us/act/{date}/ch{n}[/{path}]`
  answer a unit (`identifier`, `served_identifier`, `resolution`, `law` with `source`,
  `currency` with `amended`, `alternatives`, `note`, `provenance`, `pages`, `text`, `xml_url`,
  `level`, `num`, `heading`, `ancestors`, `children`, `provision`, `occurrences`);
  `?format=xml` returns the stamped USLM element (a provision alone below a section);
  `/us/sComp/…` answers the compiled shape with `version`, `pinned`, `usc_refs`; `/us/stat/
  {vol}/{page}` lists the documents on a page; `/laws/{c}/{n}` gives the table of contents,
  compilations and `sources`; `/comps?law=&q=`; `/cited-by?identifier=` (60 requests then 2
  a second per address); `/labels` (300 then 30 a second); `/status`. Loaded in the dev
  Postgres on :5434: volumes 26, 64, 68, 72, 124, 137; the 113th to 119th Congresses from
  PLAW (2,149 laws); six COMPS packages; the citation index (1,081,463 rows); the
  classification mirror (144,885 rows). The compose stack on :8010 (Caddy → api:8001) is
  up; `handle /app*` answers 503.
- The US Code site's reader is Astro 5 with `@astrojs/node` SSR on port 4321, USWDS 3, no
  client JS by default, Playwright and axe for e2e, `vitest` for units, and a `frontend`
  compose service the proxy sends `/app*` to. Node 24 is on this machine. Its
  `refs.ts` sends `/us/stat/{v}/{p}` to `https://www.govinfo.gov/link/statute/{v}/{p}`,
  `/us/pl/{c}/{n}` to `…/link/plaw/{c}/public/{n}` for the 104th Congress onward, and
  renders every other `/us/pl/`, `/us/pvtl/`, `/us/act/` ref as plain text; its `labels`
  call takes `/us/usc/` identifiers only (`citedIdentifiers` drops the rest). Its
  `Timeline.astro` links each amending law to the classification page, not to the law.
  Its `citeparse.py` and ADR-0023 are the model for the parser here: pure module, 84-case
  table, `422` for a non-citation, `200 exists:false` for a well-formed citation that names
  nothing loaded, a plain GET form at `/app/goto?q=`.
- Citation forms the parser has to accept, from design section 5 and the source credits
  the index holds: `Pub. L. 104-333, § 814`, `Pub. L. 104–333, title VIII, § 814(e)(1)`,
  `Public Law 118-5`, `P.L. 81-740`, `110 Stat. 4196`, `64 Stat. 563`, `Act of Aug. 25, 1916,
  ch. 408`, `Aug. 30, 1954, ch. 1073, § 2`, `ch. 823, 64 Stat. 563`, `Private Law 81-375`,
  and `43 U.S.C. 1701` / `16 USC 45f(c)(5)` (a US Code citation answers with the US Code
  site's URL, `USCODE_ORIGIN` from `.env`, and is not resolved here). A law from 1901 to
  1957 cited by chapter resolves through its `/us/act/` alias (ADR-0002); a Stat. page
  resolves to `/us/stat/{vol}/{page}` and the reader shows the documents on it.

Sequence and delegation:

1. Yourself: the citation parser (`citeparse.py`, pure, the accepted-forms table in
   `tests/test_citeparse.py`, at least 60 cases including the ones above, en dash and
   hyphen, `§`/`sec.`/`section`, subsection paths kept in their case), `GET /api/v1/cite?q=`
   in `api/cite.py` (parse, then `Repository.labels` or `stat_page` for existence; 422 /
   `exists:false` / `exists:true` with `identifier`, `served_identifier`, `url`, `label`,
   `kind`; a US Code citation answers `kind: "usc"` with the US Code site's URL and no
   existence check; `max-age=300`; a person's rate limit, 60 then 2 a second), the note
   and the 422 detail wording in params.py, the route in README's table, and the reader's
   contract: every JSON the reader needs is already served, so list in
   `docs/plans/2026-09-08-reader-contract.md` which routes each page calls and what it
   shows, including the exact sentences (`note`, the compiled explanation, the currency
   line) it prints verbatim from the API. Commit before delegating.
2. Two subagents in worktrees, neither editing `api/`, `storage/`, `db/` or `params.py`:
   (a) the reader: `frontend/` (Astro 5 + TypeScript + USWDS, SSR on Node, `/app` base,
   consuming `/api/v1` through one typed client; pages: `/app/` (what is loaded, from
   `/status`, and the citation box), `/app/goto?q=` (the box's target: 307 on a hit, the
   three failures otherwise, no JavaScript), `/app/us/pl/…`, `/app/us/pvtl/…`, `/app/us/act/
   …` (the law: title, dates, citation, `sources`, table of contents; a section or a
   provision: the text rendered from `?format=xml` by a typed USLM renderer ported from the
   US Code site's `uslm.ts`, the note, the currency line, the alternatives as links, the
   Stat. pages with govinfo links, the ancestors as breadcrumbs, previous/next section,
   cross references resolved by `refs.ts` rules with `/us/usc/` refs sent to the US Code
   site and `/us/pl/`, `/us/act/`, `/us/stat/` refs kept on this site when `labels` says
   they exist), `/app/us/sComp/…` (the compiled view with the version picker `through=` and
   the enacted counterpart link), `/app/us/stat/{vol}/{page}` (the documents on the page), a
   "cited by" panel on a law and a section from `/cited-by`; `provenance` shown on every
   unit; the sentences printed verbatim from the API, never rephrased); a `frontend`
   compose service and the Caddy `handle /app*` block pointing at it; `make dev` starting
   both; `vitest` units for the renderer and the ref rules, Playwright e2e over the compose
   stack marked so `make test` does not need Node; axe on the section page.
   (b) the US Code site integration, in ../uscode-redesign on a branch (do not push it):
   `refs.ts` links `/us/pl/`, `/us/pvtl/`, `/us/act/`, `/us/stat/` refs to
   `https://statutes.linkedlegislation.org{href}` when this site's `POST /api/v1/labels`
   says `exists`, with the hover label from the same call, govinfo as the fallback for
   `false` and plain text below the 104th Congress when nothing answers; the batched call
   goes to `STATUTES_ORIGIN` from that site's environment, at most 100 per request, cached
   as its own `labels` are, and skipped without error when the origin is unset or the call
   fails; `Timeline.astro` links each `laws[]` entry to `/us/pl/{c}/{n}` and, when
   `pl_section_raw` parses, to the section, with `?view=enacted`; a "cited by" panel on a
   US Code section is not this stage (design section 7's third bullet is the statutes
   site's panel, built in (a)). Tests with that site's vitest and its `respx`-equivalent
   for the labels call; that site's `make test` green; report the diff and leave the branch
   for review.
3. Yourself: merge (a), build the compose stack with the frontend on :8010 and check
   `/app/us/pl/81/740/s3` (rule 4 alias too: `/app/us/act/1950-08-30/ch823/s3`),
   `/app/us/pl/118/22/s101` (the section-number note), `/app/us/pl/118/5/dA/tI/s101/a` (a
   provision), `/app/us/sComp/83/703/tI/ch1./s1`, `/app/us/stat/137/112`, `/app/goto?q=110
   Stat. 4196`, and a 422 from the box; run axe on one of each; record what (b) changed in
   the sibling repository and how it was verified; write the ADRs (the reader's stack and
   what it prints verbatim; the citation parser's forms and failures; the cross-site link
   rule in both directions), BUILDLOG and README ("Not yet served" loses the reader and the
   parser; the routes table gains `cite`; a "Reader" section names the pages), then commit
   and push.

Constraints: nothing in `make test` needs Node, a browser, a database, or the network; the
reader has no build-time dependency on the database and reads only `/api/v1`; the API keeps
zero frontend dependencies and `tests/test_architecture.py` proves the parser imports no
storage, db, fastapi or sqlalchemy; never write a token into source; the sibling repository
is changed on a branch and not pushed. Report faithfully at the end of each step: what
passed, what failed with the output, what was skipped.
