"""The classification tables mirror (design section 6, `classifications`).

Source: the US Code site's API, no key. `GET {origin}/api/v1/classifications/tables`
lists every table the site holds; `GET …/tables/{congress}/{session}/entries`
pages one table's rows (`sort=pl`, `limit`, `offset`). Only `kind == 'pl'`
tables are mirrored; ECCT tables are counted and skipped. The 104th Congress
is one whole-congress table with `session` `0`.

One `classification_files` row per (congress, session, kind), replaced
wholesale with its entries in one transaction per file (the US Code site's
ADR-0067, decision 3). A file whose listing entry (`fetched_at`, `row_count`,
`covered_laws_text`) equals what is stored is not paged unless `force`; a
paged file whose rows hash to the stored `content_hash` is `unchanged` and not
rewritten. Every run writes one `classification_source_checks` row, on success
and on failure.

`--from-dir PATH` reads saved JSON instead of the network: `PATH/tables.json`
for the listing and `PATH/entries-{congress}-{session}-{offset}.json` for each
page. A page missing from the directory ends that file's paging with a warning;
a file with no page at all is skipped.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from db.models import ClassificationCheck, ClassificationEntry, ClassificationFile
from ingest.hub import USER_AGENT
from storage.identifiers import section_number_of

DEFAULT_ORIGIN = "https://uscode.linkedlegislation.org"
USCODE_ORIGIN = os.environ.get("USCODE_ORIGIN", DEFAULT_ORIGIN).rstrip("/")
TABLES_PATH = "/api/v1/classifications/tables"
KIND = "pl"
PAGE_LIMIT = 500
SORT = "pl"
TIMEOUT = 30.0
MIN_INTERVAL = 0.1
"""Seconds between requests: at most 10 per second."""
MAX_429_RETRIES = 5
MAX_5XX_RETRIES = 3
DEFAULT_RETRY_AFTER = 2.0
MAX_RETRY_AFTER = 120.0
RETRY_STATUSES = frozenset({500, 502, 503, 504})

class ClassificationsError(Exception):
    """A request to the US Code site that did not succeed."""


# ------------------------------------------------------------------ reports


@dataclass(slots=True)
class ClassificationFileReport:
    congress: int
    session: int
    session_label: str | None
    action: str
    """`loaded` | `unchanged` | `skipped` (the listing matches what is stored,
    or no page was found)."""
    listing_row_count: int | None
    rows: int = 0
    """Rows the mirror holds for the file after the run."""
    pages: int = 0
    content_hash: str | None = None
    covered_laws_text: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClassificationLoadReport:
    checked_at: str
    source_url: str
    congress: int | None
    ok: bool = True
    error: str | None = None
    files_seen: int = 0
    """Listing entries of kind `pl` (after the `congress` limit)."""
    files_other_kind: int = 0
    """Listing entries of another kind (`ecct`), skipped."""
    files_loaded: int = 0
    files_unchanged: int = 0
    files_skipped: int = 0
    rows_loaded: int = 0
    upstream_checked_at: str | None = None
    upstream_covered_text: str | None = None
    files: list[ClassificationFileReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


# ------------------------------------------------------------------- client


class ClassificationsClient:
    """The US Code site's classification endpoints: sequential requests, at
    most ten per second, a 429 waited out per `Retry-After` and retried up to
    five times, a 5xx retried three times with backoff."""

    def __init__(
        self,
        *,
        origin: str = USCODE_ORIGIN,
        timeout: float = TIMEOUT,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        http: httpx.Client | None = None,
    ) -> None:
        self.origin = origin.rstrip("/")
        self._sleep = sleep
        self._clock = clock
        self._http = http or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self._last_request: float | None = None
        self.requests_made = 0

    def __enter__(self) -> "ClassificationsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    @property
    def tables_url(self) -> str:
        return f"{self.origin}{TABLES_PATH}"

    def tables(self) -> dict[str, Any]:
        return self._get_json(self.tables_url, None)

    def entries(self, congress: int, session: int, *, offset: int = 0, limit: int = PAGE_LIMIT) -> dict[str, Any]:
        url = f"{self.tables_url}/{congress}/{session}/entries"
        return self._get_json(url, {"sort": SORT, "limit": limit, "offset": offset})

    def _get_json(self, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        response = self._get(url, params)
        try:
            data = response.json()
        except ValueError as exc:
            raise ClassificationsError(f"{url}: response is not JSON") from exc
        if not isinstance(data, dict):
            raise ClassificationsError(f"{url}: unexpected JSON shape {type(data).__name__}")
        return data

    def _get(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        rate_limited = 0
        failed = 0
        while True:
            self._pace()
            try:
                self.requests_made += 1
                response = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                failed += 1
                if failed <= MAX_5XX_RETRIES:
                    self._sleep(_backoff(failed))
                    continue
                raise ClassificationsError(f"{type(exc).__name__} for {url}: {exc}") from None
            if response.status_code == 429:
                rate_limited += 1
                if rate_limited <= MAX_429_RETRIES:
                    self._sleep(_retry_after(response))
                    continue
                raise ClassificationsError(f"HTTP 429 for {url} after {rate_limited} attempts")
            if response.status_code in RETRY_STATUSES:
                failed += 1
                if failed <= MAX_5XX_RETRIES:
                    self._sleep(_backoff(failed))
                    continue
            if response.is_error:
                raise ClassificationsError(f"HTTP {response.status_code} for {url}")
            return response

    def _pace(self) -> None:
        now = self._clock()
        if self._last_request is not None:
            remaining = MIN_INTERVAL - (now - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_request = now


def _retry_after(response: httpx.Response) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return min(max(float(header), 0.0), MAX_RETRY_AFTER)
        except ValueError:
            pass
    return DEFAULT_RETRY_AFTER


def _backoff(attempt: int) -> float:
    return float(2 ** (attempt - 1))


# ------------------------------------------------------------------ sources


class PageSource(Protocol):
    """Where a run reads the listing and the pages: the API or a directory."""

    @property
    def source_url(self) -> str: ...

    def tables(self) -> dict[str, Any]: ...

    def entries(self, congress: int, session: int, *, offset: int) -> dict[str, Any] | None:
        """One page; None when the source has no page at this offset."""
        ...


class ApiSource:
    def __init__(self, client: ClassificationsClient, *, limit: int = PAGE_LIMIT) -> None:
        self._client = client
        self._limit = limit

    @property
    def source_url(self) -> str:
        return self._client.tables_url

    def tables(self) -> dict[str, Any]:
        return self._client.tables()

    def entries(self, congress: int, session: int, *, offset: int) -> dict[str, Any] | None:
        return self._client.entries(congress, session, offset=offset, limit=self._limit)


class DirectorySource:
    """`PATH/tables.json` and `PATH/entries-{congress}-{session}-{offset}.json`."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    @property
    def source_url(self) -> str:
        return str(self.directory)

    def tables(self) -> dict[str, Any]:
        return json.loads((self.directory / "tables.json").read_text(encoding="utf-8"))

    def entries(self, congress: int, session: int, *, offset: int) -> dict[str, Any] | None:
        path = self.directory / f"entries-{congress}-{session}-{offset}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ loading


