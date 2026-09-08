"""The machine surface: `/api/v1` (design section 5).

Two families:

  * `/api/v1/us/pl/…`, `/us/pvtl/…`, `/us/act/…`, `/us/stat/…` mirror the
    identifiers the US Code cites. One handler serves a law, a hierarchy node,
    a section, or a provision inside a section; the identifier decides which.
  * `/api/v1/laws/…`, `/labels`, `/status` are about the laws rather than
    being one of them.

No SQL and no resolution logic here (CLAUDE.md architecture rule 1): handlers
ask the `Repository` and shape the answer. Machine formats only: JSON by
default, verbatim USLM for `?format=xml` or an XML `Accept:`.

Stage 2 adds `/us/sComp/…` and the compiled view; `compiled_view` below is
where it plugs in.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from api.responses import compiled_not_found, stat_page_response, unit_response
from api.schemas import (
    CollectionStatusOut,
    ErrorOut,
    LabelFoundOut,
    LabelMissingOut,
    LabelOut,
    LabelsIn,
    LawSummaryOut,
    NotFoundOut,
    SourceCheckOut,
    StatPageOut,
    StatusOut,
    UnitOut,
)
from params import (
    MACHINE_FORMATS,
    FormatParam,
    RepositoryDep,
    ThroughParam,
    ViewParam,
    negotiated_format,
    normalize_identifier,
    not_found,
    public_cache,
    rate_limit,
)
from storage import Repository, normalize_page

api = APIRouter(prefix="/api/v1", tags=["api"], dependencies=[Depends(public_cache)])

COLLECTIONS = ("STATUTE", "COMPS", "PLAW")

_limit_labels = rate_limit("labels", capacity=300, per_second=30.0)
"""A server's budget: the US Code site calls `labels` once per rendered page."""


# ------------------------------------------------------------- enacted units


@dataclass
class UnitQuery:
    """The query parameters every identifier route takes."""

    view: ViewParam = None
    format: FormatParam = None
    through: ThroughParam = None


UnitQueryDep = Annotated[UnitQuery, Depends()]

_UNIT_RESPONSES = {
    200: {"content": {"application/json": {"schema": UnitOut.model_json_schema()}, "application/xml": {}}},
    304: {"description": "The caller's `If-None-Match` matched the ETag."},
    404: {"model": NotFoundOut},
}


def enacted_unit(request: Request, repository: Repository, identifier: str, query: UnitQuery) -> Response:
    """Resolve an identifier in the requested view and answer in the negotiated format."""
    path = normalize_identifier(identifier)
    if query.view == "compiled":
        return compiled_view(request, repository, path, query)
    result = repository.get_unit(path)
    if result is None:
        raise HTTPException(status_code=404, detail=not_found(path))
    wanted = negotiated_format(request, query.format, allowed=MACHINE_FORMATS)
    return unit_response(request, repository, result, wanted)


def compiled_view(request: Request, repository: Repository, path: str, query: UnitQuery) -> Response:
    """`view=compiled` for an enacted identifier: the compiled counterpart the
    alternatives name (ADR-0007, decision 5), served in the compiled shape with
    `X-Requested-Identifier` naming the enacted form asked for. With no
    counterpart, a 404 that carries the alternatives the unit does have."""
    from api.alternatives import alternatives_for, compiled_link
    from api.comps import compiled_response

    enacted = repository.get_unit(path)
    if enacted is None:
        raise HTTPException(status_code=404, detail=not_found(path))
    target = compiled_link(alternatives_for(repository, enacted))
    if target is None:
        return compiled_not_found(repository, path, enacted)
    if enacted.provision is not None and enacted.provision.found:
        # `/us/pl/83/703/s1/a` → the same sub-path under the compiled section.
        below = enacted.provision.identifier[len(enacted.served_identifier):]
        target = f"{target}{below}"
    response = compiled_response(request, repository, target, query.through, query.format)
    response.headers["X-Requested-Identifier"] = path
    return response


