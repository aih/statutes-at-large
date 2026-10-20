"""Acts by Congress: `/api/v1/congress` and `/api/v1/congress/{congress}`
(ADR-0033).

Every count is of loaded laws and is the total its filter returns. A law's
`url`, `stat_url` and compilation `url`s are citation URLs; a table link is
the US Code site's `/app/classification/{congress}/{session}?pl={n}`, where a
whole-congress table's session is `all`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.schemas import (
    ClassificationSessionUrlOut,
    CongressDetailOut,
    CongressesOverviewOut,
    CongressLawCompOut,
    CongressLawItemOut,
    CongressSummaryOut,
    PendingLawOut,
    VolumeStartOut,
)
from params import (
    RepositoryDep,
    congress_note,
    congresses_note,
    origins,
    public_cache,
)
from storage import CongressLawItem, CongressSummary, congress_ordinal

congress_router = APIRouter(prefix="/api/v1", tags=["congress"], dependencies=[Depends(public_cache)])


def _session_segment(session: int) -> str:
    """The US Code site writes a whole-congress table's session 0 as `all`."""
    return "all" if session == 0 else str(session)


def _table_url(congress: int, session: int) -> str:
    return f"{origins.uscode_origin}/app/classification/{congress}/{_session_segment(session)}"


def _summary_out(summary: CongressSummary) -> CongressSummaryOut:
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
        public_acts=summary.public_acts,
        private_acts=summary.private_acts,
        volumes=list(summary.volumes),
        section_count=summary.section_count,
        compilations_count=summary.compilations_count,
        compiled_laws_count=summary.compiled_laws_count,
        classified_laws_count=summary.classified_laws_count,
        classification_sessions=list(summary.classification_sessions),
        cited_laws_count=summary.cited_laws_count,
        citing_sections_count=summary.citing_sections_count,
        pending_laws_count=summary.pending_laws_count,
        url=f"{origins.site_origin}/app/congress/{summary.congress}",
        uscode_classification_urls=[
            ClassificationSessionUrlOut(session=_session_segment(s), url=_table_url(summary.congress, s))
            for s in summary.classification_sessions
        ],
    )


def _law_out(law: CongressLawItem) -> CongressLawItemOut:
    url = f"{origins.site_origin}{law.identifier}"
    return CongressLawItemOut(
        identifier=law.identifier,
        kind=law.kind,
        public_private=law.public_private,
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
        url=url,
        stat_url=f"{origins.site_origin}/us/stat/{law.volume}/{law.page_first}" if law.page_first else None,
        compilations=[
            CongressLawCompOut(
                identifier_prefix=comp.identifier_prefix,
                display_title=comp.display_title,
                current_through_pl=comp.current.current_through_pl if comp.current else None,
                url=f"{origins.site_origin}{comp.identifier_prefix}",
            )
            for comp in law.compilations
        ],
        usc_citing_sections_count=law.usc_citing_sections_count,
        cited_by_url=f"{url}#cited-by" if law.usc_citing_sections_count else None,
        usc_classifications_count=law.usc_classifications_count,
        usc_titles=list(law.usc_titles),
        uscode_classification_url=(
            f"{_table_url(law.congress, law.classification_session)}?pl={law.number}"
            if law.classification_session is not None
            else None
        ),
    )


@congress_router.get("/congress", response_model=CongressesOverviewOut)
def get_congresses(repository: RepositoryDep) -> CongressesOverviewOut:
    """Every Congress from the 1st to the latest with a loaded or a pending law."""
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
    congress: Annotated[int, Path(ge=1, le=200, description="The Congress number.")],
    repository: RepositoryDep,
    kind: Literal["pl", "pvtl", "act"] | None = Query(default=None, description="Public laws, private laws, or chapter acts."),
    public_private: Literal["public", "private"] | None = Query(
        default=None, description="Public laws and public chapter acts, or private laws and private chapter acts."
    ),
    has_comp: bool = Query(default=False, description="Only laws with a Statute Compilation."),
    cited: bool = Query(default=False, description="Only laws a US Code section cites."),
    classified: bool = Query(default=False, description="Only public laws in an OLRC classification table."),
    q: str | None = Query(default=None, description="Words of a title, a citation, or an identifier."),
    sort: Literal["sequence", "date", "sections"] = Query(default="sequence"),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CongressDetailOut:
    """One page of a Congress's laws, with their cross-references."""
    detail = repository.congress_detail(
        congress,
        kind=kind,
        public_private=public_private,
        has_comp=has_comp,
        cited=cited,
        classified=classified,
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
    return CongressDetailOut(
        summary=_summary_out(detail.summary),
        latest_congress=detail.latest_congress,
        volume_starts=[
            VolumeStartOut(
                volume=v.volume,
                page=v.page,
                url=f"{origins.site_origin}/us/stat/{v.volume}/{v.page}" if v.page is not None else None,
            )
            for v in detail.volume_starts
        ],
        laws=[_law_out(law) for law in detail.laws],
        pending_laws=[
            PendingLawOut(
                identifier=p.identifier,
                bill=p.bill_label,
                title=p.title,
                action_date=p.action_date,
                url=p.congress_gov_url,
                checked_at=p.checked_at,
            )
            for p in detail.pending_laws
        ],
        total=detail.total,
        limit=detail.limit,
        offset=detail.offset,
        note=congress_note(detail),
    )