def load_classifications(
    session: Session,
    source: PageSource,
    *,
    congress: int | None = None,
    force: bool = False,
) -> ClassificationLoadReport:
    """Mirror every `pl` table the listing names (one congress with
    `congress`). The listing or a page failing is a failed run: the check row
    is written and the exception re-raised."""
    started = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    report = ClassificationLoadReport(checked_at=now.isoformat(), source_url=source.source_url, congress=congress)
    try:
        listing = source.tables()
        upstream = listing.get("source") or {}
        report.upstream_checked_at = _str(upstream.get("last_checked_at"))
        report.upstream_covered_text = _str(upstream.get("latest_covered_text"))
        for entry in listing.get("files") or []:
            if entry.get("kind") != KIND:
                report.files_other_kind += 1
                continue
            file_congress, file_session = _int(entry.get("congress")), _int(entry.get("session"))
            if file_congress is None or file_session is None:
                report.warnings.append(f"listing entry without congress and session: {entry!r}")
                continue
            if congress is not None and file_congress != congress:
                continue
            report.files_seen += 1
            file_report = _load_file(session, source, entry, file_congress, file_session, now, force=force)
            report.files.append(file_report)
            report.warnings.extend(f"{file_congress}-{file_session}: {w}" for w in file_report.warnings)
            if file_report.action == "loaded":
                report.files_loaded += 1
                report.rows_loaded += file_report.rows
            elif file_report.action == "unchanged":
                report.files_unchanged += 1
            else:
                report.files_skipped += 1
    except Exception as exc:
        session.rollback()
        report.ok = False
        report.error = _error_text(exc)
        report.seconds = round(time.monotonic() - started, 1)
        _record_check(session, now, report)
        raise
    report.seconds = round(time.monotonic() - started, 1)
    _record_check(session, now, report)
    return report


