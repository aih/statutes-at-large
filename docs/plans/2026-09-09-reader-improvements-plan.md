# Reader improvements: pages, weight, chrome, keys, search

Date: 2026-09-09. Planned against the live site (`statutes.linkedlegislation.org`),
the reader contract (`2026-09-08-reader-contract.md`), ADR-0014, and the US
Code site's reader (`../uscode-redesign`, its ADR-0028, 0031, 0046, 0051,
0055, 0061, 0062). Seven requests from the user; six work packages; a wave
plan and a model per package at the end.

## Measured on 2026-09-09

| Request | Live | Cause |
|---|---|---|
| `GET /api/v1/us/pl/117/328` | 4,748,777 bytes, 4.8 s | `text` is the whole law's plain text (4,548,249 characters), computed by parsing the 20 MB law XML on every request; `pages` lists 1,653 rows |
| `GET /app/us/pl/117/328` | 565,162 bytes, 4.0 s | waits on the JSON above; the HTML holds 1,653 page links and the full nested contents (thousands of entries) |
| `GET /api/v1/laws/117/328` | 291,278 bytes, 1.0 s | the whole reading-order `toc` |
| `GET /api/v1/us/stat/110/4196` | 459 bytes, 0.3 s | one document, `starts_here: false`, `unit_on_page: /us/pl/104/333/d1/tVIII/s814` |

The page the user cited holds Public Law 104-333 (the Omnibus Parks and
Public Lands Management Act of 1996), not 104-133.

The reader ships no client JavaScript (ADR-0014, decision 1). Packages C,
D and E introduce the first inline scripts; the US Code site's byte budget
(its ADR-0046) is ported with them.

The COMPS load runs in a separate session and on the box
(`statutes-comps-walk`). Nothing in this plan touches `ingest/comps.py`,
`api/comps.py`, the compiled repository methods or the box's `.env`; a push
to `main` deploys, so pushes wait until the walk log says it is complete.

## A. The law answer stops carrying the whole law's text

Request 2, the load time.

API and storage:

- `UnitOut.text` is empty for `level: "law"` and for hierarchy nodes. It
  stays on a section and on a provision. The description on the field says
  so. `CompUnitOut.text` follows the same rule for a compilation root and
  its hierarchy nodes.
- `Law.xml` and `CompVersion.xml` are `deferred` columns
  (`mapped_column(Text, deferred=True)`). `_law_result` and the hierarchy
  branch of `_unit_result` load the XML only when the caller asked for
  `format=xml` or the node has to be cut from it. Pass `wanted` down or
  split `get_unit` into the resolution and a `unit_xml(result)` call; keep
  `Repository` the only surface `api/` sees.
- `pages` on a law stays complete. Its JSON is about 150 KB on the largest
  law; the reader hides it behind a disclosure (package C).
- `unit_etag` still uses `content_hash`, which is stored, so the ETag does
  not change.

Tests: `tests/` gains a case per level asserting `text == ""` on a law and
a node and non-empty on a section; the SQLite suite runs the deferred
column. A timing assertion is not a unit test; the acceptance line is the
live measurement below.

Docs: ADR-0019 (the law answer carries no text; the XML is deferred). The
reader contract's "text" wording under the law page. `docs/api` examples
if any print a law's `text`.

Acceptance: `GET /api/v1/us/pl/117/328` under 300 KB and under 0.5 s on
the box; `GET /app/us/pl/117/328` under 1.5 s.

## B. A Statutes at Large page shows its own text

Request 1.

### B1. The API: the slice between two page markers

`GET /api/v1/us/stat/{volume}/{page}` gains, per document:

```
units: [{identifier, level, num, heading}]   the units the page touches, reading order
text: str                                     plain text of the slice
```

and answers `format=xml` with

```xml
<statPage identifier="/us/stat/110/4196" volume="110" page="4196">
  <slice law="/us/pl/104/333" from="/us/stat/110/4196" to="/us/stat/110/4197">
    …the USLM between the two markers, ancestors kept…
  </slice>
</statPage>
```

The slice, in `uslmtext.py` as `slice_between(root, start, end)`:

