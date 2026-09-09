"""`GET /api/v1/search`: keyword search over the units and compiled sections
that carry text (ADR-0023).

The query is built in `storage/searchquery.py`, not here, so a test can score
the ranking that ships rather than a second copy of the builder. This module
only validates the request, calls the cluster, and shapes the answer: it
imports `storage.search` and `storage.searchquery` and nothing from
`ingest/` (architecture rule 1).
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from opensearchpy import OpenSearch
from pydantic import BaseModel

from params import SEARCH_UNAVAILABLE, public_cache, rate_limit, search_note
from storage.search import UNITS_ALIAS, SearchNotConfigured, get_search_client
from storage.searchquery import (
    DEFAULT_VIEW,
    SORTS,
    build_search_body,
    effective_view,
    parse_query,
)

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"

search_router = APIRouter(prefix=API_PREFIX, tags=["search"], dependencies=[Depends(public_cache)])

_limit_search = rate_limit("search", capacity=120, per_second=10.0)

MAX_OFFSET = 1000
"""Deep paging is bounded here rather than left to OpenSearch: past
`max_result_window` (10,000 by default) the cluster throws, so an unbounded
`offset` is a 500 from a query string. A thousand results deep is past where
a keyword search is useful."""


def search_client_dependency() -> OpenSearch:
    """The cluster's client; a deployment with no `SEARCH_PASSWORD` answers
    503 with the same sentence a failing cluster does, the reason in the log."""
    try:
        return get_search_client()
    except SearchNotConfigured:
        log.warning("search is not configured: SEARCH_PASSWORD is unset")
        raise HTTPException(status_code=503, detail=SEARCH_UNAVAILABLE) from None


SearchClientDep = Annotated[OpenSearch, Depends(search_client_dependency)]


# ------------------------------------------------------------------- schemas


class FacetValue(BaseModel):
    value: str
    count: int


class SearchFacets(BaseModel):
    """Counts over the whole result set, not the page. Each one is a filter a
    facet link adds to the query (`congress:117`, `kind:pl`, `view:compiled`)."""

    congress: list[FacetValue] = []
    kind: list[FacetValue] = []
    view: list[FacetValue] = []


class SearchResult(BaseModel):
    identifier: str
    law_identifier: Optional[str] = None
    law_label: Optional[str] = None
    level: Optional[str] = None
    num: Optional[str] = None
    heading: Optional[str] = None
    snippets: list[str] = []
    enacted: Optional[str] = None
    citation: Optional[str] = None
    view: str
    comp_prefix: Optional[str] = None
    url: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    facets: SearchFacets
    note: str


# ---------------------------------------------------------------------- route


@search_router.get(
    "/search",
    response_model=SearchResponse,
    responses={400: {"description": "Bad `sort`, or a query with nothing to search for."}, 503: {"description": "The cluster is unavailable."}},
    summary="Keyword search over the laws as enacted and as compiled",
    dependencies=[Depends(_limit_search)],
)
def search(
    client: SearchClientDep,
    q: Annotated[
        str,
        Query(
            description="The keyword or phrase to search for. Accepts the scopes law:, congress:, year:, vol:, kind:, view: and heading:, and quoted phrases.",
            min_length=1,
            max_length=500,
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
    sort: Annotated[str, Query(description="relevance, date or citation.")] = "relevance",
    view: Annotated[
        Optional[str],
        Query(description="enacted (default), compiled, or all. `view:` in the query wins over this."),
    ] = None,
) -> SearchResponse:
    """`enacted` reads the laws as printed in the Statutes at Large; `compiled`
    reads a Statute Compilation's current version; `all` filters neither, so
    an enacted and a compiled section are two answers. A cluster failure is a
    503; the exception goes to the log, not to the caller."""
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of: {', '.join(SORTS)}")

    parsed = parse_query(q)
    if parsed.is_empty():
        raise HTTPException(status_code=400, detail="that query has nothing to search for")

    resolved_view = effective_view(parsed, view)
    body = build_search_body(parsed, view=resolved_view, sort=sort, limit=limit, offset=offset, facets=True)

    try:
        response = client.search(index=UNITS_ALIAS, body=body)
    except Exception:
        log.exception("search query failed")
        raise HTTPException(status_code=503, detail=SEARCH_UNAVAILABLE) from None

    hits = response["hits"]["hits"]
    total_raw = response["hits"]["total"]
    total = total_raw["value"] if isinstance(total_raw, dict) else total_raw

    results = [_result_of(hit) for hit in hits]
    facets = _facets(response.get("aggregations", {}))

    return SearchResponse(results=results, total=total, facets=facets, note=search_note(resolved_view))


def _result_of(hit: dict) -> SearchResult:
    source = hit["_source"]
    identifier = source["identifier"]
    return SearchResult(
        identifier=identifier,
        law_identifier=source.get("law_identifier"),
        law_label=source.get("law_label"),
        level=source.get("level"),
        num=source.get("num"),
        heading=source.get("heading"),
        snippets=hit.get("highlight", {}).get("text", []),
        enacted=source.get("enacted"),
        citation=source.get("citation"),
        view=source.get("view", DEFAULT_VIEW),
        comp_prefix=source.get("comp_prefix"),
        url=f"/app{identifier}",
    )


def _facets(aggregations: dict) -> SearchFacets:
    def values(name: str) -> list[FacetValue]:
        buckets = aggregations.get(name, {}).get("buckets", [])
        return [FacetValue(value=str(bucket["key"]), count=bucket["doc_count"]) for bucket in buckets]

    return SearchFacets(congress=values("congress"), kind=values("kind"), view=values("view"))
