"""A small client for the GovInfo API (https://api.govinfo.gov/docs/).

Three calls: the collection walk (`collections/{collection}/{since}`, paged
with `offsetMark`), a package summary, and a package's USLM. Requests are
sequential; a 429 or a 5xx is retried once after `Retry-After`.

The key is `GOVINFO_API_KEY` in the environment and goes on the query string
as `api_key`. It is kept out of everything that is printed: the client's
`repr`, error messages (the query string is stripped), and httpx's request log
line (a filter on the `httpx` logger redacts it).
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

BASE_URL = "https://api.govinfo.gov"
USER_AGENT = "statutes-linkedlegislation/0.1 (+https://statutes.linkedlegislation.org; COMPS poller)"
ENV_VAR = "GOVINFO_API_KEY"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 120.0
DEFAULT_RETRY_AFTER = 2.0

_QUERY = re.compile(r"\?[^\s'\"<>]*?(?=[:;,.!)]*(?:[\s'\"<>]|$))")
_KEY_IN_TEXT = re.compile(r"(api_key=)[^&\s'\"<>]*")


class GovInfoError(Exception):
    """A request that did not succeed. The message carries no query string."""


class MissingApiKeyError(GovInfoError):
    pass


def strip_query(text: str) -> str:
    """Remove every `?…` query string from a message, so a URL in an error
    never carries the key."""
    return _QUERY.sub("", text)


def redact_key(text: str) -> str:
    return _KEY_IN_TEXT.sub(r"\1REDACTED", text)


class _RedactKey(logging.Filter):
    """httpx logs `HTTP Request: GET <url> "…"` at INFO with the full URL; the
    key is replaced before the record is formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(
                redact_key(str(a)) if isinstance(a, (httpx.URL, str)) and "api_key=" in str(a) else a
                for a in args
            )
        if isinstance(record.msg, str) and "api_key=" in record.msg:
            record.msg = redact_key(record.msg)
        return True


_FILTER = _RedactKey()
for _name in ("httpx", "httpcore"):
    _logger = logging.getLogger(_name)
    if not any(isinstance(f, _RedactKey) for f in _logger.filters):
        _logger.addFilter(_FILTER)


def api_key_from_env() -> str:
    key = os.environ.get(ENV_VAR, "").strip()
    if not key:
        raise MissingApiKeyError(
            f"{ENV_VAR} is not set. Get a key at https://api.govinfo.gov/docs/ and export it; "
            "it is read from the environment only."
        )
    return key


def _utc(when: datetime.datetime) -> datetime.datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc)


def format_since(when: datetime.datetime) -> str:
    """`2026-09-01T00:00:00Z`, the form the collection route takes in its path."""
    return _utc(when).strftime("%Y-%m-%dT%H:%M:%SZ")


class GovInfoClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
        http: httpx.Client | None = None,
    ) -> None:
        self._key = api_key.strip() if api_key else api_key_from_env()
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._http = http or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self.requests_made = 0

    def __repr__(self) -> str:
        return f"GovInfoClient(base_url={self.base_url!r}, api_key=<set>)"

    def __enter__(self) -> "GovInfoClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------- the calls

    def collection(
        self, collection: str, since: datetime.datetime, *, page_size: int = 100
    ) -> Iterator[dict[str, Any]]:
        """Every package of `collection` modified since `since`, oldest page
        first, following `nextPage` (`offsetMark`, never a numeric `offset`)."""
        url: str | None = f"{self.base_url}/collections/{collection}/{format_since(since)}"
        params: dict[str, Any] | None = {"offsetMark": "*", "pageSize": page_size}
        while url:
            data = self._get_json(url, params)
            packages = data.get("packages") or []
            yield from packages
            next_page = data.get("nextPage")
            if not packages or not next_page:
                return
            # httpx replaces a URL's query when `params` is given, so the
            # page's own query is carried as params and the key joins it.
            next_url = httpx.URL(str(next_page))
            params = dict(next_url.params)
            params.pop("api_key", None)
            url = str(next_url.copy_with(query=None))

    def summary(self, package_id: str) -> dict[str, Any]:
        return self._get_json(f"{self.base_url}/packages/{package_id}/summary", None)

    def uslm(self, package_id: str) -> str:
        response = self._get(f"{self.base_url}/packages/{package_id}/uslm", None)
        response.encoding = response.encoding or "utf-8"
        return response.text

    # --------------------------------------------------------------- plumbing

    def _get_json(self, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        response = self._get(url, params)
        try:
            data = response.json()
        except ValueError as exc:
            raise GovInfoError(f"{strip_query(url)}: response is not JSON") from exc
        if not isinstance(data, dict):
            raise GovInfoError(f"{strip_query(url)}: unexpected JSON shape {type(data).__name__}")
        return data

    def _get(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        query = dict(params or {})
        query["api_key"] = self._key
        attempts = 0
        while True:
            attempts += 1
            try:
                self.requests_made += 1
                response = self._http.get(url, params=query)
            except httpx.HTTPError as exc:
                if attempts < 2:
                    self._sleep(DEFAULT_RETRY_AFTER)
                    continue
                raise GovInfoError(f"{type(exc).__name__} for {strip_query(url)}: {strip_query(str(exc))}") from None
            if response.status_code in RETRY_STATUSES and attempts < 2:
                self._sleep(_retry_after(response))
                continue
            if response.is_error:
                raise GovInfoError(f"HTTP {response.status_code} for {strip_query(url)}")
            return response


def _retry_after(response: httpx.Response) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return min(max(float(header), 0.0), MAX_RETRY_AFTER)
        except ValueError:
            pass
    return DEFAULT_RETRY_AFTER
