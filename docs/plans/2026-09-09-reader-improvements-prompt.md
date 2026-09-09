# Reader improvements prompt

The plan is `docs/plans/2026-09-09-reader-improvements-plan.md`. Paste the
text after the rule into a fresh session started in
`statutes-linkedlegislation`. The session orchestrates; the packages build
in worktrees on the models the plan names.

Before starting: check that the COMPS walk on the box has finished
(`systemctl is-active statutes-comps-walk` is inactive, or the log says the
walk is complete). A push to `main` deploys, and the session pushes once
per wave.

---

Build docs/plans/2026-09-09-reader-improvements-plan.md in this repository
(statutes-linkedlegislation): six packages, A to F, in three waves. Read
first: CLAUDE.md, BUILDLOG.md (the last entry), the plan in full,
docs/plans/2026-09-08-reader-contract.md, docs/adr/0001, 0011, 0014, 0016,
0017 and 0018, frontend/src/layouts/Base.astro,
frontend/src/components/UnitPage.astro, frontend/src/lib/unitpage.ts,
frontend/src/lib/uslm.ts, frontend/src/pages/us/stat/[volume]/[page].astro,
api/routes.py, api/responses.py, api/schemas.py, storage/postgres.py
(`_law_result`, `_unit_result`, `stat_page`), uslmtext.py,
ingest/statute.py (`_walk_units`), db/models.py, docker-compose.yml,
docker-compose.prod.yml, deploy/update-sources.sh, deploy/deploy-on-box.sh.
In ../uscode-redesign read only what the plan names per package: ADR-0028,
0031, 0046, 0051, 0055, 0060, 0061; frontend/src/lib/shortcuts.ts,
frontend/src/components/KeyboardNav.astro, ShortcutsDialog.astro,
ChapterRail.astro; frontend/src/styles/site.scss (the sticky stack and the
rail); frontend/tests/jsbudget.test.ts; frontend/src/pages/goto.astro and
search.astro; api/search.py, storage/search.py, storage/searchquery.py,
ingest/search_sync.py, ingest/reindex_search.py, docker-compose.yml (the
opensearch service). Prose follows ~/.claude/CLAUDE.md.

Run each package as a subagent in its own worktree
(`isolation: "worktree"`) on the model the plan's wave table names, with
the package's section of the plan and its file list as the brief. Wave 1
is A, B1 and E1 to E3 in parallel; wave 2 is C, then B2 and E4; wave 3 is
D, then F. Merge each branch into `main` locally in that order, run `make
test`, `make test-web` and `make test-e2e` over `make dev` after each
merge, and push once per wave. Do not touch ingest/comps.py, api/comps.py,
the compiled repository methods or the box's `.env`: another session owns
the compilations load.

Keep the conventions: `api/` talks only to the `Repository`, SQL in
`storage/` and `ingest/` only; the reader reads `/api/v1` and prints the
API's sentences verbatim; the citation parser stays pure; notes and cache
headers in params.py; pytest over SQLite with the committed fixtures; a
Makefile target per new command; an ADR per departure (0019 to 0023 are
named in the plan); a BUILDLOG entry for the session; verification counts
generated, not edited. The search cluster in production is the US Code
site's, reached over that project's network: nothing in ../uscode-redesign
changes, and `SEARCH_PASSWORD` is typed by the user into `.env` on the box
in their own SSM session. When the box needs a hand from the user (the
password, the network name), print the command and stop for it.

Finish with the acceptance list at the end of the plan measured on the
box, and report each line with its number.
