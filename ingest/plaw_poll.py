"""The PLAW poller: what GovInfo bulk data holds that the database does not.

The listings. `GET https://www.govinfo.gov/bulkdata/json/PLAW` (with
`Accept: application/json`; without it the server answers an HTML error page)
lists one folder per congress that has USLM (113 onward) and a `resources`
folder, which is skipped. `…/json/PLAW/{c}/public` lists one entry per public
law (`PLAW-118publ22.xml`, with a `link`, a `size`, and a
`formattedLastModifiedTime` such as `02-Jan-2026 19:32`, read as UTC) plus the
per-congress zip `PLAW-{c}-public.zip`. Private laws are not in bulk data and
are not looked for.

A file is due when no `laws` row from collection `PLAW` with that package id
exists, when the listing's time is later than the row's `loaded_at`, or under
`--force`. `--since` drops listing entries older than the date; the default
`since` is the newest `newest_last_modified` any PLAW `source_checks` row
recorded, less a day of overlap, and with no check yet everything is due.
`--force` makes every entry the `since` filter keeps due. `--limit N` stops after
N files fetched.

The zip rule. A congress with no PLAW-derived law stored, or with more than
half of its listed files due, is loaded from its zip
(`ingest.plaw.fetch_congress_zip` into `data/plaw`, re-downloaded when the
listing's zip time is later than the file on disk, then
`ingest.plaw.load_congress`). Otherwise the due files are fetched one by one
from their `link` and loaded with `parse_plaw` and `load_plaw`, one commit per
law; a file that fails is rolled back and counted, and the run goes on. Under
`--limit` the zip is taken only when the remaining allowance covers the due
files. The report says which path each congress took.

The check row. One `source_checks` row with collection `PLAW` per run:
`newest_last_modified` and `newest_package` from the newest listing entry
seen, `packages_seen` the law files listed, `new_packages` the package ids
loaded new or in place of a volume-derived law (the stored list is capped at
200 entries; the report carries the whole list), `error` a summary of the
files that failed. `ok` is false only when the walk itself raised (a listing
could not be read); the row is written and the exception re-raised
(ADR-0007, decision 7).

`--from-dir PATH` reads `PATH/PLAW.json`, `PATH/PLAW-{c}-public.json`, and
`PATH/PLAW-{c}publ{n}.xml` in place of the network. The walk covers the
congresses of `PLAW.json` that have a per-congress listing in the directory;
a law file the directory lacks is a failure. There is no zip in a directory,
so every due file is read one by one.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Law, SourceCheck
from ingest.hub import USER_AGENT
from ingest.plaw import (
    BULK_JSON,
    COLLECTION,
    DATA_DIR,
    fetch_congress_zip,
    listing_url,
    load_congress,
    load_plaw,
    package_id,
    parse_package_id,
    parse_plaw,
    zip_path,
)

TOP_LISTING_URL = f"{BULK_JSON}/PLAW"
TIME_FORMAT = "%d-%b-%Y %H:%M"
"""`formattedLastModifiedTime`: `02-Jan-2026 19:32`, UTC."""
SINCE_OVERLAP = datetime.timedelta(days=1)
NEW_PACKAGES_CAP = 200
"""How many package ids the `source_checks` row keeps; the report keeps all."""
HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}
TIMEOUT = 120.0
UTC = datetime.timezone.utc


# ------------------------------------------------------------------ listings


@dataclass(slots=True)
class ListingEntry:
    """One file in a per-congress listing."""

    name: str
    link: str | None
    last_modified: datetime.datetime | None
    size: int | None = None
    package: str | None = None
    """`PLAW-118publ22` for a law file; None for the zip."""
    congress: int | None = None
    number: int | None = None

    @property
    def is_zip(self) -> bool:
        return self.name.lower().endswith(".zip")


@dataclass(slots=True)
class CongressListing:
    congress: int
    files: list[ListingEntry] = field(default_factory=list)
    """The public-law files, in law-number order."""
    zip: ListingEntry | None = None


def parse_time(text: str | None) -> datetime.datetime | None:
    """`02-Jan-2026 19:32` → an aware UTC datetime; None when blank or unreadable."""
    if not text or not text.strip():
        return None
    try:
        return datetime.datetime.strptime(text.strip(), TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_top_listing(data: dict) -> list[tuple[int, datetime.datetime | None]]:
    """The congress folders of `json/PLAW`, ascending, with their times. A
    folder whose name is not a number (`resources`) is skipped."""
    out: list[tuple[int, datetime.datetime | None]] = []
    for entry in data.get("files") or []:
        if not entry.get("folder"):
            continue
        name = str(entry.get("name") or "").strip()
        if not name.isdigit():
            continue
        out.append((int(name), parse_time(entry.get("formattedLastModifiedTime"))))
    return sorted(out)


def parse_congress_listing(congress: int, data: dict) -> CongressListing:
    """The files of `json/PLAW/{c}/public`: public-law files in law-number
    order, plus the zip. Folders, private-law files, and files of another
    congress are left out."""
    listing = CongressListing(congress=congress)
    for entry in data.get("files") or []:
        if entry.get("folder"):
            continue
        name = str(entry.get("name") or "").strip()
        size = entry.get("size")
        item = ListingEntry(
            name=name,
            link=(entry.get("link") or None),
            last_modified=parse_time(entry.get("formattedLastModifiedTime")),
            size=int(size) if isinstance(size, int) else None,
        )
        if item.is_zip:
            listing.zip = item
            continue
        parsed = parse_package_id(name)
        if parsed is None or parsed[1] != "pl" or parsed[0] != congress:
            continue
        item.congress, item.number = parsed[0], parsed[2]
        item.package = package_id(parsed[0], parsed[2])
        listing.files.append(item)
    listing.files.sort(key=lambda e: e.number or 0)
    return listing


# ------------------------------------------------------------------- sources


class BulkSource:
    """The listings and files over HTTP. Bulk data needs no key."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._own = client is None

    def __enter__(self) -> BulkSource:
        if self._client is None:
            self._client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._own and self._client is not None:
            self._client.close()
            self._client = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT)
        return self._client

    def congresses(self) -> list[tuple[int, datetime.datetime | None]]:
        response = self.client.get(TOP_LISTING_URL, headers=HEADERS)
        response.raise_for_status()
        return parse_top_listing(response.json())

    def listing(self, congress: int) -> CongressListing:
        response = self.client.get(listing_url(congress), headers=HEADERS)
        response.raise_for_status()
        return parse_congress_listing(congress, response.json())

    def file(self, entry: ListingEntry) -> str:
        if not entry.link:
            raise ValueError(f"{entry.name}: the listing carries no link")
        response = self.client.get(entry.link, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.text

    def zip(self, listing: CongressListing, directory: Path) -> Path | None:
        """The per-congress zip on disk, downloaded when missing or when the
        listing's zip is later than the file."""
        target = zip_path(listing.congress, directory)
        force = False
        if target.exists() and listing.zip is not None and listing.zip.last_modified is not None:
            on_disk = datetime.datetime.fromtimestamp(target.stat().st_mtime, tz=UTC)
            force = listing.zip.last_modified > on_disk
        return fetch_congress_zip(listing.congress, directory, force=force)


class DirectorySource:
    """The same listings and files read from a directory (`--from-dir`)."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def __enter__(self) -> DirectorySource:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def congresses(self) -> list[tuple[int, datetime.datetime | None]]:
        """The congresses of `PLAW.json` that have a `PLAW-{c}-public.json`
        beside it; without a `PLAW.json`, every congress that has one."""
        top = self.directory / "PLAW.json"
        present = {
            int(path.name[len("PLAW-"):-len("-public.json")])
            for path in self.directory.glob("PLAW-*-public.json")
            if path.name[len("PLAW-"):-len("-public.json")].isdigit()
        }
        if not top.exists():
            return [(congress, None) for congress in sorted(present)]
        data = json.loads(top.read_text(encoding="utf-8"))
        return [(congress, when) for congress, when in parse_top_listing(data) if congress in present]

    def listing(self, congress: int) -> CongressListing:
        data = json.loads((self.directory / f"PLAW-{congress}-public.json").read_text(encoding="utf-8"))
        return parse_congress_listing(congress, data)

    def file(self, entry: ListingEntry) -> str:
        path = self.directory / entry.name
        if not path.exists():
            raise FileNotFoundError(f"{path} is not in {self.directory}")
        return path.read_text(encoding="utf-8")

    def zip(self, listing: CongressListing, directory: Path) -> Path | None:
        return None


# ------------------------------------------------------------------- reports


@dataclass(slots=True)
class CongressPollReport:
    congress: int
    listed: int = 0
    """Public-law files in the listing."""
    due: int = 0
    fetched: int = 0
    """Files loaded from the zip, or fetched one by one."""
    via_zip: bool = False
    loaded: int = 0
    new: int = 0
    replaced_statute: int = 0
    replaced_plaw: int = 0
    failed: int = 0
    stored_before: int = 0
    """PLAW-derived laws of the congress before this run."""
    seconds: float = 0.0


@dataclass(slots=True)
class PlawPollReport:
    collection: str
    since: str | None
    checked_at: str
    congresses: list[CongressPollReport] = field(default_factory=list)
    listed: int = 0
    due: int = 0
    fetched: int = 0
    loaded: int = 0
    new: int = 0
    replaced_statute: int = 0
    replaced_plaw: int = 0
    failed: int = 0
    newest_last_modified: str | None = None
    newest_package: str | None = None
    new_packages: list[str] = field(default_factory=list)
    """Every package loaded new or in place of a volume-derived law; the
    check row stores the first `NEW_PACKAGES_CAP`."""
    failures: list[dict] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    seconds: float = 0.0


# ------------------------------------------------------------------- polling


def poll(
    session: Session,
    source: BulkSource | DirectorySource,
    *,
    congresses: list[int] | None = None,
    since: datetime.datetime | None = None,
    limit: int | None = None,
    force: bool = False,
    directory: Path = DATA_DIR,
) -> PlawPollReport:
    """Walk the listings and load what is due. A `source_checks` row is
    written whether the walk succeeded or not."""
    started = time.monotonic()
    now = datetime.datetime.now(UTC)
    if since is None:
        since = default_since(session)
    report = PlawPollReport(
        collection=COLLECTION, since=since.isoformat() if since else None, checked_at=now.isoformat()
    )
    newest: datetime.datetime | None = None
    try:
        if congresses:
            walk = sorted(set(congresses))
        else:
            walk = [congress for congress, _ in source.congresses()]
        for congress in walk:
            if limit is not None and report.fetched >= limit:
                break
            listing = source.listing(congress)
            per = CongressPollReport(congress=congress)
            report.congresses.append(per)
            per.stored_before = len(_stored_packages(session, congress))
            for entry in listing.files:
                if entry.last_modified is not None and (newest is None or entry.last_modified > newest):
                    newest = entry.last_modified
                    report.newest_package = entry.package
            per.listed = len(listing.files)
            due = [
                entry for entry in listing.files
                if (since is None or entry.last_modified is None or entry.last_modified >= since)
                and (force or _is_due(session, entry))
            ]
            per.due = len(due)
            remaining = None if limit is None else max(limit - report.fetched, 0)
            if due and _take_zip(per, remaining):
                zip_file = source.zip(listing, directory)
            else:
                zip_file = None
            congress_started = time.monotonic()
            if zip_file is not None:
                _load_zip(session, congress, zip_file, per, report)
            else:
                _load_files(session, source, due, per, report, now, remaining)
            per.seconds = round(time.monotonic() - congress_started, 1)
            _add_totals(report, per)
    except Exception as exc:
        session.rollback()
        report.ok = False
        report.error = _error_text(exc)
        report.newest_last_modified = newest.isoformat() if newest else None
        report.seconds = round(time.monotonic() - started, 1)
        _record_check(session, now, report, newest)
        raise
    report.newest_last_modified = newest.isoformat() if newest else None
    if report.failures:
        report.error = f"{report.failed} file(s) failed: " + "; ".join(
            f"{f['package']}: {f['error']}" for f in report.failures[:10]
        )
    report.seconds = round(time.monotonic() - started, 1)
    _record_check(session, now, report, newest)
    return report


def _take_zip(per: CongressPollReport, remaining: int | None) -> bool:
    """The zip rule: nothing PLAW-derived stored, or more than half the listed
    files due; under a limit, only when the allowance covers the due files."""
    if remaining is not None and remaining < per.due:
        return False
    return per.stored_before == 0 or per.due * 2 > per.listed


def _load_zip(
    session: Session,
    congress: int,
    zip_file: Path,
    per: CongressPollReport,
    report: PlawPollReport,
) -> None:
    before = _stored_packages(session, congress)
    loaded = load_congress(session, congress, zip_file=zip_file, record_check=False)
    per.via_zip = True
    per.fetched = loaded.files
    per.loaded = loaded.laws_loaded
    per.new = loaded.laws_new
    per.replaced_statute = loaded.laws_replaced_statute
    per.replaced_plaw = loaded.laws_replaced_plaw
    per.failed = loaded.laws_failed
    for failure in loaded.failures:
        parsed = parse_package_id(failure["file"])
        package = package_id(parsed[0], parsed[2], parsed[1]) if parsed else None
        report.failures.append({"congress": congress, "package": package, "file": failure["file"], "error": failure["error"]})
    after = _stored_packages(session, congress)
    report.new_packages.extend(sorted(after - before, key=_package_order))


def _load_files(
    session: Session,
    source: BulkSource | DirectorySource,
    due: list[ListingEntry],
    per: CongressPollReport,
    report: PlawPollReport,
    now: datetime.datetime,
    remaining: int | None,
) -> None:
    for entry in due:
        if remaining is not None and per.fetched >= remaining:
            break
        per.fetched += 1
        try:
            text = source.file(entry)
            record = parse_plaw(text, package=entry.package)
            law = load_plaw(session, record, now=now)
            session.commit()
        except Exception as exc:  # one bad file must not end the run
            session.rollback()
            per.failed += 1
            report.failures.append({"congress": per.congress, "package": entry.package, "file": entry.name, "error": _error_text(exc)})
            continue
        per.loaded += 1
        if law.action == "new":
            per.new += 1
            report.new_packages.append(law.package)
        elif law.action == "replaced_statute":
            per.replaced_statute += 1
            report.new_packages.append(law.package)
        else:
            per.replaced_plaw += 1


def _add_totals(report: PlawPollReport, per: CongressPollReport) -> None:
    report.listed += per.listed
    report.due += per.due
    report.fetched += per.fetched
    report.loaded += per.loaded
    report.new += per.new
    report.replaced_statute += per.replaced_statute
    report.replaced_plaw += per.replaced_plaw
    report.failed += per.failed


def _stored_packages(session: Session, congress: int) -> set[str]:
    """Package ids of the PLAW-derived laws of a congress."""
    rows = session.scalars(
        select(Law.source_package).where(Law.source_collection == COLLECTION, Law.congress == congress)
    ).all()
    return set(rows)


def _is_due(session: Session, entry: ListingEntry) -> bool:
    """No PLAW-derived row for the package, or the listing is later than the
    row's `loaded_at`."""
    loaded_at = session.scalar(
        select(Law.loaded_at)
        .where(Law.source_collection == COLLECTION, Law.source_package == entry.package)
        .order_by(Law.loaded_at.desc())
        .limit(1)
    )
    if loaded_at is None:
        return True
    if entry.last_modified is None:
        return False
    if loaded_at.tzinfo is None:
        loaded_at = loaded_at.replace(tzinfo=UTC)
    return entry.last_modified > loaded_at


def default_since(session: Session) -> datetime.datetime | None:
    """The newest `newest_last_modified` any PLAW check recorded, less a day of
    overlap; None (everything is due) before the first check."""
    newest = session.scalar(
        select(SourceCheck.newest_last_modified)
        .where(SourceCheck.collection == COLLECTION, SourceCheck.newest_last_modified.is_not(None))
        .order_by(SourceCheck.newest_last_modified.desc())
        .limit(1)
    )
    if newest is None:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    return newest - SINCE_OVERLAP


def _record_check(session: Session, now: datetime.datetime, report: PlawPollReport, newest: datetime.datetime | None) -> None:
    session.add(
        SourceCheck(
            collection=COLLECTION,
            checked_at=now,
            ok=report.ok,
            newest_last_modified=newest,
            newest_package=report.newest_package,
            packages_seen=report.listed,
            new_packages=list(report.new_packages[:NEW_PACKAGES_CAP]),
            error=report.error,
        )
    )
    session.commit()


def _error_text(exc: BaseException) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _package_order(package: str) -> tuple[int, int, int]:
    parsed = parse_package_id(package)
    if parsed is None:
        return (0, 0, 0)
    return parsed[0], 0 if parsed[1] == "pl" else 1, parsed[2]


def write_report(report: PlawPollReport, directory: Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "plaw-poll.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n")
    return target


# --------------------------------------------------------------- command line


def print_report(report: PlawPollReport, out=None) -> None:
    out = out or sys.stdout
    for per in report.congresses:
        path = "zip" if per.via_zip else "files"
        print(
            f"PLAW {per.congress}: {per.listed} listed, {per.due} due, {per.fetched} fetched via {path}, "
            f"{per.loaded} loaded ({per.new} new, {per.replaced_statute} replaced volume-derived, "
            f"{per.replaced_plaw} re-loaded), {per.failed} failed, {per.seconds}s",
            file=out,
        )
    print(
        f"PLAW since {report.since}: {len(report.congresses)} congresses, {report.listed} listed, "
        f"{report.due} due, {report.fetched} fetched, {report.loaded} loaded, {report.new} new, "
        f"{report.replaced_statute} replaced volume-derived, {report.replaced_plaw} re-loaded, "
        f"{report.failed} failed, newest {report.newest_last_modified} ({report.newest_package}), "
        f"{report.seconds}s",
        file=out,
    )
    for failure in report.failures[:10]:
        print(f"  failed {failure['file']}: {failure['error']}", file=sys.stderr)


def cmd_poll(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    since = None
    if args.since:
        since = datetime.datetime.fromisoformat(args.since)
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
    source = DirectorySource(args.from_dir) if args.from_dir else BulkSource()
    with source, SessionLocal() as session:
        try:
            report = poll(
                session, source,
                congresses=args.congress or None,
                since=since,
                limit=args.limit,
                force=args.force,
                directory=Path(args.dir),
            )
        except Exception as exc:
            print(f"PLAW poll FAILED: {_error_text(exc)}", file=sys.stderr)
            return 1
    print_report(report)
    if args.report:
        target = write_report(report, Path(args.report))
        print(f"  report {target}")
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    return 1 if report.failed and not report.loaded else 0


def add_poll_command(inner: argparse._SubParsersAction) -> None:
    """Register `plaw poll` on the `plaw` subparsers (`ingest.plaw.add_plaw_commands`)."""
    parser = inner.add_parser("poll", help="walk the bulk-data listings and load the public laws that are new or changed")
    parser.add_argument("--congress", type=int, action="append", help="only this congress (repeatable)")
    parser.add_argument("--since", help="YYYY-MM-DD; default: the newest listing time seen, less a day")
    parser.add_argument("--force", action="store_true", help="fetch files already current")
    parser.add_argument("--limit", type=int, help="stop after this many files fetched")
    parser.add_argument("--from-dir", help="read the listings and files from a directory instead of GovInfo")
    parser.add_argument("--dir", default=str(DATA_DIR), help="where the per-congress zips are kept")
    parser.add_argument("--report", help="directory for plaw-poll.json")
    parser.add_argument("--json", action="store_true", help="print the report")
    parser.set_defaults(func=cmd_poll)
