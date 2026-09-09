# The compilations session: the compiled answer's weight and the bare prefix

Date: 2026-09-09. The prompt for a separate session in its own worktree.
Package A of `2026-09-09-reader-improvements-plan.md` fixed the enacted
side (ADR-0019) and left the compiled side to the session that owns
`ingest/comps.py`, `api/comps.py` and the compiled repository methods.

## Measured on the live site, 2026-09-09 evening

| Request | Bytes | Time | `text` |
|---|---|---|---|
| `GET /api/v1/us/sComp/74/271` (Social Security Act, whole-act file) | 8,385,144 | 4.58 s | 8,331,000 characters |
| `GET /api/v1/us/sComp/83/703` (Atomic Energy Act) | 551,813 | 0.78 s | 547,622 |
| `GET /api/v1/us/sComp/83/703/tI` | 540,777 | 0.76 s | 534,145 |
| `GET /api/v1/us/sComp/83/703/tI/ch1./s1` | 3,021 | 0.31 s | 653 |
| `GET /api/v1/us/sComp/78/410` (Public Health Service Act, no whole-act file) | 3,643 | 0.31 s | the title XXXII file, marked repealed |

`_comp_root_result` sets `text=plain_text(_root(version.xml))` over the
whole compilation on every request, and the hierarchy branch of
`_comp_unit_result` cuts the node from `version.xml`; `CompVersion.xml` is
an eager column, so every `CompVersion` row read loads it.

## The prompt

Build the compiled side of ADR-0019 and settle the bare prefix of a
compilation served title by title, in the repository
statutes-linkedlegislation, in this worktree, on this branch.

Read first: `CLAUDE.md`, `~/.claude/CLAUDE.md` (prose), `BUILDLOG.md` (the
entries of 2026-09-09, in particular "the COMPS walk ends; its failures
documented" and "the reader improvements"), `docs/adr/0001`, `0007`, `0019`,
`0023` (the compiled documents in the search index), `db/models.py`
(`Comp`, `CompVersion`, `CompUnit`), `storage/repository.py`
(`CompUnitResult`, `CompRef`, `CompVersionRef`, the `Repository` protocol's
compiled methods), `storage/postgres.py` (`get_comp_unit`, `_version_of`,
`_comp_root_result`, `_comp_unit_result`, `_comp_children`, `_comps_of`,
`compilations_for_law`), `api/comps.py` (`compiled_response`, the routes,
the ETag), `api/schemas.py` (`CompUnitOut`, `CompilationOut`,
`VersionRefOut`), `api/routes.py` (`enacted_unit`, how `wanted` is
negotiated and passed to `get_unit` since ADR-0019), `params.py`
(`compiled_note`, `negotiated_format`), `ingest/comps.py` (what a version
row holds), `ingest/search_sync.py` (`comp_documents` selects columns by
name and never `CompVersion.xml`: keep it so), `tests/test_comps_api.py`,
`tests/test_comps_loader.py`, `tests/test_comps_parser.py`,
`tests/fixtures/comps/`, `docs/verification/README.md` (the Statute
Compilations section), `docs/plans/2026-09-08-reader-contract.md` (the
`/app/us/sComp/…` section), `frontend/src/pages/us/sComp/[...identifier].astro`
and `frontend/src/components/CompUnit.astro` or whatever renders the
compiled page (the reader renders a section from `format=xml` and prints
`note` verbatim; it must not change).

Then, with `make test`, `make test-web` and `make test-e2e` over `make dev`
green after each step:

1. The compiled answer stops carrying the whole compilation's text.
   `CompVersion.xml` becomes `mapped_column(Text, nullable=False,
   deferred=True)` (no migration). `Repository.get_comp_unit` takes
   `wanted: str = "json"` like `get_unit`; `api/comps.py` negotiates the
   format before calling it and passes it down. `_comp_root_result` and the
   hierarchy branch of `_comp_unit_result` set `text=""` and read
   `version.xml` only for `wanted == "xml"`. A section keeps its stored
   `xml` and `text`; a provision is still cut from the section.
   `CompUnitOut.text`'s description says it is empty for `compilation` and
   for a hierarchy level. The ETag keeps using the stored `content_hash`.
   Check every other reader of `CompVersion.xml` in `storage/` and `api/`
   (`_version_of`, `compilations_for_law`, the alternatives, the citation
   redirector) and make sure none loads it for a JSON answer: a deferred
   column loads on attribute access, so grep for `.xml` on version objects.
   Tests over SQLite: `text == ""` and `xml == ""` on a compilation root
   and on a title node for JSON, populated for `wanted="xml"`, and
   non-empty on a section; `tests/test_architecture.py` stays green.
   Amend ADR-0019 with a "Compiled" section rather than filing a new ADR;
   the reader contract's compiled section says `text` is empty above a
   section.

2. The bare prefix of a compilation served title by title. The Public
   Health Service Act has one COMPS file per title and no whole-act file
   (COMPS-77777777 is the whole act with empty law slots and is not
   loaded; BUILDLOG "the COMPS walk ends"); `get_comp_unit` answers
   `/us/sComp/78/410` from `versions[0]`, the title XXXII file, marked
   repealed. Decide the rule and record it as an amendment to ADR-0007:
   the candidates are (a) answer the root with `level: "compilation"`,
   `heading` the display title with the title suffix removed, `children`
   the top-level units of every per-title file in title order (each
   `partial_of` file's root units, ordered by the file's title number), and
   a `note` sentence from `params.py` saying the act is served in N files
   by title; or (b) redirect the bare prefix to the first title's file and
   say so in the note. Prefer (a) if `children` can be built without
   loading any `xml`; measure `/api/v1/us/sComp/78/410` and
   `/app/us/sComp/78/410` on the dev database, where the Social Security
   Act's title II fixture (COMPS-8755) is a per-title file with no
   whole-act sibling, so `/us/sComp/74/271` on the fixture database is the
   test case.

3. The 10 packages that fail on every poll are documented in
   `docs/verification/README.md`; change nothing about them unless step 2
   makes COMPS-77777777 loadable without special cases, in which case say
   so in the ADR and leave the load itself for a later session.

4. Docs: ADR-0019 and ADR-0007 amended; the reader contract; README's
   compilation section; a BUILDLOG entry; CLAUDE.md's ADR list if a new
   ADR is filed. Verification counts stay generated.

Conventions: `api/` talks only to the `Repository`; SQL in `storage/` and
`ingest/` only; the reader prints the API's sentences verbatim and every
new sentence is built in `params.py`; pytest over SQLite with the committed
fixtures; commit messages in the style of `git log` with the attribution
lines the session gives you; prose per `~/.claude/CLAUDE.md`. Ports 8001,
4321 and 5434 are `make dev`'s; do not start a second OpenSearch (9200 is
the US Code site's dev cluster, 9201 this site's). A push to `main`
deploys within three minutes: push once, when everything is green, and
then measure on the box.

Acceptance, measured on the box after the push: `GET
/api/v1/us/sComp/74/271` under 300 KB and 1 s (from 8.4 MB and 4.6 s);
`GET /api/v1/us/sComp/83/703/tI` under 100 KB; `/app/us/sComp/74/271` and
`/app/us/sComp/83/703/tI/ch1./s1` render as before; `/us/sComp/78/410`
answers the rule step 2 chose; `make test`, `make test-web`, `make
test-e2e` green; the axe scan clean on a compiled page.
