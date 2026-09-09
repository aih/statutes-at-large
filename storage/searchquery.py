"""What a search query means, and the OpenSearch body it becomes.

Pure: nothing here talks to a cluster, to Postgres, or to `api/`. `parse_query`
turns a reader's string into filters and residual text, `build_search_body`
turns that into a request body, and `unparse_query`, `with_filter` and
`without_filter` write a query back out so a facet link is an edit of the query
string.

Matching is strict (the US Code site's ADR-0031): `simple_query_string` with
`default_operator: and`, a named flag set, and no `fuzziness`. A reader loosens
it deliberately with `~1`, `|` or `*`.

The scope words are `law:`, `congress:`, `year:`, `vol:`, `kind:`, `view:` and
`heading:`. They are not `simple_query_string` syntax — that parser has no
notion of a field, and the one that does throws on malformed input — so they
are lifted out of the string here and what is left goes to the cluster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

QUERY_SYNTAX_FLAGS = "AND|OR|NOT|PHRASE|PRECEDENCE|PREFIX|FUZZY|SLOP|ESCAPE|WHITESPACE"
"""Which operators `simple_query_string` will honour.

`WHITESPACE` is what makes the parser split on spaces at all. Without it `-`
and `+` are never read as leading operators, so `water -pollution` parses to
`+water +pollution`: the exclusion becomes a requirement, and the query is
valid either way.
"""

FIELDS: tuple[str, ...] = ("heading^2", "text")
"""The searched fields and their weights."""

PHRASE_BOOST = 4.0
HEADING_PHRASE_BOOST = 8.0
PHRASE_SLOP = 2

SORTS: tuple[str, ...] = ("relevance", "date", "citation")
"""`relevance` is the score. `date` is `enacted` newest first. `citation` walks
the Statutes at Large in print order (`citation_sort`)."""

VIEWS: tuple[str, ...] = ("enacted", "compiled", "all")
"""`enacted` is a law as printed in the Statutes at Large, `compiled` a section
of a Statute Compilation's current version. `all` filters neither: an enacted
and a compiled section are two answers."""

DEFAULT_VIEW = "enacted"

KINDS: tuple[str, ...] = ("pl", "pvtl", "act")

FACETS: tuple[str, ...] = ("congress", "kind", "view")
"""The aggregations `facets=True` asks for. Each is named for the index field
it counts and for the scope word that filters it, so a facet link is
`with_filter(parsed, name, value)`."""

SCOPE_FIELDS: dict[str, str] = {
    "law": "law_identifier",
    "congress": "congress",
    "year": "year",
    "vol": "volume",
    "kind": "kind",
    "heading": "heading",
}
"""Scope word → the index field it filters.