def _load_file(
    session: Session,
    source: PageSource,
    entry: dict[str, Any],
    congress: int,
    file_session: int,
    now: datetime.datetime,
    *,
    force: bool,
) -> ClassificationFileReport:
    listing_rows = _int(entry.get("row_count"))
    report = ClassificationFileReport(
        congress=congress,
        session=file_session,
        session_label=_str(entry.get("session_label")),
        action="skipped",
        listing_row_count=listing_rows,
        covered_laws_text=_str(entry.get("covered_laws_text")),
    )
    stored = session.scalars(
        select(ClassificationFile).where(
            ClassificationFile.congress == congress,
            ClassificationFile.session == file_session,
            ClassificationFile.kind == KIND,
        )
    ).first()
    fetched_at = _datetime(_str(entry.get("fetched_at")))
    if stored is not None and not force and _listing_matches(stored, fetched_at, listing_rows, report.covered_laws_text):
        report.rows = stored.row_count
        report.content_hash = stored.content_hash
        return report

    items, pages, warnings = fetch_rows(source, congress, file_session)
    report.pages = pages
    report.warnings.extend(warnings)
    if pages == 0:
        report.rows = stored.row_count if stored is not None else 0
        report.content_hash = stored.content_hash if stored is not None else None
        return report

    digest = content_hash(items)
    report.content_hash = digest
    report.rows = len(items)
    if stored is not None and stored.content_hash == digest and stored.row_count == len(items):
        report.action = "unchanged"
        stored.upstream_fetched_at = fetched_at
        stored.covered_laws_text = report.covered_laws_text
        stored.covered_ranges = [str(r) for r in (entry.get("covered_ranges") or [])]
        session.commit()
        return report

    if stored is None:
        stored = ClassificationFile(congress=congress, session=file_session, kind=KIND, mirrored_at=now)
        session.add(stored)
    _apply_listing(stored, entry, fetched_at)
    stored.row_count = len(items)
    stored.content_hash = digest
    stored.mirrored_at = now
    session.flush()
    session.execute(delete(ClassificationEntry).where(ClassificationEntry.file_id == stored.id))
    rows = [_entry_row(stored.id, congress, file_session, item) for item in items]
    for start in range(0, len(rows), 2000):
        session.execute(insert(ClassificationEntry), rows[start : start + 2000])
    session.commit()
    report.action = "loaded"
    return report


def fetch_rows(source: PageSource, congress: int, file_session: int) -> tuple[list[dict], int, list[str]]:
    """Every item of the table, page by page; ends early, with a warning, when
    the source has no page at the next offset."""
    items: list[dict] = []
    pages = 0
    warnings: list[str] = []
    offset = 0
    while True:
        page = source.entries(congress, file_session, offset=offset)
        if page is None:
            if pages == 0:
                warnings.append("no page found; the file is not mirrored")
            else:
                warnings.append(f"page at offset {offset} not found; {len(items)} row(s) kept")
            break
        got = page.get("items") or []
        pages += 1
        items.extend(got)
        total = _int(page.get("total"))
        if total is None:
            total = offset + len(got)
        offset += len(got)
        if not got or offset >= total:
            if offset < total:
                warnings.append(f"page at offset {offset} was empty; {len(items)} of {total} row(s) kept")
            break
    return items, pages, warnings


def content_hash(items: list[dict]) -> str:
    """sha256 over the rows' `raw_line` values, joined by newlines."""
    text = "\n".join(_str(item.get("raw_line")) or "" for item in items)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _listing_matches(stored: ClassificationFile, fetched_at: datetime.datetime | None, row_count: int | None, covered: str | None) -> bool:
    return (
        _same_instant(stored.upstream_fetched_at, fetched_at)
        and stored.row_count == row_count
        and (stored.covered_laws_text or None) == (covered or None)
    )


def _same_instant(a: datetime.datetime | None, b: datetime.datetime | None) -> bool:
    if a is None or b is None:
        return a is b
    return _utc(a) == _utc(b)


def _utc(when: datetime.datetime) -> datetime.datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc)


def _apply_listing(stored: ClassificationFile, entry: dict[str, Any], fetched_at: datetime.datetime | None) -> None:
    stored.session_label = _str(entry.get("session_label"))
    stored.source_url = _str(entry.get("source_url"))
    stored.source_filename = _str(entry.get("source_filename"))
    stored.covered_laws_text = _str(entry.get("covered_laws_text"))
    stored.covered_ranges = [str(r) for r in (entry.get("covered_ranges") or [])]
    stored.first_law = _int(entry.get("first_law"))
    stored.last_law = _int(entry.get("last_law"))
    stored.prepared_date = _date(_str(entry.get("prepared_date")))
    stored.stat_volume = _int(entry.get("stat_volume"))
    stored.upstream_fetched_at = fetched_at


