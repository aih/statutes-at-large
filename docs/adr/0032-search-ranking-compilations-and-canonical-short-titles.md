# ADR-0032: Search ranking, Statute Compilations, and canonical U.S. Code short title sections

Date: 2026-10-19. Status: accepted.

## Context

Searching for an act by title or popular name (such as "Atomic Energy Act of 1954") returned enacted section hits where minor modern amendments ranked ahead of the original act, omitted active Statute Compilations from default search results, and did not link the act's canonical U.S. Code short title section or statutory history.

## Decision

1. In OpenSearch, `FIELDS` includes `short_titles^10` and `official_title^4` alongside `heading^2` and `text`.
2. When building enacted search documents in `ingest/search_sync.py`, a law with empty `short_titles` inherits `short_titles` from its linked `Comp` row when `Comp.partial_of` is null.
3. `PostgresRepository.list_comps` strips surrounding quotes and whitespace from `q`, ranks exact matches on `display_title`, `short_titles`, or `act_title` ahead of prefix and substring matches, and deduplicates multi-file compilations by `identifier_prefix`.
4. `PostgresRepository.act_matches` queries matching compilations and laws. For matched acts, it resolves:
   - The compiled version at `identifier_prefix` with its `current_through` public law and date.
   - The enacted law with its aliases, citation, and enactment date.
   - The canonical U.S. Code section from the `citations` table where `context == 'note'` and `note_topic == 'shortTitle'`, falling back to `context == 'sourceCredit'`. It extracts the contiguous statutory history reference chain and total citing sections count.
5. In `api/search.py`, `GET /api/v1/search` calls `act_matches` on the first page (`offset == 0`) and returns `acts` on `SearchResponse`. When the repository is unavailable or not configured, `acts` defaults to an empty list.
6. The reader at `/app/search` renders matched acts in a summary card above the section results list, linking the Statute Compilation, the canonical U.S. Code section with its statutory history chain, and the original enactment.

## Consequences

A search for an act by title surfaces the current compiled text and its codified position in the U.S. Code directly above enacted section results. Compilations remain distinct from enacted section hits.