- The range starts at the `<page>` whose `identifier` names the page and
  ends at the next `<page>` element in document order, whichever page it
  names. When the law starts on the page, the preface carries the marker
  (`ingest/statute.py`, `_walk_units`); when no marker is found the range
  starts at the root. When no later marker exists it ends at the document's
  end.
- Walk `etree.iterwalk(root, events=("start", "end"))` with an `inside`
  flag: `start` of the start marker sets it, `end` of the end marker clears
  it. An element's `.text` is kept iff `inside` at its `start`; its `.tail`
  is kept iff `inside` at its `end`. An element is kept iff it, or any
  descendant, was inside; ancestors of kept elements are kept as
  containers. Work on a `deepcopy` walked in parallel with the original.
- Nested `<page>` elements inside `quotedContent` are markers too and end
  the range; the fixture in `statute-124-slice.xml` has 14 markers to test
  against.
- `units`: the `unit_on_page` (the marker's enclosing unit) first, then
  every unit of the law whose `first_page` equals the page, in `seq`
  order. A hierarchy node whose heading prints on the page is included
  from `Unit.first_page` the same way.

Cost: the law's XML is parsed per request. Cache the slice with
`functools.lru_cache(maxsize=256)` keyed on `(law.id, law.content_hash,
page)`. The stat page answer is already `immutable` with an ETag, so a
repeat from one reader is a 304. Measure `/us/stat/136/5000` (inside
Public Law 117-328); if the first hit is over 2 s, compute slices at load
time into a `stat_page_slices` table instead and record the change in the
same ADR.

Tests: the fixture database's `/us/stat/64/563` (Public Law 81-740 starts
there: the slice begins with the preface and ends at the marker for 564),
`/us/stat/64/564` (a mid-law page: begins at the marker, `units` names
section 3 and the sections starting on the page), a page shared by the
end of one law and the start of the next (find one in the 64 slice), and
`format=xml` well-formedness. `tests/test_architecture.py` stays green.

Docs: ADR-0020 (a printed page is served as the slice between its
markers). The reader contract under `/app/us/stat/{vol}/{page}`.

### B2. The reader: the stat page

`frontend/src/pages/us/stat/[volume]/[page].astro`, top to bottom:

1. `h1` `110 Stat. 4196`; the line with the GovInfo PDF link.
2. Previous and next page links (`/app/us/stat/110/4195`, `/4197`), the
   `Neighbors` component reused; numeric pages only (a lettered page such
   as `a12` has no arithmetic neighbour). A neighbour that no loaded law
   prints on answers 404 with the API's `detail`, which is the existing
   behaviour.
3. **Text on this page**: each slice rendered through `render()` from
   `lib/uslm.ts` inside `article.section-body`, headed by the law's label
   and title as a link to the law, then a line `Begins inside Sec. 814 —
   Read section 814 in full` built from `units[0]` and `unitLabel`, and one
   `Read … in full` link per further unit. When `units` is empty and
   `starts_here` is true the line is `Public Law 104-333 begins on this
   page`. `hrefs` from the slices go through `fetchLabels` as on a section
   page.
4. **Documents on this page**, the existing list, reworded per entry:
   `starts on this page` stays; `continues onto this page` becomes `begins
   at 110 Stat. 4093 and prints on this page` using `citation`. The
   `unit_on_page` sentence moves into section 3.
5. JSON, XML and the citation URL as on other pages.

Tests: `frontend/tests/uslm.test.ts` renders a `statPage` fixture cut from
the API; `tests/e2e/stat.spec.ts` asserts the slice, the `Read … in full`
link and the neighbours on `/app/us/stat/64/564`.

## C. Chrome: a sticky header, a rail, disclosures, top and bottom

Requests 2 (the pages and contents disclosures), 3, 4 and 5. All in
`frontend/`.

### C1. The header sticks

- `.site-header { position: sticky; top: 0; z-index: 500 }`. No ancestor
  of the header may carry `overflow` other than `visible`.
- Below 40em the header is one row: the brand and the search box;
  `.site-nav` is hidden there (the footer already links the API docs and
  the US Code site).
