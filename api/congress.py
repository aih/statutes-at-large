"""Historical analysis of Acts by Congress: `/api/v1/congress`.

Endpoints serving Acts enacted per Congress from the 1st Congress on,
cross-referenced to the United States Code and OLRC classification tables
(Issue #19).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.comps import origins
from api.schemas import (
    ClassificationSessionUrlOut,
    CongressDetailOut,
    CongressesOverviewOut,
    CongressLawCompOut,
    CongressLawItemOut,
    CongressSummaryOut,
    PendingLawOut,
)
from params import (
    RepositoryDep,
    congress_note,
    congresses_note,
    public_cache,
)
from storage import CongressDetail, CongressSummary, congress_ordinal

congress_router = APIRouter(prefix="/api/v1", tags=["congress"], dependencies=[Depends(public_cache)])


def _summary_out(summary: CongressSummary) -> CongressSummaryOut:
    classification_urls = [
        ClassificationSessionUrlOut(
            session="all" if s == 0 else str(s),
            url=f"{origins.uscode_origin}/app/classification/{summary.congress}/{'all' if s == 0 else s}",
        )
        for s in summary.classification_sessions
    ]
    return CongressSummaryOut(
        congress=summary.congress,
        ordinal=summary.ordinal,
        start_year=summary.start_year,
        end_year=summary.end_year,
        first_enacted=summary.first_enacted,
        last_enacted=summary.last_enacted,
        total_laws=summary.total_laws,
        public_laws=summary.public_laws,
        private_laws=summary.private_laws,
        chapter_acts=summary.chapter_acts,
        volumes=list(summary.volumes),
        section_count=summary.section_count,
        compilations_count=summary.compilations_count,
        classified_laws_count=summary.classified_laws_count,
        classification_sessions=list(summary.classification_sessions),
        cited_laws_count=summary.cited_laws_count,
        citing_sections_count=summary.citing_sections_count,
        pending_laws_count=summary.pending_laws_count,
        url=f"{origins.site_origin}/app/congress/{summary.congress}",
        uscode_classification_urls=classification_urls,
    )


@congress_router.get("/congress", response_model=CongressesOverviewOut)
def get_congresses(repository: RepositoryDep) -> CongressesOverviewOut:
    """Historical overview of Acts by Congress across all loaded Congresses."""
    overview = repository.congresses_overview()
    return CongressesOverviewOut(
        total_congresses=overview.total_congresses,
        total_laws=overview.total_laws,
        total_public_laws=overview.total_public_laws,
        total_private_laws=overview.total_private_laws,
        total_chapter_acts=overview.total_chapter_acts,
        total_sections=overview.total_sections,
        total_compilations=overview.total_compilations,
        note=congresses_note(overview),
        congresses=[_summary_out(s) for s in overview.congresses],
    )


@congress_router.get("/congress/{congress}", response_model=CongressDetailOut)
def get_congress_detail(
    congress: Annotated[int, Path(ge=1, le=200, description="The Congress number (1 to 200).")],
    repository: RepositoryDep,
    kind: Literal["pl", "pvtl", "act"] | None = Query(default=None, description="Filter by law kind."),
    has_comp: bool = Query(default=False, description="Filter to laws with a Statute Compilation."),
    cited: bool = Query(default=False, description="Filter to laws cited in the US Code or classified in OLRC tables."),
    q: str | None = Query(default=None, description="Search titles, citations, or identifiers."),
    sort: Literal["sequence", "date", "sections"] = Query(default="sequence", description="Sort order."),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CongressDetailOut:
    """Acts enacted by one Congress, with cross-references and filters."""
    detail = repository.congress_detail(
        congress,
        kind=kind,
        has_comp=has_comp,
        cited=cited,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"nothing for the {congress_ordinal(congress)} Congress in the loaded Statutes at Large volumes",
        )

    summary_out = _summary_out(detail.summary)

    laws_out: list[CongressLawItemOut] = []
    for law in detail.laws:
        comp_outs = [
            CongressLawCompOut(
                identifier_prefix=comp.identifier_prefix,
                display_title=comp.display_title,
                current_through_pl=comp.current.current_through_pl if comp.current else None,
                url=f"{origins.site_origin}/app{comp.identifier_prefix}",
            )
            for comp in law.compilations
        ]

        cited_by_url = (
            f"{origins.site_origin}/app{law.identifier}#cited-by"
            if law.usc_citing_sections_count > 0
            else None
        )

        uscode_classification_url = None
        if (
            law.usc_classifications_count > 0
            and law.number is not None
            and detail.summary.classification_sessions
        ):
            s = detail.summary.classification_sessions[0]
            session_str = "all" if s == 0 else str(s)
            uscode_classification_url = (
                f"{origins.uscode_origin}/app/classification/{congress}/{session_str}?pl={law.number}"
            )

        laws_out.append(
            CongressLawItemOut(
                identifier=law.identifier,
                kind=law.kind,
                congress=law.congress,
                number=law.number,
                chapter=law.chapter,
                label=law.label,
                citation=law.citation,
                volume=law.volume,
                page_first=law.page_first,
                enacted=law.enacted,
                official_title=law.official_title,
                short_titles=list(law.short_titles),
                section_count=law.section_count,
                url=f"{origins.site_origin}/app{law.identifier}",
                stat_url=(
                    f"{origins.site_origin}/app/us/stat/{law.volume}/{law.page_first}"
                    if law.page_first
                    else None
                ),
                compilations=comp_outs,
                usc_citing_sections_count=law.usc_citing_sections_count,
                cited_by_url=cited_by_url,
                usc_classifications_count=law.usc_classifications_count,
                usc_titles=list(law.usc_titles),
                uscode_classification_url=uscode_classification_url,
            )
        )

    pending_outs = [
        PendingLawOut(
            identifier=p.identifier,
            bill=p.bill_label,
            title=p.title,
            action_date=p.action_date,
            url=p.congress_gov_url,
            checked_at=p.checked_at,
        )
        for p in detail.pending_laws
    ]

    return CongressDetailOut(
        summary=summary_out,
        laws=laws_out,
        pending_laws=pending_outs,
        total=detail.total,
        limit=detail.limit,
        offset=detail.offset,
        note=congress_note(detail),
    )
