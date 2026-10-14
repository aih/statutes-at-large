"""`plaw pending`: the public laws Congress.gov lists that are not loaded here.

A law is enacted days or weeks before GPO publishes its text in GovInfo's PLAW
collection, and until then `plaw poll` has nothing to load. This command asks
the Congress.gov API which bills became public laws in a congress
(`GET https://api.congress.gov/v3/law/{congress}/pub`, paged with `offset` and
`limit=250`) and writes a `pending_laws` row for each listed law that has no
`laws` row or alias at its `/us/pl/{c}/{n}` identifier. A congress's rows are
replaced on every run, so a law that has since been loaded drops out.
`api/cite.py` reads the rows to tell a reader that the law exists, why its text
is not here, and where Congress.gov has it (ADR-0031).

Each listed bill carries `type` (`HR`, `S`, `HJRES`, `SJRES`), `number`,
`title`, `latestAction.actionDate`, and `laws`, a list of `{number: "119-120",
type: "Public Law"}`. The bill's page is
`https://www.congress.gov/bill/119th-congress/house-bill/1234`.

The key is `GOVINFO_API_KEY`: GovInfo and Congress.gov both take api.data.gov
keys. It goes through `ingest.govinfo.GovInfoClient`, which keeps it out of
everything printed.

The default congresses are the current one and the one before it, so the last
laws of a congress that ended in January are still covered. `--from-file PATH`
reads one listing page from a JSON file in place of the network.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models import Law, LawAlias, PendingLaw

CONGRESS_API = "https://api.congress.gov/v3"
CONGRESS_GOV = "https://www.congress.gov"
PAGE_SIZE = 250
UTC = datetime.timezone.utc

BILL_TYPE_SLUGS = {
    "HR": "house-bill",
    "S": "senate-bill",
    "HJRES": "house-joint-resolution",
    "SJRES": "senate-joint-resolution",
    "HCONRES": "house-concurrent-resolution",
    "SCONRES": "senate-concurrent-resolution",
    "HRES": "house-resolution",
    "SRES": "senate-resolution",
}


def current_congress(today: datetime.date) -> int:
    """The congress sitting on `today`; a congress begins on January 3 of an
    odd year (the 119th on January 3, 2025)."""
    year = today.year
    if year % 2 == 1 and today < datetime.date(year, 1, 3):
        year -= 1
    return (year - 1789) // 2 + 1


def ordinal(n: int) -> str:
    """`119th`, `121st`, `112th`."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def bill_url(congress: int, bill_type: str, bill_number: str) -> str:
    slug = BILL_TYPE_SLUGS.get(bill_type.upper(), bill_type.lower())
    return f"{CONGRESS_GOV}/bill/{ordinal(congress)}-congress/{slug}/{bill_number}"


@dataclass(slots=True)
class ListedLaw:
    identifier: str
    congress: int
    number: int
    bill_type: str
    bill_number: str
    title: str | None
    action_date: datetime.date | None

    @property
    def url(self) -> str:
        return bill_url(self.congress, self.bill_type, self.bill_number)


def parse_law_number(text: str) -> tuple[int, int] | None:
    """`119-120` → (119, 120)."""
    congress, sep, number = str(text).strip().partition("-")
    if not sep or not congress.isdigit() or not number.isdigit():
        return None
    return int(congress), int(number)


def parse_listing(data: dict[str, Any], congress: int) -> list[ListedLaw]:
    """The public laws of one listing page. A bill that became more than one
    law (rare) yields each; a private law and a law of another congress are
    left out."""
    out: list[ListedLaw] = []
    for bill in data.get("bills") or []:
        bill_type = str(bill.get("type") or "").strip()
        bill_number = str(bill.get("number") or "").strip()
        if not bill_type or not bill_number:
            continue
        action = (bill.get("latestAction") or {}).get("actionDate")
        try:
            action_date = datetime.date.fromisoformat(action) if action else None
        except ValueError:
            action_date = None
        for law in bill.get("laws") or []:
            if "public" not in str(law.get("type") or "").lower():
                continue
            parsed = parse_law_number(law.get("number") or "")
            if parsed is None or parsed[0] != congress:
                continue
            out.append(
                ListedLaw(
                    identifier=f"/us/pl/{parsed[0]}/{parsed[1]}",
                    congress=parsed[0],
                    number=parsed[1],
                    bill_type=bill_type.upper(),
                    bill_number=bill_number,
                    title=bill.get("title"),
                    action_date=action_date,
                )
            )
    return out


