"""`GET /api/v1/search`: keyword search over the units and compiled sections
that carry text (ADR-0023).

The query is built in `storage/searchquery.py`, not here, so a test can score
the ranking that ships rather than a second copy of the builder. This module
validates the request, calls the cluster, asks the `Repository` for the acts
the words name (`acts`, first page only; ADR-0032), and shapes the answer: it
imports `storage` and nothing from `ingest/` (architecture rule 1).
"""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from opensearchpy import OpenSearch
from pydantic import BaseModel, Field

from api.comps_schemas import CurrentThroughOut
from params import SEARCH_UNAVAILABLE, RepositoryDep, origins, public_cache, rate_limit, search_note
from storage import ActMatch, Repository
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


class SearchUscHistoryItem(BaseModel):
    identifier: str = Field(description="A law, a provision, or a Statutes at Large page, as cited.")
    label: str = Field(description="`Public Law 102-486, title IX, § 902(a)(8)`, `106 Stat. 2944`.")
    date: Optional[datetime.date] = None


class SearchCanonicalUsc(BaseModel):
    """The US Code section whose Short Title note names the act, else the
    first one whose source credit names it as enacting the section."""

    identifier: str
    citation: Optional[str] = None
    heading: Optional[str] = None
    url: str
    context: str = Field(description="`note` or `sourceCredit`.")
    note_topic: Optional[str] = Field(None, description="`shortTitle` for a note.")
    history: list[SearchUscHistoryItem] = Field([], description="The refs of that note or source credit, in order.")
    citing_sections_count: int = Field(0, description="US Code sections that cite the act anywhere.")


class SearchCompilationMatch(BaseModel):
    identifier: str = Field(description="The compilation's prefix: `/us/sComp/83/703`.")
    package_id: str
    current_through: Optional[CurrentThroughOut] = None
    url: str


class SearchLawMatch(BaseModel):
    identifier: str
    label: str
    aliases: list[str] = []
    citation: Optional[str] = None
    enacted: Optional[datetime.date] = None
    official_title: Optional[str] = None


class SearchActMatch(BaseModel):
    title: str
    short_titles: list[str] = []
    compilation: Optional[SearchCompilationMatch] = None
    law: Optional[SearchLawMatch] = None
    canonical_usc: Optional[SearchCanonicalUsc] = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    facets: SearchFacets
    note: str
    acts: list[SearchActMatch] = Field(
        [], description="Acts whose popular name the words match, on the first page only (ADR-0032)."
    )


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
    repo: RepositoryDep,
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
    503; the exception goes to the log, not to the caller. On the first page
    `acts` lists the acts whose popular name the words match (ADR-0032); a
    database failure there is logged and leaves `acts` empty."""
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

    acts = _acts(repo, parsed.text) if offset == 0 and parsed.text else []

    return SearchResponse(results=results, total=total, facets=facets, note=search_note(resolved_view), acts=acts)


def _acts(repository: Repository, text: str) -> list[SearchActMatch]:
    """The act cards; a failure is logged and answers none, so the results
    are served without them."""
    try:
        return [_act_of(match) for match in repository.act_matches(text)]
    except Exception:
        log.warning("act_matches failed; answering without acts", exc_info=True)
        return []


def _act_of(match: ActMatch) -> SearchActMatch:
    comp, law, usc = match.compilation, match.law, match.canonical_usc
    compilation = None
    if comp is not None:
        current = comp.current
        through = None
        if current is not None and (current.current_through_pl or current.current_through_date):
            through = CurrentThroughOut(pl=current.current_through_pl, enacted=current.current_through_date)
        compilation = SearchCompilationMatch(
            identifier=comp.identifier_prefix,
            package_id=comp.package_id,
            current_through=through,
            url=f"{origins.site_origin}{comp.identifier_prefix}",
        )
    return SearchActMatch(
        title=match.title,
        short_titles=list(match.short_titles),
        compilation=compilation,
        law=SearchLawMatch(
            identifier=law.identifier,
            label=law.label,
            aliases=list(law.aliases),
            citation=law.citation,
            enacted=law.enacted,
            official_title=law.official_title,
        )
        if law is not None
        else None,
        canonical_usc=SearchCanonicalUsc(
            identifier=usc.identifier,
            citation=usc.citation,
            heading=usc.heading,
            url=f"{origins.uscode_origin}{usc.identifier}",
            context=usc.context,
            note_topic=usc.note_topic,
            history=[SearchUscHistoryItem(identifier=h.identifier, label=h.label, date=h.date) for h in usc.history],
            citing_sections_count=usc.citing_sections_count,
        )
        if usc is not None
        else None,
    )


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
        url=f"{origins.site_origin}{identifier}",
    )


def _facets(aggregations: dict) -> SearchFacets:
    def values(name: str) -> list[FacetValue]:
        buckets = aggregations.get(name, {}).get("buckets", [])
        return [FacetValue(value=str(bucket["key"]), count=bucket["doc_count"]) for bucket in buckets]

    return SearchFacets(congress=values("congress"), kind=values("kind"), view=values("view"))
