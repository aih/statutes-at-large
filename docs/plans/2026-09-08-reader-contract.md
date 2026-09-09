# The reader's contract with the API

Date: 2026-09-08. Stage 5 of the design. The reader at `/app` (Astro 5,
SSR on Node, `frontend/`) reads `/api/v1` and nothing else. Every JSON it
needs is already served; this page lists, per reader page, the routes it
calls, what it shows, and the sentences it prints verbatim from the API.

Conventions the reader keeps from the US Code site (its ADR-0010, 0011,
0015): every page is server-rendered; one typed client module makes every
API call; the base is `/app`; the reader never rephrases a `note`. Links to
this site's own identifiers are `/app{identifier}`; links to the US Code
site are `USCODE_ORIGIN{identifier}` (`https://uscode.linkedlegislation.org`);
links to a printed page are the `pdf` field the API gives. Client
JavaScript is budgeted rather than absent (ADR-0021): every page carries one
small inline script (opening a disclosure a fragment names) and stays under
the ceiling `docs/js-budgets.json` states for its route.

## Chrome

`Base.astro` wraps every page's content in `.reader-layout`: the rail
(`Rail.astro`) beside it from 64em, after it below 64em. The rail lists two
things, either of which can be empty: **On this page**, the panels the page
actually rendered, by id (`#text`, `#contents`, `#pages`, `#sources`,
`#about-h`, `#cited-by-h`, `#versions`, `#documents`); and **In this law**, the law's or
compilation's nested contents, bounded above 300 units to the hierarchy plus
the branch being read (`lib/rail.ts`). A unit or a law page's Contents and
Pages panels are `<details class="disclosure">`, closed by default except
Pages on a section page, which prints open. A fragment naming a closed
`<details>` opens it, on load and on `hashchange`.

## Sentences printed verbatim

All built in `params.py`; the reader shows the field, never its own wording.

| Field | Route | Built by |
|---|---|---|
| `note` on an enacted unit | `/us/pl/…`, `/us/pvtl/…`, `/us/act/…` | `served_note` (when the resolution was not exact) then `enacted_note`, whose amended sentence is `amended_sentence` |
| `note` on a compiled unit | `/us/sComp/…`, `?view=compiled` | `served_note` then `compiled_note` |
| `note` on `cited-by` | `/cited-by` | `cited_by_note` |
| `note`, `message` on `cite` | `/cite` | `cite_note`, `cite_chapter_not_on_page`, and the provision sentence in `api/cite.py` |
| `detail` on a 422 from `cite` | `/cite` | `cite_not_a_citation` |
| `detail` on a 404 | every route | `not_found` |

Examples, from the dev database on 2026-09-08:

- `/api/v1/us/pl/81/740/s3`: `This is section 3 of Public Law 81-740 as
  enacted on August 30, 1950 (64 Stat. 563). It is not updated. No later
  amendment of this section is recorded in the indexes here (the US Code's
  source credits, the classification tables, and the Statute Compilations);
  amendment may still have occurred. To check for later amendments: the
  classification tables at uscode.house.gov for laws after August 30, 1950.`
- `/api/v1/us/act/1950-08-30/ch823/s3`: the same, prefixed by
  `/us/act/1950-08-30/ch823/s3 is served as /us/pl/81/740/s3, the same law
  under its other identifier.`
- `/api/v1/us/pl/118/22/s101`: prefixed by `No unit is stored at
  /us/pl/118/22/s101; the section numbered 101 in this law is at
  /us/pl/118/22/dA/s101 and is served here.` and with the amended sentence
  `This section has been amended since; the most recent law recorded is
  Public Law 118-35 (January 19, 2024).`