- `:root { --sticky-h }` measured per band and set in `site.scss` with the
  same comment discipline as the US Code site's: the value is what
  `scroll-margin-top` spends. `main`, every `[id]` inside `.section-body`,
  every `.panel[id]` and every `details[id]` get
  `scroll-margin-top: calc(var(--sticky-h) + 0.5rem)`.
- Print: the header does not stick.

### C2. The layout and the rail

- `Base.astro` wraps `main` in `.reader-layout`: one column below 64em; at
  64em and above `16rem minmax(0, 1fr)`, the rail first, sticky at
  `top: calc(var(--sticky-h) + 0.5rem)`, `max-height` to the viewport,
  `overflow-y: auto`, `overscroll-behavior: contain`. The wide reading
  wrap (`.reader-wrap--text`) keeps its sidenote margin; the rail sits to
  its left.
- `Rail.astro` takes two props from the page:
  - `sections: Link[]` — **On this page**: the page's own panels, in order,
    only those rendered: `#text`, `#contents`, `#pages`, `#sources`,
    `#about`, `#cited-by`, `#versions`. Every panel heading gains the `id`;
    `About this text` and `Cited by the US Code` already have `about-h`
    and `cited-by-h` and keep them as the targets.
  - `toc: TocNode[] | null` and `current: string | null` — **In this law**:
    the nested contents with `<details>` per hierarchy node. The branch
    holding `current` is open and `current` is marked `aria-current="page"`;
    every other node is closed. The rail's contents are bounded: hierarchy
    nodes always; sections only inside the open branch; a closed node
    lists nothing (its link is its page). When the law has at most 300
    units the rail lists everything. A section of a private law or an act
    has only the parent's `children` (the existing `parentChildren`), which
    is what the rail shows.
- Below 64em the rail renders after `main`'s content as a plain block
  (order 2), so nothing is lost and nothing is pinned.
- `CompUnit` pages pass `unit.children` and the version list heading.

### C3. Disclosures on the unit pages

- **Contents** on a law or node page: `<details id="contents"
  class="disclosure">` with `<summary>Contents — 45 units, 1,205
  sections</summary>` (counts from `summary.section_count` and the toc
  length), closed by default; the nested `TocList` inside.
- **Pages**: `<details id="pages" class="disclosure">` with `<summary>Stat.
  pages for this law — 1,653 pages, 136 Stat. 4459 to 6111</summary>`
  (first and last from `pages`), closed by default, the linked page list
  inside. On a section page (a handful of pages) the list prints open as
  now, under the same `id`.
- A fragment jump to a closed `details` opens it: one inline script in
  `Base.astro` on `hashchange` and load, the US Code site's ADR-0060
  pattern. This is the reader's first script; see C5.

### C4. Top and bottom

- `EndLinks.astro`: a fixed control at the lower right with two anchor
  links, `↑ Top` to `#main` and `↓ End` to `#site-footer`, plain anchors
  with `aria-label`s, visible at every width, hidden in print, 44px
  targets. The footer gains `id="site-footer"`.
- The keyboard counterparts `t` and `b` are package D.

### C5. The first scripts, and the budget

- ADR-0021 (the reader's chrome: sticky header, the rail, disclosures,
  and the first inline scripts), amending ADR-0014 decision 1.
- Port `frontend/tests/jsbudget.test.ts` and `docs/js-budgets.json` from
  the US Code site (count `<script is:inline>` bytes per route from
  source), so packages D and E grow within a stated ceiling.

Tests: `tests/e2e/chrome.spec.ts` — after `page.goto("/app/us/pl/81/740/s3#about-h")`
the target's `boundingBox().y` is at or below the header's bottom edge at
1280 and at 375; the rail is visible at 1280 and stacked at 375; the
contents `details` is closed on `/app/us/pl/124/…` and opens on a `#contents`
jump; the axe scan stays clean. `test-web` covers the rail's bounding rule
in `lib/rail.ts` (the pure function that decides what the rail lists).

Docs: the reader contract's page sections (what each page renders and
where); README's reader paragraph.

## D. Keyboard shortcuts

