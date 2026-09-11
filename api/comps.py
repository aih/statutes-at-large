"""The compiled view: `/api/v1/us/sComp/…`, `/api/v1/comps`, `/api/v1/comps/{fileId}`
(design sections 4 and 5).

Everything is answered by the `Repository`; this module shapes the JSON, the
note, the `alternatives`, and the caching headers. A compiled unit is
`immutable` only when the caller pinned a stored version with `through=` and
was served exactly that; otherwise it revalidates against the ETag.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.comps_schemas import (
    CompDetailOut,
    CompilationOut,
    CompListOut,
    CompOut,
    CompUnitOut,
    CompVersionOut,
    CurrencyOut,
    CurrentThroughOut,
    LawOut,
    ProvenanceOut,
    ProvisionOut,
    UnitRefOut,
)
from params import (
    FormatParam,
    MACHINE_FORMATS,
    RepositoryDep,
    ThroughParam,
    cache_control,
    compiled_note,
    if_none_match,
    negotiated_format,
    not_found,
    public_cache,
    served_note,
    serves_xml,
)
from storage import CompRef, CompUnitResult, CompVersionRef, Repository, UnitRef

API_PREFIX = "/api/v1"
TEXT_PROVENANCE = "gpo-uslm"
IDENTIFIER_PROVENANCE = "gpo-uslm"
FIRST_NUMBERED_CONGRESS = 57
"""Public-law numbering begins with the 57th Congress; before it the prefix's
second number is a chapter (CLAUDE.md gotcha 8)."""


class _Origins(BaseSettings):
    """The public origins used in absolute URLs. `db.config` has the same two
    fields; `api/` may not import `db`, so they are read here as well."""

    site_origin: str = "https://statutes.linkedlegislation.org"
    uscode_origin: str = "https://uscode.linkedlegislation.org"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


origins = _Origins()

comps_router = APIRouter(prefix=API_PREFIX, tags=["compiled"], dependencies=[Depends(public_cache)])


# ------------------------------------------------------------------ shaping


def _iso_utc(when: datetime.datetime | None) -> str | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_of(when: datetime.datetime | None) -> datetime.date | None:
    return when.date() if when is not None else None


def _current_through(version: CompVersionRef | None) -> CurrentThroughOut:
    if version is None:
        return CurrentThroughOut()
    return CurrentThroughOut(pl=version.current_through_pl, enacted=version.current_through_date)


def _with_through(url: str, version: CompVersionRef) -> str:
    return f"{url}?through={version.current_through_pl}" if version.current_through_pl else url


def _versions_out(identifier: str, versions: tuple[CompVersionRef, ...]) -> list[CompVersionOut]:
    return [
        CompVersionOut(
            current_through=_current_through(v),
            fetched=_date_of(v.fetched_at),
            govinfo_last_modified=_iso_utc(v.govinfo_last_modified),
            is_current=v.is_current,
            url=_with_through(f"{origins.site_origin}{identifier}", v),
        )
        for v in versions
    ]


def _unit_ref_out(ref: UnitRef) -> UnitRefOut:
    return UnitRefOut(identifier=ref.identifier, level=ref.level, num=ref.num, heading=ref.heading, is_section=ref.is_section)


def _law_out(comp: CompRef) -> LawOut:
    identifier = comp.law_identifier
    if identifier is None and comp.law_congress is not None and comp.law_number is not None:
        if comp.law_congress >= FIRST_NUMBERED_CONGRESS:
            identifier = f"/us/pl/{comp.law_congress}/{comp.law_number}"
    return LawOut(congress=comp.law_congress, number=comp.law_number, identifier=identifier, loaded=comp.law_identifier is not None)


def comp_out(comp: CompRef) -> CompOut:
    return CompOut(
        file_id=comp.file_id,
        package_id=comp.package_id,
        identifier_prefix=comp.identifier_prefix,
        display_title=comp.display_title,
        title=comp.title,
        short_titles=list(comp.short_titles),
        law_identifier=comp.law_identifier,
        partial_of=comp.partial_of,
        current_through=_current_through(comp.current) if comp.current else None,
        govinfo_last_modified=_iso_utc(comp.current.govinfo_last_modified) if comp.current else None,
        url=f"{origins.site_origin}{comp.identifier_prefix}",
        govinfo_details=comp.govinfo_details,
    )


def compiled_alternatives(repository: Repository, result: CompUnitResult) -> list[dict]:
    """The other views of this unit: the enacted section with the same number
    under the law the prefix names (when that law is loaded), and the US Code
    section(s) the compilation's editorial note gives."""
    alternatives: list[dict] = []
    enacted = repository.enacted_counterpart(result.comp.identifier_prefix, result.section_num)
    if enacted is not None:
        alternatives.append(
            {
                "view": "enacted",
                "identifier": enacted.served_identifier,
                "url": f"{origins.site_origin}{enacted.served_identifier}",
            }
        )
    if result.usc_refs:
        alternatives.append(
            {
                "view": "codified",
                "identifiers": list(result.usc_refs),
                "url": f"{origins.uscode_origin}{result.usc_refs[0]}",
            }
        )
    return alternatives