- `/api/v1/us/sComp/83/703/tI/ch1./s1`: `This is section 1 of Atomic Energy
  Act of 1954 as compiled by the House Office of the Legislative Counsel,
  incorporating amendments through Public Law 118-67 (July 9, 2024).
  Compilations are not an official version; the official text is in the
  Statutes at Large and the United States Code (1 U.S.C. 112, 204). Laws
  enacted after July 9, 2024 are not reflected; check the classification
  tables for Atomic Energy Act of 1954 and the US Code section(s)
  https://uscode.linkedlegislation.org/us/usc/t42/s2011. The enacted text is
  at https://statutes.linkedlegislation.org/us/pl/83/703/s1.`
- `/api/v1/cite?q=Pub. L. 104-333, § 814`: `Public Law 104-333, section 814
  is /us/pl/104/333/s814; nothing is loaded there.`
- `/api/v1/cite?q=garbage` (422): `'garbage' is not a citation this site can
  read. Try 'Pub. L. 104-333, § 814', '110 Stat. 4196', 'Act of Aug. 25,
  1916, ch. 408', 'Aug. 30, 1954, ch. 1073, § 2', 'Private Law 81-375', or
  '43 U.S.C. 1701'.`

The currency line the reader prints on an enacted unit is
`currency.amended` rendered as its fields, beside the note: the status word
(`known_amended`, `no_record`, `unknown`), `latest.label` and
`latest.enacted` when present, and `evidence`. The compiled currency line is
`currency.current_through.pl` and `.enacted`, `fetched`, and
`govinfo_last_modified`.

## Pages

### `/app/`

Calls `GET /api/v1/status`. Shows what is loaded: per collection
(`collections.STATUTE.volumes`, `collections.PLAW.congresses` with
`laws_by_congress`, `collections.COMPS.packages_loaded`), the citation index
(`citations.rows`, `citations.citing_sections`, `citations.release_labels`),
the classification mirror (`classifications.congresses`, `classifications.rows`),
and `stale`. The citation box is a plain GET form to `/app/goto` with one
field `q`, and the forms it accepts are listed from `params.CITE_FORMS`
(reproduced in the reader as the same six strings). Example links:
`/app/us/pl/81/740/s3`, `/app/us/act/1950-08-30/ch823/s3`,
`/app/us/sComp/83/703/tI/ch1./s1`, `/app/us/stat/64/563`.

### `/app/goto?q=`

Calls `GET /api/v1/cite?q=`. Four outcomes:

| API | Reader |
|---|---|
| 422 | status 422; the `detail` printed verbatim; the box again with the query |
| 200, `exists: true` | 307 to `/app{identifier}` (the identifier asked for, not `served_identifier`; the unit page says which unit answered) |
| 200, `kind: "usc"` | 307 to `url` (the US Code site) |
| 200, `exists: false` | status 404; `note` printed verbatim; `label` and `identifier` shown; `message` when present; the box again |

No JavaScript. The 404 and 422 pages are `Cache-Control: private, no-store`.

### `/app/us/pl/{c}/{n}`, `/app/us/pvtl/{c}/{n}`, `/app/us/act/{date}/ch{n}`

The law. Calls `GET /api/v1{identifier}` (a `UnitOut` with `level: "law"`)
and, for a public law, `GET /api/v1/laws/{c}/{n}`. `UnitOut.text` is empty on
a law; the page never renders it. Shows:

- `law.short_titles` (first as the page title, the rest listed),
  `law.official_title` (also `heading` on the unit), `law.label`,
  `law.enacted` (long date), `law.citation`, `law.doc_type`, `law.aliases`
  (each as `/app{alias}`; the note says which one answered), `law.source`.
- `note` verbatim; the currency line from `currency.amended`.
- `provenance` (`text`, `identifiers`, `sha256`), on every unit page.
- `pages` as links to `pdf`, labelled by the page identifier.
- `children` as the table of contents, each entry `/app{identifier}` with
  `num` and `heading`; sections marked by `is_section`. For a public law the
  full reading-order `toc` from `/laws/{c}/{n}` is used instead, nested by
  level.
