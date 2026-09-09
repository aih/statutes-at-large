# ADR-0022: One keyboard map, ported with this site's actions

Date: 2026-09-09. Status: accepted. Implements
`docs/plans/2026-09-09-reader-improvements-plan.md`, package D. Amends
ADR-0014 decision 3 (the reader contract's "No JavaScript" lines under
`/app/goto` and in the conventions paragraph) and follows ADR-0021's byte
budget (C5).

## Context

The reader shipped no keyboard navigation beyond the browser's own. The US
Code site ported its shortcuts into one list (`lib/shortcuts.ts`), a dialog
(`ShortcutsDialog.astro`) and one island (`KeyboardNav.astro`), recorded in
its ADR-0055. This site's unit pages, compiled pages and rail give it a
different set of destinations to reach: no notes, no source-credit anchor,
no command palette, but a compiled view's version picker and a rail with a
nested contents list the source site does not have.

## Decisions

1. **`frontend/src/lib/shortcuts.ts` is the one list.** `SHORTCUT_GROUPS`
   is data; `ShortcutsDialog.astro` renders it and `KeyboardNav.astro`'s
   island receives `keyMap()` as JSON, because an `is:inline` script can
   import nothing. `keyMap()` throws on a key bound to two actions.

2. **The bindings**: `←`/`j` and `→`/`k` move to the previous and next
   section, from `neighbors`; `u` goes up to the nearest ancestor, else the
   law, on any unit page but the law page, which has neither; `c` reaches
   the contents; `[`/`]` step through a section's top-level provisions; `p`
   opens the Statutes at Large pages disclosure; `a` reaches About this
   text; `v` reaches Versions on a compiled page; `t`/`b` go to the top and
   bottom of the page; `/` focuses the citation box (`#cite-q`, the id
   `CiteBox.astro` renders in the header on every page); `?` opens the
   shortcut list; `Esc` closes it, natively — a `<dialog>` closes on Escape
   by itself, so the key is printed in the list and bound to nothing in the
   island. No Alt, Ctrl or ⌘ binding: this site has one box and no page
   commands, so a held modifier has nothing of its own to reach.

3. **`c` reaches the rail when the rail is pinned beside the text (64em and
   up, C2), else the `#contents` disclosure, else the rail.** Below 64em
   the rail renders after the page's own content rather than beside it, so
   jumping into `#contents` there reaches the law's nested list where a
   reader is already looking, at the top of the page; a page whose rail
   carries only "On this page" (a hierarchy node with no toc to nest) has
   no `#contents` to fall back to, so the rule's last step is the rail
   itself, wherever it sits.

4. **`[` and `]` read the section's own DOM rather than a rendered contents
   list.** This site's section page carries no `SectionContents` panel, so
   the top-level provisions are the `[id]` children of `.uslm-section`
   (`uslm.ts`'s wrapper for the section itself, `article#text`'s one
   child, carrying the section's own identifier as its own id) —
   the same elements the renderer already gave an `id` to, the wrapper
   excluded. A section with none has nothing to step through;
   `say()` writes one sentence into `#keysay`, the `role="status"` region
   `Base.astro` renders on every page, and clears it after five seconds.
   Which provision is current is decided against the reading line (the
   target's own `scroll-margin-top`), not the top of the viewport, for the
   reason ADR-0055 gives: a provision just jumped to sits under the sticky
   header rather than at zero, and comparing against zero would make `]`
   land on the provision it started from.

5. **`up`, `previous` and `next` are computed by the page, not the
   island.** `Base.astro` takes them as `Link | null` props and passes them
   to `KeyboardNav`, which looks them up by action name and navigates with
   `location.assign` rather than `scrollIntoView` — they are cross-page
   jumps, not in-page ones. `UnitPage.astro` sets `previous`/`next` from
   `neighbors` (a section only) and `up` from the nearest entry of
   `ancestors`, else the law. The compiled view sets `up` the same way from
   its own `ancestors`, else the compilation root; it fetches no
   neighbouring section, so `previous` and `next` stay null there.

6. **A footer link opens the dialog.** `SiteFooter.astro` gains `<a
   href="#shortcuts" data-shortcuts-open>Keyboard shortcuts</a>`; the
   island intercepts its click and calls `showModal()` instead of
   navigating.

7. **Every route's byte budget rises to 3,500** (`docs/js-budgets.json`).
   `KeyboardNav.astro`'s inline script is 2,759 bytes; with `Base.astro`'s
   existing 380-byte disclosure script every route under `Base` now ships
   3,139 bytes, plus 200 rounded up to the next 500. `ShortcutsDialog.astro`
   and the two JSON data scripts (`type="application/json"`, not
   `is:inline`) contribute nothing to the count, the same split the US Code
   site's ADR-0046 draws. `/app/healthz` does not use `Base.astro` and
   keeps its 500-byte ceiling.

## Consequences

- The reader contract's "No JavaScript" line under `/app/goto` and in the
  conventions paragraph no longer holds; both are corrected to name the
  budgeted inline scripts ADR-0021 introduced and this one adds to.
- A key typed into a text field, a `<select>`, or anything
  `contenteditable` is left alone; nothing fires while a `dialog[open]`
  exists, so a shortcut behind the open dialog cannot scroll or navigate a
  page the reader cannot see.
- `README.md`'s reader paragraph gains one sentence naming the shortcuts
  and the `?` dialog.
