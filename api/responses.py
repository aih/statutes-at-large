"""Hand-built responses for the routes that serve two representations from one
URL: an enacted unit (JSON or verbatim USLM) and a Statutes at Large page.

Built as `Response` objects rather than returned as models, because the
headers (`ETag`, `Cache-Control`, `Vary`, `X-Served-Identifier`) and the 304
belong to the representation.
"""

from __future__ import annotations

import hashlib
from xml.sax.saxutils import quoteattr

from fastapi import Request, Response

from api.alternatives import alternatives_for, codified_labels, compiled_link
from api.currency import Amended, amended_for_unit
from api.schemas import AmendedOut, NotFoundOut, StatPageOut, UnitOut
from params import (
    IMMUTABLE,
    REVALIDATE,
    amended_sentence,
    cache_control,
    enacted_note,
    if_none_match,
    not_found,
    served_note,
)
from storage import Repository, StatPageResult, UnitResult
from uslmtext import content_hash

XML_MEDIA_TYPE = "application/xml; charset=utf-8"


def unit_note(result: UnitResult, alternatives: list | None = None, amended: Amended | None = None) -> str:
    """The resolution sentence, when there is one, then the as-enacted note,
    which names the compiled and codified texts the alternatives found and
    says what `amended` decided (`unknown` when no decision is given)."""
    alternatives = alternatives or []
    latest = amended.latest if amended is not None else None
    enacted = enacted_note(
        result,
        compiled_link=compiled_link(alternatives),
        codified=codified_labels(alternatives),
        amended_sentence=amended_sentence(
            result,
            amended.status if amended is not None else "unknown",
            latest_label=latest.label if latest is not None else None,
            latest_date=latest.date if latest is not None else None,
        ),
    )
    served = served_note(result)
    return f"{served} {enacted}" if served else enacted


def unit_etag(result: UnitResult) -> str:
    """The content hash; a found provision adds the hash of its identifier so
    two provisions of one section do not share an ETag."""
    if result.provision is not None and result.provision.found:
        suffix = hashlib.sha256(result.provision.identifier.encode()).hexdigest()[:16]
        return f'"{result.content_hash}-{suffix}"'
    return f'"{result.content_hash}"'


def xml_url_for(request: Request) -> str:
    url = request.url.include_query_params(format="xml")
    return f"{url.path}?{url.query}"


def unit_response(request: Request, repository: Repository, result: UnitResult, wanted: str) -> Response:
    """JSON or XML for an enacted unit, with the caching headers; 304 when the
    caller already holds it."""
    etag = unit_etag(result)
    headers = {
        "ETag": etag,
        "Cache-Control": cache_control(result),
        "Vary": "Accept",
        "X-Served-Identifier": result.served_identifier,
    }
    if if_none_match(request, etag):
        return Response(status_code=304, headers=headers)

    if wanted == "xml":
        fragment = (
            result.provision.xml
            if result.provision is not None and result.provision.found and result.provision.xml
            else result.xml
        )
        return Response(content=fragment, media_type=XML_MEDIA_TYPE, headers=headers)

    amended = amended_for_unit(repository, result)
    alternatives = alternatives_for(repository, result, citing=amended.citing)
    out = UnitOut.of(
        result,
        note=unit_note(result, alternatives, amended),
        alternatives=alternatives,
        xml_url=xml_url_for(request),
        amended=AmendedOut.of(amended),
    )
    return Response(content=out.model_dump_json(), media_type="application/json", headers=headers)


def compiled_not_found(repository: Repository, path: str, enacted: UnitResult | None) -> Response:
    """The compiled view's 404: the detail names the collection searched, and
    the body carries the alternatives the enacted unit has."""
    out = NotFoundOut(
        detail=not_found(path, view="compiled"),
        alternatives=alternatives_for(repository, enacted) if enacted is not None else [],
    )
    return Response(
        status_code=404,
        content=out.model_dump_json(),
        media_type="application/json",
        headers={"Cache-Control": REVALIDATE},
    )


def stat_page_xml(page: StatPageResult) -> str:
    """The page as USLM: one `slice` per law, holding the law's markup between
    the page's marker and the next one (ADR-0020)."""
    parts = [
        f"<statPage identifier={quoteattr(page.identifier)} "
        f"volume={quoteattr(str(page.volume))} page={quoteattr(page.page)}>"
    ]
    for document in page.documents:
        to = f" to={quoteattr(document.to_identifier)}" if document.to_identifier else ""
        parts.append(
            f"<slice law={quoteattr(document.law.identifier)} from={quoteattr(page.identifier)}{to}>"
        )
        parts.append(document.xml or "")
        parts.append("</slice>")
    parts.append("</statPage>")
    return "".join(parts)


def stat_page_response(request: Request, page: StatPageResult, wanted: str = "json") -> Response:
    """A printed page never changes: immutable, with an ETag over the documents
    on it and the slice each one prints."""
    digest = hashlib.sha256(
        "\n".join(
            f"{d.law.identifier}\t{d.starts_here}\t{d.unit_identifier or ''}\t{content_hash(d.xml or '')}"
            for d in page.documents
        ).encode()
    ).hexdigest()
    etag = f'"{digest}"'
    headers = {"ETag": etag, "Cache-Control": IMMUTABLE, "Vary": "Accept"}
    if if_none_match(request, etag):
        return Response(status_code=304, headers=headers)
    if wanted == "xml":
        return Response(content=stat_page_xml(page), media_type=XML_MEDIA_TYPE, headers=headers)
    return Response(
        content=StatPageOut.of(page).model_dump_json(), media_type="application/json", headers=headers
    )