@api.get(
    "/us/pl/{congress}/{number}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A public law",
)
def public_law(
    congress: int, number: int, request: Request, repository: RepositoryDep, query: UnitQueryDep
) -> Response:
    """The law: its summary, its table of contents as `children`, and the whole
    `pLaw` element for `format=xml`."""
    return enacted_unit(request, repository, f"/us/pl/{congress}/{number}", query)


@api.get(
    "/us/pl/{congress}/{number}/{path:path}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A section or lower level of a public law",
)
def public_law_unit(
    congress: int, number: int, path: str, request: Request, repository: RepositoryDep, query: UnitQueryDep
) -> Response:
    """`{path}` is GPO's PLAW form: `tI/s101`, `s3/1`. A path below a section
    returns the section with that provision cut out as `provision` (`format=xml`
    returns the provision alone). A section number under the wrong hierarchy
    is found by number (design section 3, rule 3); a path nothing is stored at
    is answered by its longest stored prefix (rule 2). `note` and
    `served_identifier` say which rule answered."""
    return enacted_unit(request, repository, f"/us/pl/{congress}/{number}/{path}", query)


@api.get(
    "/us/pvtl/{congress}/{number}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A private law",
)
def private_law(
    congress: int, number: int, request: Request, repository: RepositoryDep, query: UnitQueryDep
) -> Response:
    """The private law, same shape as a public law."""
    return enacted_unit(request, repository, f"/us/pvtl/{congress}/{number}", query)


@api.get(
    "/us/pvtl/{congress}/{number}/{path:path}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A section or lower level of a private law",
)
def private_law_unit(
    congress: int, number: int, path: str, request: Request, repository: RepositoryDep, query: UnitQueryDep
) -> Response:
    """Same resolution as a public law's path."""
    return enacted_unit(request, repository, f"/us/pvtl/{congress}/{number}/{path}", query)


@api.get(
    "/us/act/{date}/ch{chapter}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A chapter-numbered act",
)
def act(
    date: datetime.date, chapter: int, request: Request, repository: RepositoryDep, query: UnitQueryDep
) -> Response:
    """An act by its date and chapter. A law from 1901 to 1957 answers here and
    under its law number; `served_identifier` carries the primary form and
    `resolution` is `alias`."""
    return enacted_unit(request, repository, f"/us/act/{date.isoformat()}/ch{chapter}", query)


@api.get(
    "/us/act/{date}/ch{chapter}/{path:path}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A section or lower level of a chapter-numbered act",
)
def act_unit(
    date: datetime.date,
    chapter: int,
    path: str,
    request: Request,
    repository: RepositoryDep,
    query: UnitQueryDep,
) -> Response:
    """Same resolution as a public law's path."""
    return enacted_unit(request, repository, f"/us/act/{date.isoformat()}/ch{chapter}/{path}", query)


# ---------------------------------------------------------------- stat pages


@api.get(
    "/us/stat/{volume}/{page}",
    response_model=None,
    responses={200: {"model": StatPageOut}, 404: {"model": ErrorOut}},
    summary="Every law on a Statutes at Large page",
)
def stat_page(volume: int, page: str, request: Request, repository: RepositoryDep) -> Response:
    """The laws that start on or span the page, with the unit the page marker
    falls in, and the GovInfo link to the printed page. Page labels are matched
    lower case (`a12`, `B3` → `b3`)."""
    label = normalize_page(page)
    result = repository.stat_page(volume, label)
    if result is None:
        raise HTTPException(status_code=404, detail=not_found(f"/us/stat/{volume}/{label}"))
    return stat_page_response(request, result)


# -------------------------------------------------------------------- labels


def _labels(repository: Repository, identifiers: list[str]) -> dict[str, LabelOut]:
    paths = [normalize_identifier(one) for one in identifiers]
    found = repository.labels(paths)
    return {path: (LabelFoundOut.of(found[path]) if path in found else LabelMissingOut()) for path in paths}


