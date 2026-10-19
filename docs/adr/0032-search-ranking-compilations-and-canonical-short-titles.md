# ADR-0032: Search ranking, Statute Compilations, and canonical U.S. Code short title sections

Date: 2026-10-19. Status: accepted.

## Context

A search for an act by its popular name ("Atomic energy act of 1954") ranked
sections of later amending laws above the act, did not show its Statute
Compilation (the default view is `enacted`), and did not say where the US Code
carries it (42 U.S.C. 2011). Issue #10.

## Decision

1. `FIELDS` (`storage/searchquery.py`) searches `short_titles^10` and
   `official_title^4` beside `heading^2` and `text`. Both fields were already
   in the mapping.
2. In `ingest/search_sync.py` a law with no short title of its own takes its
   compilation's: its enacted documents take the whole-act file's
   (`Comp.partial_of` null), and the compiled documents of a matched law take
   their own file's. Public Law 83-703's short title is inside
   `quotedContent`, so `laws.short_titles` is empty.
3. `Repository.act_matches(query)` returns up to five acts whose popular name
   the query matches as whole words: a compilation's display title, act title
   or short titles, or a law's short titles. The long title is not read; it
   names the acts a law amends. A whole title ranks first, then whole words at
   the start of a title, then whole words inside one; compilations come before
   laws on a tie. There is one act per compilation prefix, titled with the
   act's name (`Social Security Act` for its per-title files). A query of only
   common title words (`act`, `of`, `the`, …) and numbers names no act.
   Quotes around the query are dropped.
4. An act's law is the compilation's `law_id`, or the law its prefix names
   (`_law_by_congress_number`, as `CompRef.law_identifier` reads it). A
   compilation whose law is not loaded gets no US Code section. The section
   comes from the citation index:
   - the first section whose Short Title note (`note_topic` `shortTitle`)
     cites one of the law's aliases before the note's first Statutes at Large
     page, as the enacting law or after `as added`; `history` is that note's
     refs;
   - else the first section whose source credit cites an alias before the
     credit's first Statutes at Large page, a section the law enacted;
     `history` is the whole credit.

   A law cited only after that page amended the section and is not given it.
   "First" is identifier order. `citing_sections_count` is the number of US
   Code sections that cite the law anywhere, as `cited-by` counts them.
5. `GET /api/v1/search` returns `acts` on the first page (`offset` 0) when the
   query has free text. The API adds the URLs: `/app{prefix}` for the
   compilation and `USCODE_ORIGIN{identifier}` for the section. A failure in
   `act_matches` is logged and leaves `acts` empty; the results are served.
6. `/app/search` shows each act in a summary box above the results: the
   compilation and its currency, the US Code section with the refs of its
   Short Title note or source credit (each law followed by its Stat. page),
   and the law as enacted.
7. `GET /api/v1/comps?q=` ranks the same way, with the long title read too,
   and still lists every file. Quotes around `q` are dropped.

## Consequences

The enacted and compiled documents change while the mapping does not, so the
deploy's `reindex-search --if-changed` leaves the live index as it is. One
`reindex-search` on the box after the merge puts the inherited short titles in
the index.

A note's refs are told apart from the next note's by a gap in `seq`, so two
adjacent Short Title notes in one section read as one. A law whose short title
the US Code records only in a "Short Title of … Amendment" note
(`shortTitleOfAmendment`) is found by its source credit, or not at all.