def fetch_listing(client: Any, congress: int) -> Iterator[ListedLaw]:
    """Every page of `/law/{congress}/pub`, until a page comes back short."""
    offset = 0
    while True:
        data = client.get_json(
            f"{CONGRESS_API}/law/{congress}/pub",
            {"format": "json", "limit": PAGE_SIZE, "offset": offset},
        )
        bills = data.get("bills") or []
        yield from parse_listing(data, congress)
        if len(bills) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def loaded_identifiers(session: Session, identifiers: Iterable[str]) -> set[str]:
    wanted = list(identifiers)
    if not wanted:
        return set()
    found = set(session.scalars(select(Law.identifier).where(Law.identifier.in_(wanted))))
    found |= set(session.scalars(select(LawAlias.identifier).where(LawAlias.identifier.in_(wanted))))
    return found


@dataclass(slots=True)
class CongressReport:
    congress: int
    listed: int = 0
    loaded: int = 0
    pending: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PendingReport:
    checked_at: str
    congresses: list[CongressReport] = field(default_factory=list)


def record_pending(session: Session, congress: int, listed: list[ListedLaw], *, now: datetime.datetime) -> CongressReport:
    """Replace the congress's `pending_laws` rows with the listed laws not
    loaded. The caller commits."""
    report = CongressReport(congress=congress, listed=len(listed))
    loaded = loaded_identifiers(session, (law.identifier for law in listed))
    report.loaded = len({law.identifier for law in listed} & loaded)
    session.execute(delete(PendingLaw).where(PendingLaw.congress == congress))
    seen: set[str] = set()
    for law in sorted(listed, key=lambda law: law.number):
        if law.identifier in loaded or law.identifier in seen:
            continue
        seen.add(law.identifier)
        session.add(
            PendingLaw(
                identifier=law.identifier,
                congress=law.congress,
                number=law.number,
                bill_type=law.bill_type,
                bill_number=law.bill_number,
                title=law.title,
                action_date=law.action_date,
                congress_gov_url=law.url,
                checked_at=now,
            )
        )
        report.pending.append(law.identifier)
    session.flush()
    return report


def cmd_pending(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    now = datetime.datetime.now(UTC)
    if args.congress:
        congresses = sorted(set(args.congress))
    else:
        current = current_congress(now.date())
        congresses = [current - 1, current]
    report = PendingReport(checked_at=now.isoformat())
    client = None
    if not args.from_file:
        from ingest.govinfo import GovInfoClient

        client = GovInfoClient(base_url=CONGRESS_API)
    try:
        with SessionLocal() as session:
            for congress in congresses:
                if args.from_file:
                    data = json.loads(Path(args.from_file).read_text())
                    listed = parse_listing(data, congress)
                else:
                    listed = list(fetch_listing(client, congress))
                if not listed and args.from_file:
                    continue
                per = record_pending(session, congress, listed, now=now)
                session.commit()
                report.congresses.append(per)
                print(f"  {congress}: {per.listed} listed, {per.loaded} loaded, {len(per.pending)} pending {' '.join(per.pending)}".rstrip())
    except Exception as exc:
        from ingest.govinfo import strip_query

        print(f"plaw pending FAILED: {strip_query(str(exc))}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
    if args.report:
        target = Path(args.report) / "plaw-pending.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(report), indent=2) + "\n")
        print(f"  report {target}")
    return 0


def add_pending_command(inner: argparse._SubParsersAction) -> None:
    """Register `plaw pending` on the `plaw` subparsers."""
    parser = inner.add_parser("pending", help="record the public laws Congress.gov lists that are not loaded")
    parser.add_argument("--congress", type=int, action="append", help="only this congress (repeatable); default the current one and the one before")
    parser.add_argument("--from-file", help="read one Congress.gov listing page from a JSON file instead of the API")
    parser.add_argument("--report", help="directory for plaw-pending.json")
    parser.set_defaults(func=cmd_pending)