@api.post(
    "/labels",
    response_model=dict[str, LabelOut],
    responses={422: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    summary="Resolution and heading for many identifiers at once",
    dependencies=[Depends(_limit_labels)],
)
def labels(
    repository: RepositoryDep,
    body: Annotated[
        LabelsIn,
        Body(examples=[{"identifiers": ["/us/pl/81/740/s3", "/us/act/1950-08-30/ch823", "/us/pl/81/1"]}]),
    ],
) -> dict[str, LabelOut]:
    """Between 1 and 100 identifiers per request. Every requested identifier
    appears in the answer: `{exists: true, …}` with the served identifier,
    resolution, heading and law for the ones that resolve, `{exists: false}`
    for the rest. What the US Code site's `resolveRef` calls."""
    return _labels(repository, body.identifiers)


@api.get(
    "/labels",
    response_model=dict[str, LabelOut],
    responses={422: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    summary="Resolution and heading for many identifiers at once (query form)",
    dependencies=[Depends(_limit_labels)],
)
def labels_by_query(
    repository: RepositoryDep,
    identifier: Annotated[
        list[str],
        Query(
            description="Repeat once per identifier, 1 to 100 per request.",
            examples=[["/us/pl/81/740/s3", "/us/act/1950-08-30/ch823"]],
            min_length=1,
            max_length=100,
        ),
    ],
) -> dict[str, LabelOut]:
    """The same answer as `POST /labels`, for callers that cannot send a body."""
    return _labels(repository, identifier)


# -------------------------------------------------------------------- status


@api.get("/status", response_model=StatusOut, summary="What is loaded, and when the sources were last polled")
def status(repository: RepositoryDep) -> StatusOut:
    """Per collection (`STATUTE`, `COMPS`, `PLAW`): packages loaded, the newest
    one, and the counts; and the last poll of its source. `stale` is true when
    a collection with packages has no recorded check or one older than a week
    (`storage.SOURCE_CHECK_STALE_AFTER`)."""
    collections = {c: CollectionStatusOut.of(repository.collection_status(c)) for c in COLLECTIONS}
    checks: dict[str, SourceCheckOut | None] = {}
    for collection in COLLECTIONS:
        check = repository.last_source_check(collection)
        checks[collection] = SourceCheckOut.of(check) if check is not None else None
    stale = any(
        collections[c].packages_loaded > 0 and (checks[c] is None or checks[c].stale) for c in COLLECTIONS
    )
    return StatusOut(collections=collections, checks=checks, stale=stale)


# ---------------------------------------------------------------------- laws


@api.get(
    "/laws/{congress}/{number}",
    response_model=LawSummaryOut,
    responses={404: {"model": ErrorOut}},
    summary="A public law's summary",
)
def law_summary(congress: int, number: int, repository: RepositoryDep) -> LawSummaryOut:
    """Titles, dates, citation, the table of contents with identifiers, and the
    compilations loaded for the law."""
    identifier = f"/us/pl/{congress}/{number}"
    summary = repository.get_law(identifier)
    if summary is None:
        raise HTTPException(status_code=404, detail=not_found(identifier))
    return LawSummaryOut.of(summary, repository.compilations_for_law(summary.law.identifier))


@api.get(
    "/laws/{congress}/{number}/sections/{num}",
    response_model=None,
    responses=_UNIT_RESPONSES,
    summary="A section of a public law by number, ignoring hierarchy",
)
def law_section(
    congress: int,
    number: int,
    num: str,
    request: Request,
    repository: RepositoryDep,
    format: FormatParam = None,
) -> Response:
    """Design section 3, rule 3 on its own: `/laws/81/910/sections/101` answers
    with `/us/pl/81/910/tI/s101`. Same body and headers as the identifier routes."""
    identifier = f"/us/pl/{congress}/{number}"
    result = repository.get_section_by_number(identifier, num)
    if result is None:
        raise HTTPException(status_code=404, detail=not_found(f"{identifier}/s{num}"))
    wanted = negotiated_format(request, format, allowed=MACHINE_FORMATS)
    return unit_response(request, repository, result, wanted)