def _entry_row(file_id: int, congress: int, file_session: int, item: dict[str, Any]) -> dict[str, Any]:
    pl_section_raw = _str(item.get("pl_section_raw")) or ""
    return {
        "file_id": file_id,
        "congress": congress,
        "session": file_session,
        "row_seq": int(item.get("row_seq") or 0),
        "raw_line": _str(item.get("raw_line")),
        "title_raw": _str(item.get("title_raw")),
        "title_num": _str(item.get("title_num")),
        "is_appendix": bool(item.get("is_appendix")),
        "section_raw": _str(item.get("section_raw")),
        "section_norm": _str(item.get("section_norm")),
        "description_raw": _str(item.get("description_raw")),
        "is_note": bool(item.get("is_note")),
        "action": _str(item.get("action")),
        "transfer_counterpart": _str(item.get("transfer_counterpart")),
        "act_name": _str(item.get("act_name")),
        "usc_identifier": _str(item.get("usc_identifier")),
        "pl_congress": _int(item.get("pl_congress")),
        "pl_num": _int(item.get("pl_num")),
        "pl_label": _str(item.get("pl_label")),
        "pl_section_raw": pl_section_raw,
        "pl_section_num": section_number_of(pl_section_raw),
        "new_section_quote": _str(item.get("new_section_quote")),
        "stat_volume": _int(item.get("stat_volume")),
        "stat_pages": list(item.get("stat_pages") or []),
        "stat_page_labels": [str(p) for p in (item.get("stat_page_labels") or [])],
    }


def _record_check(session: Session, now: datetime.datetime, report: ClassificationLoadReport) -> None:
    session.add(
        ClassificationCheck(
            checked_at=now,
            ok=report.ok,
            source_url=report.source_url,
            congress=report.congress,
            files_seen=report.files_seen,
            files_loaded=report.files_loaded,
            files_unchanged=report.files_unchanged,
            rows_loaded=report.rows_loaded,
            upstream_checked_at=_datetime(report.upstream_checked_at),
            upstream_covered_text=report.upstream_covered_text,
            error=report.error,
        )
    )
    session.commit()


def _error_text(exc: BaseException) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _datetime(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return _utc(parsed)


# ------------------------------------------------------------- command line


def write_report(report: ClassificationLoadReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "classifications.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n")
    return target


def cmd_classifications(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    if args.from_dir:
        source: PageSource = DirectorySource(Path(args.from_dir))
        client = None
    else:
        client = ClassificationsClient()
        source = ApiSource(client)
    try:
        with SessionLocal() as session:
            try:
                report = load_classifications(session, source, congress=args.congress, force=args.force)
            except Exception as exc:
                print(f"classifications FAILED: {_error_text(exc)}", file=sys.stderr)
                return 1
    finally:
        if client is not None:
            client.close()
    print(
        f"classifications from {report.source_url}: {report.files_seen} pl file(s) seen, "
        f"{report.files_other_kind} other kind, {report.files_loaded} loaded, {report.files_unchanged} unchanged, "
        f"{report.files_skipped} skipped, {report.rows_loaded} rows, "
        f"upstream checked {report.upstream_checked_at} ({report.upstream_covered_text}), {report.seconds}s"
    )
    for line in report.files:
        print(
            f"  {line.congress}-{line.session}\t{line.action}\t{line.rows} rows"
            + (f" (listing says {line.listing_row_count})" if line.listing_row_count != line.rows else "")
            + f"\t{line.covered_laws_text}"
        )
    for warning in report.warnings:
        print(f"  warning: {warning}", file=sys.stderr)
    if args.report:
        target = write_report(report, Path(args.report))
        print(f"  report {target}")
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    return 0


def add_classifications_commands(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("classifications", help="mirror the classification tables from the US Code site")
    parser.add_argument("--congress", type=int, help="only this congress's tables")
    parser.add_argument("--from-dir", help="read tables.json and entries-*.json from this directory instead of the API")
    parser.add_argument("--force", action="store_true", help="page every file, whatever the listing says")
    parser.add_argument("--report", help="directory for classifications.json")
    parser.add_argument("--json", action="store_true", help="print the report")
    parser.set_defaults(func=cmd_classifications)
