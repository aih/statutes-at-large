"""The HTTP-shaped helpers the API and the citation URL share.

`served_note`, `not_found`, and `cache_control` are the three sentences and the
one header every response owes the caller (the US Code site's `params.py`
conventions, ADR-0018 there). Nothing here touches a database session:
`storage.get_repository` is the dependency.
"""

from __future__ import annotations

import threading
import time
from typing import Annotated, Callable, Literal

from fastapi import Depends, HTTPException, Query, Request, Response

from storage import CompUnitResult, Repository, UnitResult, get_repository, long_date

Format = Literal["json", "xml", "html"]
View = Literal["enacted", "compiled"]

RepositoryDep = Annotated[Repository, Depends(get_repository)]


def normalize_identifier(path: str) -> str:
    """URL path → identifier. Both `/us/pl/81/443` and `us/pl/81/443`."""
    cleaned = path.strip().strip("/")
    return f"/{cleaned}" if cleaned else "/"


# ------------------------------------------------------------------ the notes
#
# Every answer says what it is and how current it is (design section 4). The
# sentences are built here so the API and, later, the reader say them in the
# same words.


def served_note(result: UnitResult | CompUnitResult) -> str | None:
    """Say when the answer is not literally what was asked for.

    Rule 2 (a stored prefix answered), rule 3 (the section was found by number
    under a different hierarchy), and rule 4 (a law addressed by its other
    identifier) each get a sentence. `None` for an exact answer.
    """
    requested = result.requested_identifier
    served = result.served_identifier
    if result.resolution == "exact":
        return None
    if result.resolution == "alias":
        return f"{requested} is served as {served}, the same law under its other identifier."
    if result.resolution == "section_number":
        return (
            f"No unit is stored at {requested}; the section numbered "
            f"{result.num} in this law is at {served} and is served here."
        )
    if result.resolution == "prefix":
        missing = ""
        if result.provision is not None and not result.provision.found:
            missing = f" {result.provision.identifier} is not in its text."
        return (
            f"Nothing is stored at {requested}; {served} is the longest stored "
            f"prefix and is served here.{missing}"
        )
    return None


def not_found(path: str, *, view: str = "enacted", searched: str | None = None) -> str:
    """404s say what was searched. `searched` names the collection or version."""
    where = searched or {"enacted": "the loaded Statutes at Large volumes", "compiled": "the loaded Statute Compilations"}.get(view, view)
    return f"nothing at {path} in {where}"


def enacted_note(result: UnitResult, *, compiled_link: str | None, codified: list[str], amended_sentence: str) -> str:
    """The as-enacted note (design section 4), one sentence per fact."""
    law = result.law
    date = long_date(law.enacted) if law.enacted else "an unrecorded date"
    citation = f" ({law.citation})" if law.citation else ""
    what = law.label if result.level == "law" else f"{result.unit_label} of {law.label}"
    first = f"This is {what} as enacted on {date}{citation}. It is not updated."
    checks: list[str] = []
    if compiled_link:
        checks.append(f"the compiled text at {compiled_link}")
    if codified:
        checks.append("the US Code section(s) classified from it at " + ", ".join(codified))
    checks.append(f"the classification tables at uscode.house.gov for laws after {date}")
    return f"{first} {amended_sentence} To check for later amendments: " + "; ".join(checks) + "."


def amended_unknown_sentence(result: UnitResult) -> str:
    """The `amended` sentence while no index of later amendments exists
    (`currency.amended.status = "unknown"`), worded for the level served."""
    noun = "law" if result.level == "law" else ("section" if result.level == "section" else result.level)
    return f"Whether this {noun} has been amended since is not recorded here."


def compiled_note(result: CompUnitResult, *, enacted_link: str | None, codified: list[str]) -> str:
    """The compiled note (design section 4)."""
    comp = result.comp
    version = result.version
    title = comp.short_title or comp.display_title or comp.identifier_prefix
    through = version.current_through_pl or "an unrecorded law"
    date = long_date(version.current_through_date) if version.current_through_date else "an unrecorded date"
    what = title if result.level == "compilation" else f"{result.unit_label} of {title}"
    sentences = [
        f"This is {what} as compiled by the House Office of the "
        f"Legislative Counsel, incorporating amendments through Public Law {through} ({date}).",
        "Compilations are not an official version; the official text is in the Statutes at "
        "Large and the United States Code (1 U.S.C. 112, 204).",
    ]
    check = f"Laws enacted after {date} are not reflected; check the classification tables for {title}"
    if codified:
        check += " and the US Code section(s) " + ", ".join(codified)
    sentences.append(check + ".")
    if enacted_link:
        sentences.append(f"The enacted text is at {enacted_link}.")
    return " ".join(sentences)


