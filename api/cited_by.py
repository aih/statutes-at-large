"""`GET /api/v1/cited-by`: the US Code sections that cite a law, a section of
it, or a Statutes at Large page (design section 5).

The `Repository` answers; this module validates the query, shapes the JSON,
writes the note, and sets the caching headers. The answer changes when the
citation index is rebuilt, so it revalidates against an ETag over the query
and the index revision.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from api.alternatives import USCODE_ORIGIN
from api.schemas import CitedByOut, ErrorOut
from params import (
    REVALIDATE,
    RepositoryDep,
    cited_by_note,
    if_none_match,
    normalize_identifier,
    not_found,
    public_cache,
    rate_limit,
)
from storage import CitedBy, law_label_of_identifier, parse_identifier, parse_stat_page
from storage.identifiers import LEVEL_PREFIXES

API_PREFIX = "/api/v1"
CONTEXTS = ("sourceCredit", "note", "text")

cited_by_router = APIRouter(prefix=API_PREFIX, tags=["citations"], dependencies=[Depends(public_cache)])

_limit_cited_by = rate_limit("cited-by", capacity=60, per_second=2.0)
"""A person's budget."""


# ------------------------------------------------------------------ wording


def unit_phrase(answer: CitedBy) -> str:
    """`section 814 of Public Law 104-333`, `title I of Public Law 81-910`,
    `Public Law 83-703`, `page 563 of volume 64 of the Statutes at Large`."""
    stat = parse_stat_page(answer.requested_identifier)
    if stat is not None:
        return f"page {stat.page} of volume {stat.volume} of the Statutes at Large"
    law = answer.law.label if answer.law is not None else law_label_of_identifier(answer.law_identifier)
    if answer.section_num is not None:
        below = "".join(f"({seg})" for seg in (answer.below or "").split("/") if seg)
        return f"section {answer.section_num}{below} of {law}"
    parsed = parse_identifier(answer.requested_identifier)
    if parsed is not None and parsed.segments:
        return f"{_path_label(parsed.segments)} of {law}"
    return law


def _path_label(segments: tuple[str, ...]) -> str:
    """`('dI', 'tVIII')` → `title VIII of division I`."""
    labels: list[str] = []
    for segment in segments:
        for prefix, level in LEVEL_PREFIXES:
            if segment.startswith(prefix) and len(segment) > len(prefix):
                labels.append(f"{level} {segment[len(prefix):]}")
                break
        else:
            labels.append(segment)
    return " of ".join(reversed(labels))


def _etag(identifier: str, contexts: tuple[str, ...], limit: int, offset: int, revision: str | None, answer: CitedBy) -> str:
    parts = [identifier, ",".join(sorted(contexts)), str(limit), str(offset), revision or "", str(answer.total)]
    parts.extend(s.identifier for s in answer.sections)
    return '"' + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest() + '"'


# -------------------------------------------------------------------- route


@cited_by_router.get(
    "/cited-by",
    response_model=CitedByOut,
    responses={
        304: {"description": "The caller's `If-None-Match` matched the ETag."},
        404: {"model": ErrorOut},
        422: {"model": ErrorOut},
        429: {"model": ErrorOut},
    },
    summary="US Code sections that cite a law, a section, or a Statutes at Large page",
    dependencies=[Depends(_limit_cited_by)],
)
def cited_by(
    request: Request,
    repository: RepositoryDep,
    identifier: Annotated[
        str,
        Query(
            description="An enacted identifier (`/us/pl/104/333/s814`, `/us/act/1954-08-30/ch1073`) or a page (`/us/stat/64/563`).",
            examples=["/us/pl/104/333/s814"],
        ),
    ],
    context: Annotated[
        list[str] | None,
        Query(description="Repeatable: `sourceCredit`, `note`, `text`. Default: all three."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    """The law is matched through every alias it answers to and a section by
    its number, whatever hierarchy the citing text wrote. `law` is null when
    the law is not loaded; the index answers alone. `sections` is one page of
    distinct citing sections in identifier order; `total` counts them all.
    404 when the index holds nothing for an identifier of a law that is not
    loaded; 200 with an empty `sections` when the law is loaded and nothing
    cites it."""
    path = normalize_identifier(identifier)
    contexts = tuple(dict.fromkeys(context or CONTEXTS))
    bad = [c for c in contexts if c not in CONTEXTS]
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown context {', '.join(bad)}; use sourceCredit, note, text")
    answer = repository.cited_by(path, contexts=list(contexts), limit=limit, offset=offset)
    if answer is None:
        raise HTTPException(status_code=422, detail=f"{path} is not an identifier the citation index answers for")
    if answer.total == 0 and answer.law is None:
        raise HTTPException(status_code=404, detail=not_found(path, searched="the citation index"))
    index = repository.citation_index_status()
    etag = _etag(path, contexts, limit, offset, index.dataset_revision, answer)
    headers = {"ETag": etag, "Cache-Control": REVALIDATE}
    if if_none_match(request, etag):
        return Response(status_code=304, headers=headers)
    out = CitedByOut.of(
        answer,
        identifier=path,
        limit=limit,
        offset=offset,
        index=index,
        section_url=lambda section: f"{USCODE_ORIGIN}{section}",
        note=cited_by_note(what=unit_phrase(answer), total=answer.total, release_labels=answer.release_labels),
    )
    return Response(content=out.model_dump_json(), media_type="application/json", headers=headers)
