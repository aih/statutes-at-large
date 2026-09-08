# ADR-0014: The reader is Astro at `/app` and prints the API's sentences verbatim

Date: 2026-09-08. Status: accepted. Implements design stage 5 (the reader)
with the US Code site's stack (its ADR-0011, 0015, 0023); records what the
pages show and where this reader departs from that one.

## Context

The citation URL has redirected browsers to `/app/…` since stage 1, and the
proxy answered 503 there. The API serves every fact the reader needs
(`docs/plans/2026-09-08-reader-contract.md` lists the routes per page and
the sentences each prints). The US Code site's reader is Astro 5 with
`@astrojs/node` SSR, USWDS 3, no client JavaScript by default, a typed USLM
renderer in the frontend, and a plain GET citation box.

## Decisions

1. **The stack is the US Code site's.** `frontend/` is Astro 5 with
   TypeScript, `output: "server"`, `@astrojs/node` standalone on port 4321,
   `base: "/app"`, USWDS 3 compiled from SCSS, `@xmldom/xmldom` for the
   renderer. Caddy sends `/app*` to `frontend:4321` and everything else to
   `api:8001`; the reader reads `/api/v1` over HTTP (`API_BASE_URL`) through
   one client module (`src/lib/api.ts`) and has no other data source and no
   build-time dependency on the database. `make dev` runs the API on :8001
   and the reader's dev server on :4321 (its Vite proxy forwards `/api/v1`);
   `make up` is the compose stack on :8010. Pages ship no `<script>`.

2. **The API's sentences are printed verbatim.** `note` on every unit,
   `note` and `message` from `cite`, `note` from `cited-by`, `detail` on
   every error. The reader adds sentences of its own only where the API has
   none: the provision line ("Provision X is shown, marked, in the context
   of section N."), the missing-provision alert, the currency line
   (`Amended: {status} — {latest.label} ({enacted}); evidence: …`), unit
   labels (`Sec. 101`, `Title I`, `Division A`, `Chapter 1.`).

3. **The pages.** `/app/` (what is loaded, from `/status`; the citation box;
   the six forms of `params.CITE_FORMS`). `/app/goto?q=` (a GET form's
   target: 307 to `/app{identifier}` on a hit, 307 to the US Code site for a
   US Code citation, 404 with the `note` for `exists: false`, 422 with the
   `detail`). `/app/us/pl/…`, `/us/pvtl/…`, `/us/act/…` (one loader and one
   component for the law, a hierarchy node, a section and a provision: the
   text rendered from `{served_identifier}?format=xml`, the note, the
   currency line, alternatives, Stat. pages with govinfo links, ancestors as
   breadcrumbs, previous and next section, the "cited by" panel from
   `cited-by` with `limit=20`, provenance, and for a public law the sources
   and the nested contents from `/laws/{c}/{n}`). `/app/us/sComp/…` (the
   compiled view with the version picker over `versions` and `?through=`,
   the enacted counterpart from `alternatives`). `/app/us/stat/{vol}/{page}`
   (the documents on the page, `starts_here`, `unit_on_page`).

4. **The renderer** (`src/lib/uslm.ts`, ported from the US Code site's):
   the same element map shape, `@class` and `@style` copied, `@identifier`
   to `id` on the first element carrying it, unknown elements to `div`, a
   `target` option marking the matched element `target` and its ancestors
   `target-path`. Statutes USLM differs from the Code's: `content`,
   `chapeau`, `continuation` and `proviso` are `div` (they hold
   `sidenote`, `quotedContent` and `page`); `quotedContent` with block
   children is a `blockquote`, a quoted phrase stays inline; `sidenote` is
   `<aside role="note">`; `page` is a link to the govinfo page when its
   identifier is a Stat. page. Cross references open in the same tab.

5. **References** follow the labels answer (ADR-0016, decision 5): the
   fragment's `/us/pl/`, `/us/pvtl/`, `/us/act/` and `/us/stat/` hrefs go to
   `POST /labels` at most 100 per request and at most 1,000 per page; a
   reference that exists links to `/app{href}` with `law_label`, `§ num`
   and `heading` as hover text; a public law of the 104th Congress onward
   or a Stat. page that does not exist links to govinfo; anything else is
   text. `/us/usc/` links to `USCODE_ORIGIN`. A failed labels call renders
   every reference as text.

6. **Caching follows the API.** A unit page copies the API's
   `Cache-Control` (`immutable` for an enacted unit and a pinned
   compilation, `max-age=300` otherwise); `/app/` and a stat page are
   `max-age=300`; every error page and every non-redirect from `/app/goto`
   is `private, no-store`; a 429 copies `Retry-After`; an unreachable API is
   a 502.

7. **Neighbours** come from `/laws/{c}/{n}`'s `toc` for a public law and
   from the nearest ancestor's `children` for a private law or an act, so
   no new route was added for them.

8. **Tests.** `make test` is unchanged and needs no Node. `make test-web`
   is vitest over the renderer, the reference rule, URL encoding and the
   labels batching (62 tests, fixtures cut verbatim from the API).
   `make test-e2e` is Playwright over a running site (`BASE_URL`), with an
   axe scan (WCAG 2.1 AA) of one page of each kind (26 tests).

## Departures from the US Code site

- System font stacks rather than webfonts; a custom header rather than
  USWDS's script-driven navigation; USWDS images copied from the package
  at build time (`scripts/uswds-assets.mjs`) and gitignored rather than
  committed.
- No preview cards, no release picker, no accounts: nothing in this site's
  API is versioned by release point, and a compilation's versions are the
  picker.

## Consequences

- The proxy's 503 at `/app*` is gone; the citation URL lands on a page.
- The reader's Docker image builds from `./frontend` alone; the compose
  `frontend` service takes `API_BASE_URL` and `USCODE_ORIGIN`.
- Checked on the compose stack on 2026-09-08: `/app/us/pl/81/740/s3`,
  `/app/us/act/1950-08-30/ch823/s3` (the alias sentence),
  `/app/us/pl/118/22/s101` (the section-number sentence),
  `/app/us/pl/118/5/dA/tI/s101/a` (the provision marked),
  `/app/us/sComp/83/703/tI/ch1./s1`, `/app/us/stat/137/112`,
  `/app/goto?q=110 Stat. 4196` (404 with the note), `/app/goto?q=garbage`
  (422 with the detail); all print the API's sentences unchanged and pass
  axe.