# -------------------------------------------------------------------- caching
#
# An enacted unit never changes, so it is cached for a year; a compiled unit is
# immutable only when the caller pinned a stored version with `through=` and
# got exactly that (design section 5). Everything else revalidates against the
# ETag, which is the content hash.

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "public, max-age=300"


def cache_control(result: UnitResult | CompUnitResult) -> str:
    if isinstance(result, UnitResult):
        return IMMUTABLE
    return IMMUTABLE if result.pinned and result.is_exact else REVALIDATE


def if_none_match(request: Request, etag: str) -> bool:
    """True when the client already holds this exact representation
    (comma lists, weak validators, and `*`, RFC 9110 §13.1.2)."""
    header = request.headers.get("if-none-match", "")
    if not header:
        return False
    if header.strip() == "*":
        return True
    wanted = etag.strip().removeprefix("W/").strip('"')
    return any(
        candidate.strip().removeprefix("W/").strip('"') == wanted
        for candidate in header.split(",")
    )


def public_cache(response: Response) -> None:
    """A dependency for routes whose answer is public but not pinned."""
    response.headers["Cache-Control"] = REVALIDATE


# -------------------------------------------------------------- rate limiting
#
# ADR-0029's shape: a token bucket per client address, 429 with `Retry-After`.
# `labels` is sized for a server (the US Code site calls it once per rendered
# page); `cite` and `cited-by` for a person. The state is per process.


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, tokens: float, updated: float) -> None:
        self.tokens = tokens
        self.updated = updated


class RateLimiter:
    SWEEP_INTERVAL = 600.0

    def __init__(self, *, name: str, capacity: int, per_second: float) -> None:
        self.name = name
        self.capacity = float(capacity)
        self.per_second = per_second
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._swept = time.monotonic()

    def check(self, key: str) -> float | None:
        """None if the request may proceed; otherwise seconds until it may."""
        now = time.monotonic()
        with self._lock:
            if now - self._swept > self.SWEEP_INTERVAL:
                self._sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(self.capacity, now)
                self._buckets[key] = bucket
            bucket.tokens = min(self.capacity, bucket.tokens + (now - bucket.updated) * self.per_second)
            bucket.updated = now
            if bucket.tokens < 1.0:
                return max(1.0, (1.0 - bucket.tokens) / self.per_second)
            bucket.tokens -= 1.0
            return None

    def _sweep(self, now: float) -> None:
        full_after = self.capacity / self.per_second
        self._buckets = {k: b for k, b in self._buckets.items() if now - b.updated < full_after}
        self._swept = now

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._swept = time.monotonic()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "-"


LIMITERS: dict[str, RateLimiter] = {}


def rate_limit(name: str, *, capacity: int, per_second: float) -> Callable[[Request], None]:
    limiter = RateLimiter(name=name, capacity=capacity, per_second=per_second)
    LIMITERS[name] = limiter

    def dependency(request: Request) -> None:
        retry_after = limiter.check(client_key(request))
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="too many requests; try again shortly",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    return dependency


# ---------------------------------------------------------------- negotiation

_ACCEPTED: dict[str, Format] = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/json": "json",
}

MACHINE_FORMATS: frozenset[Format] = frozenset({"json", "xml"})
ALL_FORMATS: frozenset[Format] = frozenset({"json", "xml", "html"})


def negotiated_format(request: Request, requested: Format | None, *, allowed: frozenset[Format] = ALL_FORMATS) -> Format:
    """`?format=` wins; otherwise `Accept:` with q-values, highest first; JSON
    when the client asks for nothing this surface serves."""
    if requested and requested in allowed:
        return requested
    best: tuple[float, Format] | None = None
    for part in request.headers.get("accept", "").split(","):
        media_type, _, parameters = part.strip().partition(";")
        candidate = _ACCEPTED.get(media_type.strip().lower())
        if candidate is None or candidate not in allowed:
            continue
        quality = 1.0
        for parameter in parameters.split(";"):
            key, _, value = parameter.partition("=")
            if key.strip() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0 and (best is None or quality > best[0]):
            best = (quality, candidate)
    return best[1] if best else "json"


FormatParam = Annotated[
    Format | None,
    Query(description="Response format. Defaults to content negotiation on Accept."),
]
ViewParam = Annotated[
    View | None,
    Query(description="`enacted` (default): the Statutes at Large text. `compiled`: the Statute Compilation, when one exists."),
]
ThroughParam = Annotated[
    str | None,
    Query(description="A compilation's stored version, by the public law it is current through: `118-67`.", examples=["118-67"]),
]