- From `/laws/{c}/{n}`: `sources.served_from`, `sources.package`,
  `sources.volume` (`package`, `loaded`, `govinfo` link), `sources.plaw`
  (`package`, `uslm`, `loaded`, `govinfo` link), and `compilations` (each
  `identifier_prefix` as `/app{identifier_prefix}`, `display_title`,
  `current_through`).
- `alternatives`: a `compiled` entry links to `/app{identifier}` with
  `current_through`; a `codified` entry links each of `identifiers` to the
  US Code site.
- The "cited by" panel: `GET /api/v1/cited-by?identifier={served_identifier}&limit=20`;
  `note` verbatim, `total`, `contexts`, and `sections` each as `citation`,
  `heading`, `release_label`, linked to `url`, with a link to the API for the
  rest when `total` exceeds the page. A 404 from `cited-by` (a law in no
  index) shows nothing; a failed call shows nothing.
- Links: `xml_url` (source XML), the JSON at `/api/v1{identifier}`, the
  citation URL `{identifier}` as text.

### `/app/us/pl/{c}/{n}/{path}` (also `/us/pvtl/…`, `/us/act/…`)

A hierarchy node, a section, or a provision. Calls `GET /api/v1{identifier}`
(JSON). `level` decides the layout:

- A hierarchy node (`division`, `title`, `subtitle`, `chapter`, `subchapter`,
  `part`, `subpart`): heading, `ancestors` as breadcrumbs, `children` as the
  table of contents, `note`, `provenance`, `pages`. `UnitOut.text` is empty
  here; the text is not rendered, and `xml_url` is linked instead.
