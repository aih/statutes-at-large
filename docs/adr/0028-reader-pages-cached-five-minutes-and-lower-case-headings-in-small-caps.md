# ADR-0028: Reader pages are cached for five minutes, and a lower-case heading is set in small caps

Date: 2026-09-14. Status: accepted. Amends ADR-0014, decision 6 (caching),
and ADR-0027, decision 3 (small caps in the h1).

## Context

A unit page and a compiled page copied the API's `Cache-Control`. The API
answers an enacted unit with `public, max-age=31536000, immutable`, so the
HTML of every enacted law, hierarchy node and section page was cacheable for
a year. That HTML names the stylesheet by its build hash
(`/app/_astro/_identifier_.i9wR-mes.css`) and carries the footer's version,
the rail, the neighbours and the cited-by panel. After ADR-0027 was
deployed, `/app/us/pl/98/181/tI/chI/tVIII/s805` kept the earlier stylesheet
in a browser that had loaded the page before, until a hard refresh.

The API's `heading` is the heading's text without its classes. GPO's USLM
types a small-caps heading in lower case:
`<heading class="smallCaps centered">elimination of agricultural export subsidies</heading>`.
The section h1 took the class from the section's XML (ADR-0027). The table
of contents, the rail, previous and next, and search results printed the
text in lower case.

Sections outside `quotedContent` whose heading has letters, across the 17
volume files in `data/statute` on the workstation and the PLAW zips for the
113th to 119th Congresses:

| | no capital letters | a capital letter |
|---|---|---|
| `smallCaps` | 6,380 | 293 |
| no `smallCaps` | 153 | 65,691 |

The 293 are in title or upper case ("Definitions", "General Provisions").
The 153 are in lower case ("authorization of appropriations", "effective
date").

## Decisions

1. **Every reader page that answers 200 is `public, max-age=300`**, the
   enacted unit pages and the compiled pages included (`lib/cache.ts`).
   Error pages stay `private, no-store`. The API's own `Cache-Control` is
   unchanged. The hashed assets under `/app/_astro/` stay `immutable`.

2. **A heading with lower-case letters and no capital letters is set in
   small caps** (`lib/toc.ts: smallCapsClass`) wherever the reader prints a
   unit's heading: the h1 of a hierarchy node, a section and a compiled
   unit, the table of contents, the rail's "In this law" list, previous and
   next, and a search result. The section h1 also keeps the class from its
   XML heading (ADR-0027, decision 3).

## Consequences

- A browser holding a page changed by a deploy gets the new page within
  five minutes. A page it does not hold arrives with the current
  stylesheet.
- A page cached under `immutable` before this change stays in that browser
  until the reader reloads it without the cache.
- A reload after five minutes renders the page again, with its API calls.
- The 153 lower-case headings without the class are set in small caps. The
  293 small-caps headings with a capital letter are in small caps in the
  section h1 only.
