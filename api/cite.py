"""`GET /api/v1/cite?q=`: a citation in written form, resolved to the
identifier it names and whether that is loaded (design section 5).

The parse is `citeparse.parse_citation`, which is pure. Existence is answered
with what the `Repository` already has: `labels` for a law, an act, a section
or a provision (the same resolution rules a unit request follows, so an alias
and a section number under another hierarchy both answer), `stat_page` for a
Statutes at Large page, `get_comp_unit` for a compilation. A US Code citation
is handed to the US Code site's origin and not checked.

Three answers, the US Code site's ADR-0023 shape: a 422 for text that is not
a citation, `exists: false` for a citation naming nothing loaded, and
`exists: true` with the served identifier and the citation URL.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from api.comps import origins
from api.schemas import CiteOut, ErrorOut
from citeparse import ParsedCitation, parse_citation
from params import (
    REVALIDATE,
    RepositoryDep,
    cite_chapter_not_on_page,
    cite_not_a_citation,
    cite_note,
    if_none_match,
    public_cache,
    rate_limit,
)
from storage import Repository

API_PREFIX = "/api/v1"

cite_router = APIRouter(prefix=API_PREFIX, tags=["citations"], dependencies=[Depends(public_cache)])

_limit_cite = rate_limit("cite", capacity=60, per_second=2.0)
"""A person's budget: the reader's `/app/goto` calls this once per typed citation."""


def _url(identifier: str) -> str:
    return f"{origins.site_origin}{identifier}"


def _resolve(repository: Repository, parsed: ParsedCitation, query: str) -> CiteOut:
    if parsed.kind == "usc":
        url = f"{origins.uscode_origin}{parsed.identifier}"
        return CiteOut.of(
            parsed,
            query,
            exists=None,
            url=url,
            note=cite_note(label=parsed.label, identifier=parsed.identifier, kind="usc", exists=None, url=url),
        )
    if parsed.kind == "stat":
        return _resolve_page(repository, parsed, query)
    if parsed.kind == "sComp":
        return _resolve_compiled(repository, parsed, query)
    return _resolve_unit(repository, parsed, query, parsed.identifier, parsed.kind, parsed.label, parsed.section_identifier)


def _resolve_unit(
    repository: Repository,
    parsed: ParsedCitation,
    query: str,
    identifier: str,
    kind: str,
    label: str,
    section_identifier: str | None = None,
) -> CiteOut:
    found = repository.labels([identifier]).get(identifier)
    if found is None:
        return CiteOut.of(
            parsed, query, identifier=identifier, section_identifier=section_identifier, kind=kind, label=label,
            exists=False, note=cite_note(label=label, identifier=identifier, kind=kind, exists=False),
        )
    message = None
    if found.resolution == "prefix" and parsed.subdivisions:
        message = f"{identifier} is not in the text of {found.served_identifier}."
    return CiteOut.of(
        parsed,
        query,
        identifier=identifier,
        section_identifier=section_identifier,
        kind=found.law.kind,
        label=label,
        exists=True,
        served_identifier=found.served_identifier,
        resolution=found.resolution,
        level=found.level,
        num=found.num,
        heading=found.heading,
        law_identifier=found.law.identifier,
        law_label=found.law.label,
        url=_url(identifier),
        note=cite_note(
            label=label, identifier=identifier, kind=found.law.kind, exists=True,
            served_identifier=found.served_identifier, resolution=found.resolution, num=found.num,
        ),
        message=message,
    )


def _resolve_page(repository: Repository, parsed: ParsedCitation, query: str) -> CiteOut:
    assert parsed.volume is not None and parsed.page is not None
    page = repository.stat_page(parsed.volume, parsed.page)
    if page is None:
        return CiteOut.of(
            parsed, query, exists=False,
            note=cite_note(label=parsed.label, identifier=parsed.identifier, kind="stat", exists=False),
        )
    message = None
    if parsed.chapter is not None:
        # `ch. 823, 64 Stat. 563`: the law on the page with that chapter, and
        # its section when the citation gave one.
        for document in page.documents:
            if document.law.chapter == parsed.chapter:
                identifier = section = document.law.identifier
                label = f"{document.law.label}"
                if parsed.section_num is not None:
                    section = f"{identifier}/s{parsed.section_num}"
                    identifier = f"{section}{parsed.below_section}"
                    label += f", section {parsed.section_num}" + "".join(f"({s})" for s in parsed.subdivisions)
                return _resolve_unit(repository, parsed, query, identifier, document.law.kind, label, section)
        message = cite_chapter_not_on_page(chapter=parsed.chapter, page_identifier=page.identifier)
    return CiteOut.of(
        parsed,
        query,
        exists=True,
        served_identifier=page.identifier,
        resolution="exact",
        level="page",
        num=page.page,
        url=_url(page.identifier),
        note=cite_note(label=parsed.label, identifier=page.identifier, kind="stat", exists=True),
        message=message,
    )


def _resolve_compiled(repository: Repository, parsed: ParsedCitation, query: str) -> CiteOut:
    result = repository.get_comp_unit(parsed.identifier)
    if result is None:
        return CiteOut.of(
            parsed, query, exists=False,
            note=cite_note(label=parsed.label, identifier=parsed.identifier, kind="sComp", exists=False),
        )
    return CiteOut.of(
        parsed,
        query,
        exists=True,
        served_identifier=result.served_identifier,
        resolution=result.resolution,
        level=result.level,
        num=result.num,
        heading=result.heading,
        law_identifier=result.comp.law_identifier,
        law_label=result.comp.short_title or result.comp.display_title,
        url=_url(parsed.identifier),
        note=cite_note(
            label=parsed.label, identifier=parsed.identifier, kind="sComp", exists=True,
            served_identifier=result.served_identifier, resolution=result.resolution, num=result.num,
        ),
    )


@cite_router.get(
    "/cite",
    response_model=CiteOut,
    responses={
        304: {"description": "The caller's `If-None-Match` matched the ETag."},
        422: {"model": ErrorOut},
        429: {"model": ErrorOut},
    },
    summary="A written citation, resolved to an identifier and checked",
    dependencies=[Depends(_limit_cite)],
)
def cite(
    request: Request,
    repository: RepositoryDep,
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=300,
            description="A citation in written form: a public or private law with an optional section, "
            "an act by date and chapter, a Statutes at Large page, a chapter with its page, an identifier, "
            "or a US Code citation.",
            examples=["Pub. L. 104-333, § 814", "110 Stat. 4196", "Act of Aug. 25, 1916, ch. 408", "43 U.S.C. 1701"],
        ),
    ],
) -> Response:
    """`Pub. L. 104-333, § 814` → `/us/pl/104/333/s814`, and whether it is
    loaded. A law from 1901 to 1957 cited by date and chapter resolves through
    its `/us/act/` alias; a Stat. page resolves to `/us/stat/{vol}/{page}`; a
    chapter cited with its page resolves to the law on that page with that
    chapter. A US Code citation answers `kind: "usc"` with the US Code site's
    URL and `exists: null`. Text that is not a citation is a 422 whose detail
    names the accepted forms; a citation naming nothing loaded is `exists:
    false`."""
    parsed = parse_citation(q)
    if parsed is None:
        raise HTTPException(status_code=422, detail=cite_not_a_citation(q))
    out = _resolve(repository, parsed, q)
    body = out.model_dump_json()
    etag = '"' + hashlib.sha256(body.encode("utf-8")).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": REVALIDATE}
    if if_none_match(request, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