`heading` is the odd one: it scopes a *term* to a field rather than filtering,
so it becomes its own matching clause. `view` is not here — it is carried on
`ParsedQuery.view` and settled by the caller against the route's `view=`
parameter (`effective_view`).
"""

INT_FIELDS: frozenset[str] = frozenset({"congress", "year", "volume", "number"})
"""Index fields whose filter values are sent as integers."""

_NUMERIC_SCOPES = frozenset({"congress", "year", "vol"})

_SCOPE_TOKEN = re.compile(r"^([a-zA-Z]+):(.*)$")

_TOKENS = re.compile(r'[a-zA-Z]+:"[^"]*"|"[^"]*"|\S+')
"""Whitespace-separated tokens, except that a double-quoted run is one token —
including one carrying a scope prefix. Without the first alternative
`heading:"wild horses"` parses as the scope value `"wild` plus a stray
`horses"` in the free text."""

_LAW_NUMBER = re.compile(r"^(\d+)-(\d+)$")
_PLAIN_WORDS = re.compile(r"^[\w\s]+$", re.UNICODE)


@dataclass(frozen=True)
class ParsedQuery:
    """A reader's query, split into what filters and what matches."""

    text: str = ""
    """What is left after the scopes are lifted out; parsed by the cluster."""

    heading_terms: tuple[str, ...] = ()
    """`heading:water` — matched against the heading field alone."""

    filters: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Index field → the values asked for. Several values of one field are an
    OR (`congress:117 congress:118` is either); several fields are an AND."""

    view: str | None = None
    """`view:compiled` written in the query rather than passed as `?view=`.
    The caller settles the two — see `effective_view`."""

    def is_empty(self) -> bool:
        """Nothing left to search: no text, no heading term, no filter.

        `view:` alone does not make a query. It narrows an answer; it is not
        one.
        """
        return not (self.text or self.heading_terms or self.filters)


def law_identifier_of(value: str) -> str:
    """`117-328` → `/us/pl/117/328`; an identifier is kept as written.

    `law:` filters on the whole identifier rather than on congress plus number,
    so one keyword term answers for every kind: a private law
    (`law:/us/pvtl/81/375`) and a chapter-era act
    (`law:/us/act/1890-07-02/ch647`) are named the same way a public law is.
    The bare `117-328` form is the public-law one because that is the form
    readers write.
    """
    value = value.strip()
    match = _LAW_NUMBER.match(value)
    return f"/us/pl/{match.group(1)}/{match.group(2)}" if match else value


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _scope_value(name: str, value: str) -> str | None:
    """The stored form of a scope value, or None when the token is not one.

    A token this returns None for stays in the free text, so a reader's colon
    is a search rather than an empty result set.
    """
    if not value:
        return None
    if name == "law":
        return law_identifier_of(value)
    if name in _NUMERIC_SCOPES:
        return value if value.isdigit() else None
    if name == "kind":
        return value.lower() if value.lower() in KINDS else None
    if name == "view":
        return value.lower() if value.lower() in VIEWS else None
    return value


def parse_query(q: str) -> ParsedQuery:
    """Lift the `field:value` scopes out of a query string.

    A token whose prefix is not a scope this site implements, or whose value
    the scope cannot mean (`congress:soon`, `kind:statute`), is left in the
    text untouched.
    """
    text_parts: list[str] = []
    heading_terms: list[str] = []
    filters: dict[str, list[str]] = {}
    view: str | None = None

    for token in _TOKENS.findall(q):
        match = _SCOPE_TOKEN.match(token)
        if match is None:
            text_parts.append(token)
            continue

        name = match.group(1).lower()
        if name != "view" and name not in SCOPE_FIELDS:
            text_parts.append(token)
            continue

        value = _scope_value(name, _unquote(match.group(2)).strip())
        if value is None:
            text_parts.append(token)
        elif name == "view":
            view = value
        elif name == "heading":
            heading_terms.append(value)
        else:
            filters.setdefault(SCOPE_FIELDS[name], []).append(value)

    return ParsedQuery(
        text=" ".join(text_parts),
        heading_terms=tuple(heading_terms),
        filters={key: tuple(values) for key, values in filters.items()},
        view=view,
    )


def unparse_query(parsed: ParsedQuery) -> str:
    """A `ParsedQuery` written back as something a reader could have typed.

    The facet links spend this: adding a filter edits the query, so the query
    string stays the one place a search is written down and a filtered search
    is citable by its URL alone.
    """
    parts: list[str] = []
    if parsed.text:
        parts.append(parsed.text)
    parts.extend(f"heading:{_quote_if_spaced(term)}" for term in parsed.heading_terms)
    for name, index_field in SCOPE_FIELDS.items():
        if name == "heading":
            continue
        for value in parsed.filters.get(index_field, ()):
            parts.append(f"{name}:{_quote_if_spaced(value)}")
    if parsed.view:
        parts.append(f"view:{parsed.view}")
    return " ".join(parts)


def _quote_if_spaced(value: str) -> str:
    return f'"{value}"' if " " in value else value


def with_filter(parsed: ParsedQuery, name: str, value: str) -> ParsedQuery:
    """The same query with one more `name:value` scope. Idempotent.

    `name` is a scope word (`congress`, `kind`, `view`, `law`, `year`, `vol`).
    A value the scope cannot mean is ignored, so a facet link built from a
    stale answer cannot produce a query that means something else.
    """
    stored = _scope_value(name, value.strip())
    if stored is None:
        return parsed
    if name == "view":
        return replace(parsed, view=stored)
    if name == "heading":
        if stored in parsed.heading_terms:
            return parsed
        return replace(parsed, heading_terms=parsed.heading_terms + (stored,))
    index_field = SCOPE_FIELDS[name]
    existing = parsed.filters.get(index_field, ())
    if stored in existing:
        return parsed
    return replace(parsed, filters={**parsed.filters, index_field: existing + (stored,)})


def without_filter(parsed: ParsedQuery, name: str, value: str) -> ParsedQuery:
    """The same query with one `name:value` scope removed."""
    stored = _scope_value(name, value.strip())
    if stored is None:
        return parsed
    if name == "view":
        return replace(parsed, view=None) if parsed.view == stored else parsed
    if name == "heading":
        return replace(
            parsed, heading_terms=tuple(t for t in parsed.heading_terms if t != stored)
        )
    index_field = SCOPE_FIELDS[name]
    remaining = tuple(v for v in parsed.filters.get(index_field, ()) if v != stored)
    filters = dict(parsed.filters)
    if remaining:
        filters[index_field] = remaining
    else:
        filters.pop(index_field, None)
    return replace(parsed, filters=filters)


def effective_view(parsed: ParsedQuery, requested: str | None = None) -> str:
    """Which view a search reads: `view:` in the query, else `?view=`, else
    `enacted`. A value that is not one of `VIEWS` is the default."""
    for candidate in (parsed.view, requested):
        if candidate in VIEWS:
            return candidate  # type: ignore[return-value]
    return DEFAULT_VIEW


def _text_clause(text: str, fields: Iterable[str]) -> dict[str, Any]:
    return {
        "simple_query_string": {
            "query": text,
            "fields": list(fields),
            # Every word must appear. The default is OR, which ranks "matched
            # either" against "matched both" and buries the second.
            "default_operator": "and",
            "flags": QUERY_SYNTAX_FLAGS,
            "analyze_wildcard": True,
        }
    }


def _phrase_clauses(text: str) -> list[dict[str, Any]]:
    """The proximity boost, when the query is one a phrase match can mean.

    Skipped for a single word, and for anything carrying operator characters:
    `match_phrase` has no operator syntax, so `park | forest` would be scored
    as a search for the literal word `|`.
    """
    if len(text.split()) < 2 or not _PLAIN_WORDS.match(text):
        return []
    return [
        {"match_phrase": {"text": {"query": text, "slop": PHRASE_SLOP, "boost": PHRASE_BOOST}}},
        {
            "match_phrase": {
                "heading": {"query": text, "slop": PHRASE_SLOP, "boost": HEADING_PHRASE_BOOST}
            }
        },
    ]


def _filter_clause(index_field: str, values: tuple[str, ...]) -> dict[str, Any]:
    if index_field in INT_FIELDS:
        return {"terms": {index_field: [int(v) for v in values]}}
    return {"terms": {index_field: list(values)}}


def _sort_clause(sort: str) -> list[Any]:
    if sort == "date":
        return [{"enacted": {"order": "desc", "missing": "_last"}}, "_score"]
    if sort == "citation":
        # Missing last: a document with no `citation_sort` belongs at the end
        # rather than at the front of the volume.
        return [{"citation_sort": {"order": "asc", "missing": "_last"}}, "_score"]
    return ["_score"]


HIGHLIGHT: dict[str, Any] = {
    "pre_tags": ["<em>"],
    "post_tags": ["</em>"],
    "fields": {
        "heading": {"number_of_fragments": 1},
        # 220 characters is about two lines at the reading width and usually
        # reaches a sentence boundary; the default 100 lands mid-clause.
        "text": {"number_of_fragments": 2, "fragment_size": 220},
    },
    "no_match_size": 0,
}


def build_search_body(
    parsed: ParsedQuery,
    *,
    view: str = DEFAULT_VIEW,
    sort: str = "relevance",
    limit: int = 20,
    offset: int = 0,
    facets: bool = False,
) -> dict[str, Any]:
    """The OpenSearch request body for one search.

    `view` is the view to read, already settled between the query's `view:` and
    the route's `?view=` (`effective_view`): `enacted` and `compiled` filter on
    the `view` field, `all` filters neither.

    `sort` is one of `SORTS`; `relevance` sends no sort at all. `facets` adds
    the `congress`, `kind` and `view` aggregations.
    """
    must: list[dict[str, Any]] = []
    if parsed.text:
        must.append(_text_clause(parsed.text, FIELDS))
    for term in parsed.heading_terms:
        must.append(_text_clause(term, ["heading"]))

    should = _phrase_clauses(parsed.text) if parsed.text else []

    filters: list[dict[str, Any]] = [
        _filter_clause(index_field, values)
        for index_field, values in sorted(parsed.filters.items())
    ]
    if view in ("enacted", "compiled"):
        filters.append({"term": {"view": view}})

    query: dict[str, Any] = {"bool": {"filter": filters}}
    if must:
        query["bool"]["must"] = must
    if should:
        query["bool"]["should"] = should

    body: dict[str, Any] = {
        "from": offset,
        "size": limit,
        "query": query,
        "highlight": HIGHLIGHT,
        # OpenSearch stops counting at 10,000 by default and reports the cap as
        # the total.
        "track_total_hits": True,
    }

    if sort != "relevance":
        body["sort"] = _sort_clause(sort)

    if facets:
        body["aggs"] = {
            "congress": {"terms": {"field": "congress", "size": 30}},
            "kind": {"terms": {"field": "kind", "size": len(KINDS)}},
            "view": {"terms": {"field": "view", "size": 2}},
        }

    return body
