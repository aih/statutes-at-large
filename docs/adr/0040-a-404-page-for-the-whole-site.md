# ADR-0040: A 404 page for the whole site

Date: 2026-11-09. Status: accepted. Modelled on reintroductions-us's
`reintro/web/notfound.py` and its `404.html`.

## Context

A path under `/app` with no route got Astro's default 404, outside the
site's chrome. `/app/congress/{n}` with a number that is not one answered
the text `Invalid Congress number`. A browser asking FastAPI for any other
path it has no route for (`/about`, `/search`) got `{"detail":"Not Found"}`.
A 404 from the API on a law, section or page printed the status and the
API's `detail`.

## Decision

1. `frontend/src/pages/404.astro` is the reader's 404, in `Base`: the path
   asked for, links under "Did you mean", the citation box, and the site's
   pages. Status 404, `Cache-Control: private, no-store`.
2. The links come from `frontend/src/lib/notfound.ts`, in this order: an
   identifier the path spells without `/us`, under `/api/v1`, or with the
   kind in another case (`/app/pl/81/740` → `/us/pl/81/740`, `scomp` →
   `sComp`); otherwise a law number in a segment (`81-740`, `PL81-740`) as
   the public law; then up to three reader pages whose lower-cased path is
   within a similarity of 0.75 (edit distance with adjacent swaps counted
   once, over the longer length). At most five.
3. A GET or HEAD for one of the reader's pages in another letter case
   (`/app/About`) is a 301 to it. Identifiers are not lower-cased: `sComp`,
   `tI` and `ch1.` are case-sensitive.
4. A page that finds its own parameters invalid sets
   `Astro.locals.notFoundPath` and returns `Astro.rewrite("/404")`;
   `/app/congress/{n}` does.
5. `ErrorPage` on a 404 from the API keeps the API's `detail` as the lede,
   titles the page "Not found", and adds the same citation box and page
   list, with "Where else to look" offering the law's Congress page for
   `/us/pl/{c}/…` and `/us/pvtl/{c}/…`, the Congresses index for `/us/act/…`
   and the compilations index for `/us/sComp/…`. Other statuses are as
   before.
6. FastAPI answers a 404 for a GET or HEAD that prefers HTML, outside
   `/api/` and `/app`, with a 307 to the same path and query under `/app`
   (`citation.reader_redirect`). The reader then serves the page or its 404.
   Every other 404 stays JSON. The handler is registered for Starlette's
   `HTTPException`, so it also sees the router's own 404 for an unmatched
   path.

## Consequences

- `/about`, `/search?q=…` and `/sources` in a browser reach the reader's
  pages of those names.
- On the box, the 307 into `/app` meets the cookie gate (ADR-0030) like any
  other `/app` request.
- The page list in `lib/notfound.ts` is written by hand; a new reader page
  is not offered until it is added there.
