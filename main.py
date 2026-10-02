"""The composition root: the FastAPI half of the site.

Mounted here: the machine surface at `/api/v1` and the citation redirector at
`/us/…`. The reader at `/app` is stage 5 of the design and is not part of this
process. Every question about which text belongs to which identifier is
answered by the `Repository` behind `storage/`.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.telemetry import TelemetryConfig

from api.cite import cite_router
from api.cited_by import cited_by_router
from api.comps import comps_router
from api.routes import api
from api.search import search_router
from citation import router as citation_router
from site_version import GIT_COMMIT, SITE_VERSION
from storage import RepositoryUnavailableError

DESCRIPTION = """
Public laws from the Statutes at Large, at the section level, addressed by the
identifiers the US Code writes in its source credits, and the Statute
Compilations the House Office of the Legislative Counsel maintains.

* `/api/v1/us/pl/81/740/s3` — section 3 of Public Law 81-740 as enacted.
* `/api/v1/us/act/1950-08-30/ch823/s3` — the same section by its chapter form.
* `/api/v1/us/stat/64/564` — every law on a Statutes at Large page, with the
  text the page prints.
* `/api/v1/us/sComp/83/703/tI/ch1./s1` — the compiled text, current through the
  law the response names.
* `/api/v1/cited-by?identifier=/us/pl/104/333/s814` — the US Code sections
  whose source credits, notes, or text cite the section.
* `/api/v1/cite?q=Pub. L. 81-740, § 3` — a written citation, resolved to its
  identifier and checked.
* `/api/v1/search?q=wild horses` — keyword search over the laws as enacted
  and as compiled.

The bare citation URL (`/us/pl/81/740/s3`) is a **307 redirect** to whichever
surface the caller can read, so `curl` it with `-L` or address `/api/v1`.
"""

STATIC = Path(__file__).resolve().parent / "static"
FAVICON = "/favicon.svg"


def _untraced(scope: MutableMapping[str, Any]) -> bool:
    """`/health` is polled every 10s by Docker and by the watchdog."""
    return scope["path"] == "/health"


# FastAPI's built-in OpenTelemetry (ADR-0029). It exports only when
# OTEL_EXPORTER_OTLP_ENDPOINT is set, which it is on the box alone; the rest of
# the export (service name, sampler, credentials) is OTEL_* in the environment.
TELEMETRY: TelemetryConfig = {"exclude": _untraced}

# FastAPI's own docs pages are turned off so the two below can name the site's
# favicon; the stock pages name fastapi.tiangolo.com's.
app = FastAPI(
    title="statutes-linkedlegislation",
    version=SITE_VERSION,
    summary="Statutes at Large and Statute Compilations, by the identifiers the US Code cites.",
    description=DESCRIPTION,
    docs_url=None,
    redoc_url=None,
    telemetry=TELEMETRY,
)

app.include_router(api)
app.include_router(comps_router)
app.include_router(cited_by_router)
app.include_router(cite_router)
app.include_router(search_router)
app.include_router(citation_router)


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} — Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_favicon_url=FAVICON,
    )


@app.get(app.swagger_ui_oauth2_redirect_url or "/docs/oauth2-redirect", include_in_schema=False)
def swagger_ui_redirect() -> HTMLResponse:
    """The path Swagger UI's configuration names; `docs_url=None` unmounts it."""
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
def redoc() -> HTMLResponse:
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} — ReDoc",
        redoc_favicon_url=FAVICON,
    )


@app.get(FAVICON, include_in_schema=False)
def favicon() -> FileResponse:
    """The tab mark for the reader and both docs pages, cached for a day."""
    return FileResponse(
        STATIC / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> Response:
    """A 301 to `/favicon.svg`."""
    return Response(status_code=301, headers={"Location": FAVICON})


@app.get("/health", tags=["ops"], summary="Liveness check")
def health() -> dict[str, str]:
    """`{"status": "ok", "version": "0.1.0", "commit": "<sha or unknown>"}` if
    the process is up. Says nothing about the database; for that, ask
    `/api/v1/status`."""
    return {"status": "ok", "version": SITE_VERSION, "commit": GIT_COMMIT}


@app.exception_handler(RepositoryUnavailableError)
def repository_unavailable(request: Request, exc: RepositoryUnavailableError) -> Response:
    return JSONResponse(
        status_code=503,
        content={"detail": "The site is busy. Please retry in a moment."},
        headers={"Retry-After": "5", "Cache-Control": "private, no-store"},
    )


@app.exception_handler(HTTPException)
def http_exception(request: Request, exc: HTTPException) -> Response:
    """Errors are JSON, because everything this process serves is."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