def _note(result: CompUnitResult, alternatives: list[dict]) -> str:
    enacted_link = next((a["url"] for a in alternatives if a["view"] == "enacted"), None)
    codified = [f"{origins.uscode_origin}{ref}" for ref in result.usc_refs]
    body = compiled_note(result, enacted_link=enacted_link, codified=codified)
    prefix = served_note(result)
    return f"{prefix} {body}" if prefix else body


def _xml_url(identifier: str, through: str | None) -> str:
    url = f"{API_PREFIX}{identifier}?format=xml"
    return f"{url}&through={through}" if through else url


def _compilation_out(comp: CompRef) -> CompilationOut:
    return CompilationOut(
        file_id=comp.file_id,
        package_id=comp.package_id,
        display_title=comp.display_title,
        short_titles=list(comp.short_titles),
        identifier_prefix=comp.identifier_prefix,
        law_identifier=comp.law_identifier,
        partial_of=comp.partial_of,
        govinfo_details=comp.govinfo_details,
    )


def compiled_unit_out(repository: Repository, result: CompUnitResult, *, through: str | None) -> CompUnitOut:
    comp = result.comp
    version = result.version
    # A root gathered from per-title files has no one version history.
    detail = None if result.is_gathered else repository.get_comp(comp.file_id)
    versions = detail.versions if detail is not None else ()
    alternatives = compiled_alternatives(repository, result)
    provision = None
    if result.provision is not None:
        provision = ProvisionOut(
            identifier=result.provision.identifier,
            found=result.provision.found,
            text=result.provision.text,
            xml=result.provision.xml,
        )
    return CompUnitOut(
        identifier=result.requested_identifier,
        served_identifier=result.served_identifier,
        resolution=result.resolution,
        compilation=_compilation_out(comp),
        law=_law_out(comp),
        currency=CurrencyOut(
            current_through=_current_through(version),
            fetched=_date_of(version.fetched_at),
            govinfo_last_modified=_iso_utc(version.govinfo_last_modified),
        ),
        versions=_versions_out(result.requested_identifier, versions),
        alternatives=alternatives,
        note=_note(result, alternatives),
        provenance=ProvenanceOut(text=TEXT_PROVENANCE, identifiers=IDENTIFIER_PROVENANCE, sha256=result.content_hash),
        usc_refs=list(result.usc_refs),
        text=result.text,
        xml_url=_xml_url(result.requested_identifier, through if result.pinned else None) if serves_xml(result) else None,
        level=result.level,
        num=result.num,
        heading=result.heading,
        section_num=result.section_num,
        ancestors=[_unit_ref_out(a) for a in result.ancestors],
        children=[_unit_ref_out(c) for c in result.children],
        provision=provision,
        files=[_compilation_out(f) for f in result.files],
    )


def _etag(result: CompUnitResult, fmt: str) -> str:
    tag = result.content_hash
    if result.provision is not None and result.provision.found:
        tag = f"{tag}:{result.provision.identifier}"
    if fmt == "xml":
        tag = f"{tag};xml"
    return f'"{tag}"'


# ------------------------------------------------------------------- routes


def compiled_response(
    request: Request,
    repository: Repository,
    identifier: str,
    through: str | None,
    format: str | None,
) -> Response:
    """A compiled unit in the negotiated format with its caching headers; also
    what `view=compiled` on an enacted identifier serves (`api/routes.py`).
    Above a section the format is JSON whatever was asked, and the ETag is
    the JSON answer's."""
    fmt = negotiated_format(request, format, allowed=MACHINE_FORMATS)  # type: ignore[arg-type]
    result = repository.get_comp_unit(identifier, through=through, wanted=fmt)
    if result is None:
        if through is not None and repository.get_comp_unit(identifier) is not None:
            prefix = "/".join(identifier.split("/")[:5])
            raise HTTPException(
                status_code=404,
                detail=not_found(
                    identifier,
                    view="compiled",
                    searched=f"the loaded Statute Compilations; no stored version of {prefix} is current through {through}",
                ),
            )
        raise HTTPException(status_code=404, detail=not_found(identifier, view="compiled"))
    if not serves_xml(result):
        fmt = "json"
    etag = _etag(result, fmt)
    headers = {"ETag": etag, "Cache-Control": cache_control(result), "Vary": "Accept"}
    if if_none_match(request, etag):
        return Response(status_code=304, headers=headers)
    if fmt == "xml":
        xml = result.provision.xml if result.provision is not None and result.provision.found and result.provision.xml else result.xml
        return Response(content=xml, media_type="application/xml", headers=headers)
    body = compiled_unit_out(repository, result, through=through)
    return JSONResponse(content=body.model_dump(mode="json"), headers=headers)