Request 6. Ported from the US Code site's `lib/shortcuts.ts`,
`KeyboardNav.astro` and `ShortcutsDialog.astro` (its ADR-0055) with this
site's actions:

| Keys | Action | Where |
|---|---|---|
| `←` `j` / `→` `k` | previous / next section | a section page, from `neighbors` |
| `u` | up: the nearest ancestor, else the law | a unit page |
| `c` | the contents (the rail's, else the `#contents` disclosure, opened) | any page with one |
| `[` `]` | previous / next top-level provision: the `[id]` children of the section element | a section page |
| `p` | the pages disclosure, opened | a unit page |
| `a` | About this text | a section page |
| `v` | Versions | a compiled page |
| `t` / `b` | top (`#main`) / bottom (`#site-footer`) | anywhere |
| `/` | the citation box | anywhere |
| `?` | this list | anywhere |
| `Esc` | close the list | anywhere |

Rules kept from the source: no Alt, Ctrl or ⌘ bindings; nothing fires in
a text field or while a `dialog[open]` exists; a jump moves focus
(`tabindex="-1"` and `focus({preventScroll: true})`) and opens a
`details` target; a key with nothing to reach writes one sentence into a
`role="status"` region. No command palette: this site has one box and no
page commands.

The bindings are one list (`lib/shortcuts.ts`) rendered by the dialog and
handed to the island as JSON; `keyMap()` throws on a collision. A footer
link `Keyboard shortcuts` opens the dialog.

Tests: `frontend/tests/shortcuts.test.ts` (no collisions, every action has
a `switch` arm — grep the island's source); `tests/e2e/keys.spec.ts` on
`/app/us/pl/81/740/s3`: `k` lands on `/s4`, `]` moves the reading line to
the second provision, `?` opens the dialog, `/` focuses `#cite-q`, a key
inside the box does nothing. The byte budget from C5 gains the two
islands.

Docs: ADR-0022 (one keyboard map). The reader contract's "No JavaScript"
lines under `/app/goto` and in the conventions paragraph are corrected.

## E. Keyword search over OpenSearch, in the one box

Request 7. The US Code site's shape (ADR-0028, 0031, 0049, 0051) with a
smaller corpus and one cluster shared between the two sites.

### E1. The cluster

- Production: the box (`t4g.large`, 8 GB) already runs the US Code site's
  OpenSearch at a 2 GB heap beside about 5 GB of that site and 1.3 GB of
  this one. A second JVM does not fit. `statutes-api` joins the US Code
  compose project's default network as an external network in
  `docker-compose.prod.yml` (the name is read on the box with `docker
  network ls`; nothing in `../uscode-redesign` changes) and reaches the
  cluster as `SEARCH_URL=https://opensearch:9200`. `SEARCH_PASSWORD` is the
  cluster's admin password, typed by the user into this site's `.env`
  through `deploy/bootstrap-box.sh` in an SSM session, never in a
  transcript. `SEARCH_VERIFY_CERTS=false` on both stacks with the same
  comment the US Code site carries.
- Development: `docker-compose.yml` gains an `opensearch` service copied
  from the US Code site's dev file, published on host port 9201 (9200 is
  that site's dev cluster). `.env.example` gains the three variables;
  `DISABLE_SEARCH_SYNC=1` keeps `make test` and every load cluster-free.
- `pyproject.toml` gains `opensearch-py`.

### E2. The index

`storage/search.py` (client and index names; the singleton and
`SearchNotConfigured` as in the US Code site) and `ingest/search_sync.py`
(mapping, fingerprint, aliases, bulk sync). One alias `statutes_units`
over a physical index named for the mapping fingerprint. One document per
unit that carries text:

| Field | From |
|---|---|
| `identifier`, `law_identifier`, `law_label`, `kind` (`pl`, `pvtl`, `act`), `congress`, `number`, `chapter` | `units` joined to `laws` |
| `level`, `num`, `heading`, `text` | the unit; `text` is `Unit.text`, no analyzer beyond the standard one, no stemming (ADR-0031) |
| `short_titles`, `official_title`, `enacted` (date), `year`, `volume`, `first_page`, `citation` | the law |
| `view` | `enacted`; compiled sections of every compilation's current version are indexed too with `view: compiled`, `comp_prefix` and `current_through` |
| `citation_sort` | zero-padded `volume` then `first_page` then `seq`, for citation order |

Hierarchy nodes are indexed with `heading` and no `text`. Quoted sections
are not units and are not indexed on their own.

`python -m ingest reindex-search [--if-changed] [--since YYYY-MM-DD] [--recreate]`:
streams from Postgres in batches of 500, `refresh_interval=-1` during the
build, builds beside the live alias and moves it in one `update_aliases`
call, `--if-changed` rebuilds only when the fingerprint differs,
`--since` re-syncs laws whose `laws.loaded_at` is later (the weekly update
in `deploy/update-sources.sh` runs `--if-changed` then `--since` the last
run's date, under `nice`). Loads themselves do not index; `ingest/` stays
cluster-free except this command.

### E3. The API

`api/search.py`, `GET /api/v1/search?q=&limit=20&offset=0&sort=relevance|date|citation&view=enacted|compiled|all`:

- `storage/searchquery.py`, pure: `parse_query` reads `law:117-328`,
  `congress:117`, `year:1996`, `vol:110`, `kind:pl`, `view:compiled`,
  `heading:"…"` and quoted phrases; `build_search_body` is `operator: and`,
  no fuzziness, phrase boost, `heading^2`, a highlighter on `text` with
  `<em>`; facets over `congress`, `kind`, `view`. `unparse_query`,
  `with_filter`, `without_filter` for the facet links.
- The default `view` is `enacted`. `all` collapses nothing: an enacted and
  a compiled section are two answers.
- `SearchResponse`: `results[{identifier, law_identifier, law_label,
  level, num, heading, snippets, enacted, citation, view, comp_prefix,
  url}]`, `total`, `facets`, `note`. `url` is `/app{identifier}`; the reader
  prints `note` verbatim.
- Rate limit `search` at capacity 120, 10 a second; a cluster failure is a
  503 with `search is unavailable; try again shortly`, the exception in the
  log only.
- `MAX_OFFSET = 1000`.

### E4. The reader

- `/app/goto`: a 422 from `cite` redirects to `/app/search?q=` (the US
  Code site's `goto.astro` shape). A citation still wins. The 422 page goes
  away; the search page carries the box prefilled.
- `/app/search`: results (law label and section label linked, heading,
  snippet with `<em>` kept and everything else escaped, enacted date and
  citation, a `compiled` tag), facets as links that edit the query, a pager
  at 20, the sort control, the API's `note`. Zero results prints the
  syntax page link and the six citation forms.
- `/app/search/syntax`: the operators and the scope words, one page, no
  API call.
- `CiteBox` placeholder becomes `Citation or words`; the label stays
  `Citation or search`.
- Every call forwards the client address (`callHeaders`) so the API's
  bucket is per reader.

Tests: `tests/test_searchquery.py` (pure), `tests/test_search_mapping.py`
(fingerprint, alias promotion against a fake client), `tests/test_search_route.py`
(the route with a stubbed client through a dependency override: a hit, a
503, an empty query 400). `frontend/tests/searchsyntax.test.ts` for the
result renderer's escaping. `tests/e2e/search.spec.ts` over the dev stack
with the fixture database indexed. `make reindex-search`.

Docs: ADR-0023 (keyword search: one document per unit with text, the
shared cluster, strict matching). The reader contract gains `/app/search`
and the `goto` fallback. README's commands and `.env.example`. The deploy
plan's memory table gains the cluster line.

## F. Documentation pass

After the packages land: the reader contract reconciled end to end, the
README's reader section, `docs/plans` index lines, the CLAUDE.md commands
block (`make reindex-search`, `test-e2e` counts), one BUILDLOG entry per
session. Verification counts stay generated.

## Waves, isolation, models

Each package builds in its own worktree on a branch off `main`
(`Agent` with `isolation: "worktree"`, or `git worktree add`), runs `make
test`, `make test-web` and `make test-e2e` over `make dev`, and merges
to `main` in the order below. Pushes to `main` deploy within three minutes:
merge locally in order, push once per wave, and only when the COMPS walk
on the box is complete.

| Wave | Packages | Parallel | Model |
|---|---|---|---|
| 1 | A (API weight) | yes | Sonnet 5 |
| 1 | B1 (the slice, API) | yes | Opus 5 — the range walk and its tests |
| 1 | E1 + E2 + E3 (cluster, index, route) | yes | Opus 5 for `searchquery.py` and `search_sync.py`; Sonnet 5 for the compose, CLI and route |
| 2 | C (chrome) | after A | Sonnet 5; Haiku 4.5 for the SCSS tokens and `EndLinks` |
| 2 | B2 (the stat page) | after B1 and C's `Base` | Sonnet 5 |
| 2 | E4 (search pages) | after E3 and C's `Base` | Sonnet 5; Haiku 4.5 for the syntax page |
| 3 | D (keys) | after C | Sonnet 5 |
| 3 | F (docs) | after everything | Haiku 4.5 |

Package owners and the files they may touch, so two worktrees do not meet
in one file:

- A: `api/schemas.py` (`text` descriptions), `api/responses.py`,
  `storage/postgres.py`, `storage/repository.py`, `db/models.py`, `tests/`,
  `docs/adr/0019`.
- B1: `uslmtext.py`, `storage/postgres.py` (`stat_page` only),
  `storage/repository.py` (`StatPageResult`), `api/schemas.py`
  (`StatPageOut`), `api/responses.py` (`stat_page_response`), `api/routes.py`
  (the stat route's `format`), `tests/`, `docs/adr/0020`.
- C: `frontend/src/layouts`, `frontend/src/components` (new files and
  `SiteHeader`, `SiteFooter`, `UnitPage`, `Pages`, `TocList`),
  `frontend/src/styles`, `frontend/src/lib/rail.ts`, `frontend/tests`,
  `docs/adr/0021`.
- B2: `frontend/src/pages/us/stat`, `frontend/src/lib/types.ts` (the stat
  fields), `frontend/src/lib/api.ts` (`fetchStatPageXml`), `frontend/tests`.
- D: `frontend/src/lib/shortcuts.ts`, `KeyboardNav.astro`,
  `ShortcutsDialog.astro`, one line in `Base.astro` and `SiteFooter.astro`,
  `frontend/tests`, `docs/adr/0022`.
- E: `storage/search.py`, `storage/searchquery.py`, `ingest/search_sync.py`,
  `ingest/reindex_search.py`, `ingest/__main__.py` (one subcommand),
  `api/search.py`, `main.py` (mount), `params.py` (the search note and the
  limit), `docker-compose*.yml`, `.env.example`, `deploy/update-sources.sh`,
  `deploy/deploy-on-box.sh` (the `--if-changed` step, `|| echo`),
  `frontend/src/pages/goto.astro`, `frontend/src/pages/search.astro`,
  `frontend/src/pages/search/syntax.astro`, `frontend/src/components/SearchResult.astro`,
  `SearchFacets.astro`, `Pager.astro`, `frontend/src/lib/api.ts`
  (`fetchSearch`), `frontend/src/lib/url.ts` (`searchHref`, `syntaxHref`),
  `tests/`, `docs/adr/0023`.

## Acceptance, measured on the box after the last wave

- `GET /api/v1/us/pl/117/328` under 300 KB and 0.5 s; `/app/us/pl/117/328`
  under 1.5 s.
- `/app/us/stat/110/4196` shows the text printed on the page, names
  section 814 as where the page begins, and links `/app/us/pl/104/333/d1/tVIII/s814`.
- The header stays on screen at 1280 and 375; a fragment jump lands under
  it; the rail lists the panels and the law's contents at 1280.
- `?` lists the keys; `k` on `/app/us/pl/81/740/s3` reaches `/s4`.
- `/app/goto?q=wild horses` lands on `/app/search?q=wild+horses` with
  results; `/app/goto?q=Pub. L. 81-740, § 3` still lands on the section.
- `make test`, `make test-web`, `make test-e2e` green; the axe scan clean on
  one page of each kind including `/app/search`.