- A section: the text rendered from `GET /api/v1{served_identifier}?format=xml`
  (the whole section, always; `xml_url` on a provision request returns the
  provision alone) by the typed USLM renderer (`frontend/src/lib/uslm.ts`,
  ported from the US Code site's), with `@identifier` copied to `id`. When
  `provision` is present and `provision.found`, the element whose `id` is
  `provision.identifier` is marked as the target and a line says which
  provision is shown in the context of the section; when `found` is false
  the note already says the provision is not in the text and an alert
  repeats `provision.identifier`. `heading`, `num`, `ancestors` as
  breadcrumbs (each `/app{identifier}`), `note` verbatim, the currency line,
  `alternatives` as links, `pages` with `pdf` links, `provenance`,
  `occurrences` when above 1, and the "cited by" panel as on the law.
- Previous and next section: for a public law, the neighbouring `is_section`
  entries of `toc` from `GET /api/v1/laws/{c}/{n}`; for a private law or an
  act, the neighbouring sections among the nearest ancestor's `children`
  (`GET /api/v1{ancestors[-1].identifier}`, or the law when there is none).
  Both links are `/app{identifier}`.
- Cross references inside the rendered text (`ref/@href`): collected from
  the fragment, deduplicated, looked up with `POST /api/v1/labels` at most
  100 per request (`{"identifiers": […]}`), and resolved by the rules in
  `frontend/src/lib/refs.ts`:

  | `href` | Link |
  |---|---|
  | `/us/usc/…` | `USCODE_ORIGIN{href}`; no hover text (labels does not answer the US Code) |
  | `/us/pl/…`, `/us/pvtl/…`, `/us/act/…` with `exists: true` | `/app{href}`; hover `law_label` then `num` and `heading` when present |
  | `/us/stat/{v}/{p}` with `exists: true` (`level: "page"`) | `/app/us/stat/{v}/{p}`; hover the first document's `label` |
  | `/us/pl/{c}/{n}…` with `exists: false`, `c` ≥ 104 | `https://www.govinfo.gov/link/plaw/{c}/public/{n}` |
  | `/us/stat/{v}/{p}` with `exists: false` | `https://www.govinfo.gov/link/statute/{v}/{p}` |
  | anything else, or a failed labels call | plain text |

  The labels call is allowed to fail: the text renders with every reference
  as plain text and an `href`-less `cite`.

### `/app/us/sComp/{c}/{n}[/{path}][?through=]`

The compiled view. Calls `GET /api/v1/us/sComp/…[?through=]` (JSON) and, for
a section, `…{served_identifier}?format=xml[&through=]` for the text. Shows
`compilation.display_title` and `short_titles`, `law.identifier` as
`/app{law.identifier}` when `law.loaded`, `currency` as the compiled
currency line, `note` verbatim, `provenance`, `usc_refs` as US Code links,
`ancestors`, `children`, the rendered text (a section), and the version
picker: one link per entry of `versions`, labelled `current_through.pl` and
`current_through.enacted`, marked `is_current`, each to
`/app{identifier}?through={current_through.pl}`. `alternatives` with
`view: "enacted"` is the enacted counterpart link (`/app{identifier}`);
`codified` links to the US Code site. Cross references resolve by the same
rules as the enacted section. `Cache-Control` follows the API: the page is
cacheable for a year only when the API answered `immutable`.

### `/app/us/stat/{vol}/{page}`

Calls `GET /api/v1/us/stat/{vol}/{page}` and, when it lists any document,
`GET …?format=xml`. Shows the page label and volume, the `pdf` link, and the
numeric neighbours (`Neighbors.astro`, reused): `/app/us/stat/{vol}/{page-1}`
and `{page+1}`, omitted on a lettered page (`a12`) and at the volume's first
page. A neighbour nothing prints on is the API's 404. A 404 for the page
itself shows the API's `detail`.

**Text on this page** (`#text`, skipped when `documents` is empty): one block
per document, headed by its `label` and `title` linked to `/app{identifier}`.
`units[0]` and `unitLabel` build "Begins inside Sec. 3 — Read section 3 in
full", linked to `units[0].identifier`; each further unit of `units` gets its
own "Read … in full" line. An empty `units` with `starts_here` true prints
"{label} begins on this page." instead. Below that, the slice from
`?format=xml`'s matching `slice` element, rendered by `render()` into an
`article.section-body` — `slice`, and the `pLaw`/`main` it wraps, are not in
the element map and so render as plain containers around the law's USLM. The
slice's `ref/@href`s, gathered across every document on the page, resolve
through one `fetchLabels` call, as on a section page. A failed `format=xml`
call falls back to the document's plain `text` field, with the same notice a
section page gives when its own XML call fails.

**Documents on this page** (`#documents`): each `label`, `title`, `citation`,
`enacted`, linked to `/app{identifier}`, with `starts_here` printed as
"starts on this page" and, otherwise, "begins at {citation} and prints on
this page".

## The forwarded address

Every server-side call the reader makes carries the browser's address as
`X-Forwarded-For` (`CallOptions.clientAddress` in `src/lib/api.ts`, read
from `Astro.clientAddress` in each page by `clientAddressOf`). The address
is the one the proxy set: `deploy/Caddyfile` overwrites `X-Forwarded-For`
with `{client_ip}` on the way to the reader, which is the client the edge
named when the peer is the edge and the peer itself otherwise. The API's
`client_key` reads it through uvicorn's `--proxy-headers`, so `cite`
(`/app/goto`) and `cited-by` (the panel) are limited per reader at 60
requests then 2 a second, the same buckets a direct API caller uses. A call
without an address (a page rendered with no adapter address) sends no
header and is keyed on the reader container.

`/app/healthz` answers 200 with `ok` and no API call; the compose
healthcheck and the watchdog read it.

## Errors

A 404 from any route renders the `detail` verbatim with status 404. A 429
renders `detail` with status 429 and the `Retry-After` header copied. A 503
(`RepositoryUnavailableError`) renders `detail` with status 503.

## Caching

The reader copies the API's `Cache-Control` for a unit page (`immutable` for
an enacted unit and a pinned compilation, `max-age=300` otherwise) and sets
`max-age=300` on `/app/` and the stat page. `/app/goto` failures are
`no-store`.
