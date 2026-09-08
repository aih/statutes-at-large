"""The composition root: the FastAPI half of the site.

Mounted here: the machine surface at `/api/v1` and the citation redirector at
`/us/…`. The reader at `/app` is stage 5 of the design and is not part of this
process. Every question about which text belongs to which identifier is
answered by the `Repository` behind `storage/`.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from api.comps import comps_router
from api.routes import api
from citation import router as citation_router
from storage import RepositoryUnavailableError

DESCRIPTION = """
Public laws from the Statutes at Large, at the section level, addressed by the
identifiers the US Code writes in its source credits, and the Statute
Compilations the House Office of the Legislative Counsel maintains.

* `/api/v1/us/pl/81/740/s3` — section 3 of Public Law 81-740 as enacted.
* `/api/v1/us/act/1950-08-30/ch823/s3` — the same section by its chapter form.
* `/api/v1/us/stat/64/564` — every law on a Statutes at Large page.
* `/api/v1/us/sComp/83/703/tI/ch1./s1` — the compiled text, current through the
  law the response names.

The bare citation URL (`/us/pl/81/740/s3`) is a **307 redirect** to whichever
surface the caller can read, so `curl` it with `-L` or address `/api/v1`.
"""

app = FastAPI(
    title="statutes-linkedlegislation",
    version="0.1.0",
    summary="Statutes at Large and Statute Compilations, by the identifiers the US Code cites.",
    description=DESCRIPTION,
)

app.include_router(api)
app.include_router(comps_router)
app.include_router(citation_router)


@app.get("/health", tags=["ops"], summary="Liveness check")
def health() -> dict[str, str]:
    """`{"status": "ok"}` if the process is up. Says nothing about the database;
    for that, ask `/api/v1/status`."""
    return {"status": "ok"}


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
