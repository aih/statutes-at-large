# ADR-0021: The reader's chrome: a sticky header, a rail, disclosures, and the first inline scripts

Date: 2026-09-09. Status: accepted. Implements package C of
`docs/plans/2026-09-09-reader-improvements-plan.md`. Amends ADR-0014 decision
1 ("Pages ship no `<script>`").

## Decisions

1. **The header is sticky and one row at every width.** `.site-header {
   position: sticky; top: 0; z-index: 500 }`. `.site-header__inner` does not
   wrap: the brand truncates with an ellipsis before anything gives up its
   line, the nav is hidden below 40em, and the search box is the flexible
   item. Measured on `/app/us/pl/81/740/s3` and `/app/us/pl/81/740` at 375,
   700 and 1280 CSS px: 56px (3.5rem) at every width. `--sticky-h: 3.5rem`
   covers every band with one value. `scroll-margin-top: calc(var(--sticky-h)
   + 0.5rem)` applies to `main`, the section body and its descendants, a
   panel or a heading inside one, and a `details` carrying an id. Print sets
   `.site-header { position: static }`.

2. **`Base.astro` wraps `main`'s content in `.reader-layout`: one column
   below 64em, `16rem minmax(0, 1fr)` from 64em up.** The rail is first in
   the grid and pinned (`position: sticky; top: calc(var(--sticky-h) +
   0.5rem)`, bounded to the viewport, `overflow-y: auto`) from 64em; below
   64em it is second in source order, rendered after the page's own content.
   A page with nothing for the rail to show renders `.reader-layout--single`
   instead, a plain block. `.reader-wrap--rail` widens a page's maximum width
   by the rail's column and gap, so the rail does not narrow the reading
   column (checked at 1280 on a section page: the reading column holds
   704px, unchanged from a page without a rail).

3. **`Rail.astro` takes `sections`, `toc` and `current`.** `sections` lists
   the page's own rendered panels — `#text`, `#contents`, `#pages`,
   `#sources`, `#about-h`, `#cited-by-h`, `#versions` — in the order they
   appear; a panel that is not rendered is not listed. `toc` is the law's or
   compilation's nested contents; `lib/rail.ts`'s `railNodes` decides what of
   it to put on the page: every node, nested in full, when the law holds at
   most 300 units in all; otherwise every hierarchy node, plus a section only
   inside the branch holding `current`. A hierarchy node outside that branch
   carries no children in the DOM at all — checked against
   `/api/v1/laws/117/328`'s 2,155-unit toc, where a section deep inside
   Division A renders 6 `<details>` rather than the law's other 1,864
   sections. Each nested node is a plain link plus, only when it carries
   children, a sibling `<details>` holding the nested list — a link and a
   disclosure toggle side by side rather than one nested inside the other,
   which keeps every rail entry a single interactive control.

4. **Contents and Pages are `<details class="disclosure">`, closed by
   default on a law or a hierarchy node page.** `<summary>Contents — 45
   units, 1,205 sections</summary>` counts the toc entries and, for a public
   law, `summary.section_count`; for a private law, an act, or a hierarchy
   node, the sections among the entries themselves. `<summary>Stat. pages
   for this law — 1,653 pages, 136 Stat. 4459 to 6111</summary>` reads the
   first and last of `pages`. On a section page the Pages disclosure carries
   `open`, so it prints open as it always has, under the same `id="pages"`.
   The compiled view's own Contents becomes the same kind of disclosure, for
   one open/close treatment across every page that lists units.

5. **A fragment naming a closed `<details>` opens it.** One inline script in
   `Base.astro`, on `load` and `hashchange`: it finds the id the hash names,
   opens every `<details>` ancestor of it, and scrolls to it. This is the
   reader's first script, 356 bytes minified with no comments inside it (the
   explanation above is the one Astro does not ship). ADR-0014 decision 1
   ("Pages ship no `<script>`") no longer holds; decision 3's page
   descriptions are unchanged.

6. **`EndLinks.astro`** is a fixed control at the lower right, `↑ Top` to
   `#main` and `↓ End` to `#site-footer`, 44px targets at every width, hidden
   in print. Below 40em `.site-footer` carries 8rem of bottom padding so the
   stacked links do not sit over the footer's last lines at the foot of the
   scroll.

7. **A per-route JavaScript byte budget**, ported from the US Code site's
   `jsbudget.test.ts` (its ADR-0046): `frontend/tests/jsbudget.test.ts` sums
   `<script is:inline>` bytes across each route's transitive `.astro` import
   graph and fails `make test-web` when a route exceeds its ceiling in
   `docs/js-budgets.json`; the measured counts are written to
   `docs/verification/js-bytes.json`. Every route today carries the one
   script from `Base.astro` — 380 bytes as served, comment included — except
   `/app/healthz`, which does not use `Base.astro`. Ceilings are the measured
   bytes plus 200, rounded up to the next 500: 1000 for every route with the
   script, 500 for `/app/healthz`. Packages D and E raise these ceilings when
   their own islands land.

## Consequences

- Every page under `Base.astro` now carries one inline script; `astro
  build`'s client bundle is still empty, since `is:inline` scripts are never
  bundled.
- The compiled view's Contents list is closed by default where it used to
  print open, matching the enacted law and node pages; `section.spec.ts`'s
  "a law with divisions lists its contents nested" opens the disclosure
  before asserting on it.
- A section of a private law or an act still has no toc beyond its nearest
  ancestor's `children` (`parentChildren` in `lib/unitpage.ts`, already
  fetched for `Neighbors`); the rail shows exactly that on such a page,
  matching the plan's rule for these laws.
