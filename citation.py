"""The citation URL: `/us/pl/…`, `/us/pvtl/…`, `/us/act/…`, `/us/stat/…`,
`/us/sComp/…`, kept as a thin redirector (design section 5; the US Code site's
ADR-0010).

A caller that prefers HTML is sent to the reader at `/app`, everyone else to
`/api/v1`; `?format=` overrides the header. 307, `Vary: Accept`, and the query
string copied through verbatim.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from params import FormatParam, negotiated_format

READER = "/app"
API = "/api/v1"

router = APIRouter(include_in_schema=False)


def _redirect_to(prefix: str, request: Request) -> RedirectResponse:
    target = f"{prefix}{request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(target, status_code=307, headers={"Vary": "Accept"})


@router.api_route("/us/{kind:path}", methods=["GET", "HEAD"])
def citation(request: Request, kind: str, format: FormatParam = None):
    wanted = negotiated_format(request, format)
    return _redirect_to(READER if wanted == "html" else API, request)


@router.api_route("/", methods=["GET", "HEAD"])
def home(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{READER}/", status_code=307)