@comps_router.get(
    "/us/sComp/{congress}/{number}",
    response_model=CompUnitOut,
    summary="A Statute Compilation",
    responses={304: {"description": "Not modified"}, 404: {"description": "No compilation has this prefix, or `through` names no stored version"}},
)
def compiled_root(
    request: Request,
    congress: int,
    number: int,
    repository: RepositoryDep,
    through: ThroughParam = None,
    format: FormatParam = None,
) -> Response:
    """The compilation itself: its table of contents, in JSON for every
    format. `through=118-67` selects a stored version. An act with one file
    per title and no whole-act file answers with its files gathered
    (`files`)."""
    return compiled_response(request, repository, f"/us/sComp/{congress}/{number}", through, format)


@comps_router.get(
    "/us/sComp/{congress}/{number}/{path:path}",
    response_model=CompUnitOut,
    summary="A unit of a Statute Compilation",
    responses={304: {"description": "Not modified"}, 404: {"description": "No compilation has this prefix, or `through` names no stored version"}},
)
def compiled_unit(
    request: Request,
    congress: int,
    number: int,
    path: str,
    repository: RepositoryDep,
    through: ThroughParam = None,
    format: FormatParam = None,
) -> Response:
    """A section or a level of a compilation in GPO's identifier form
    (`/tI/ch1./s1`, `/tI/ch1./s1/a`). Resolution: exact; the longest stored
    prefix with the rest cut from the section's XML; the section number under
    the compilation ignoring hierarchy. `note` says which rule answered.
    `format=xml` serves a section or a provision as USLM; a hierarchy level
    answers its JSON table of contents."""
    identifier = f"/us/sComp/{congress}/{number}/{path.strip('/')}" if path.strip("/") else f"/us/sComp/{congress}/{number}"
    return compiled_response(request, repository, identifier, through, format)


@comps_router.get("/comps", response_model=CompListOut, summary="Compilations for a law, or by title")
def list_comps(
    repository: RepositoryDep,
    law: Annotated[str | None, Query(description="An enacted law's identifier: `/us/pl/83/703`.", max_length=200)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200, description="A word of the title or a short title.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CompListOut:
    """`law=` lists the compilations whose prefix names a loaded law; `q=`
    searches titles and short titles. Without either, the first `limit`
    compilations by title."""
    comps = repository.list_comps(law_identifier=law, q=q, limit=limit)
    return CompListOut(comps=[comp_out(c) for c in comps])


def _toc(repository: Repository, comp: CompRef) -> list[UnitRefOut] | None:
    """The top-level units of this file's current version.

    Several files can share a prefix (one per title of the Social Security
    Act); `get_comp_unit` addresses the prefix, not a file, so the answer is
    checked against the file id and a per-title file is addressed through its
    title node."""
    if comp.current is None:
        return None
    root = repository.get_comp_unit(comp.identifier_prefix)
    if root is not None and not root.is_gathered and root.comp.file_id == comp.file_id:
        return [_unit_ref_out(c) for c in root.children]
    if comp.partial_of:
        title = repository.get_comp_unit(f"{comp.identifier_prefix}/t{comp.partial_of}")
        if title is not None and title.comp.file_id == comp.file_id and title.is_exact:
            return [UnitRefOut(identifier=title.served_identifier, level=title.level, num=title.num, heading=title.heading)]
    return None


@comps_router.get("/comps/{file_id}", response_model=CompDetailOut, summary="A compilation and its stored versions")
def get_comp(file_id: str, repository: RepositoryDep) -> CompDetailOut:
    """By GovInfo file id (`1630`) or package id (`COMPS-1630`). `versions` is
    the stored history, oldest first; GovInfo keeps only the current text, so
    it starts at the first ingest."""
    comp = repository.get_comp(file_id)
    if comp is None:
        raise HTTPException(status_code=404, detail=not_found(f"/api/v1/comps/{file_id}", view="compiled"))
    base = comp_out(comp)
    return CompDetailOut(
        **base.model_dump(),
        versions=_versions_out(comp.identifier_prefix, comp.versions),
        toc=_toc(repository, comp),
    )
