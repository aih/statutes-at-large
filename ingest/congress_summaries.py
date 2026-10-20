"""`python -m ingest congress-summaries` — the stored Congress summaries
(ADR-0037).

    congress-summaries           compute and store them when the stored rows
                                 are not at the current `data_version` stamp
    congress-summaries --force   compute and store them whatever the stamp

The stamp is read before the counts, so a load that commits while they are
computed leaves the rows behind the stamp and the next run computes again.
"""

from __future__ import annotations

import argparse
import time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.models import CongressSummaryRow
from storage.postgres import PostgresRepository, summary_to_json


def add_congress_summaries_command(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "congress-summaries", help="store the per-Congress counts at the current data version (ADR-0037)"
    )
    parser.add_argument("--force", action="store_true", help="recompute even when the stored rows are current")
    parser.set_defaults(func=cmd_congress_summaries)


def refresh_congress_summaries(session: Session, *, force: bool = False) -> dict:
    """Store every Congress's summary under the current stamp; a no-op when
    the stored rows are already at it, unless `force`."""
    repository = PostgresRepository(session)
    stamp = repository.data_stamp()
    if stamp is None:
        raise RuntimeError("no data_version row; run the migrations")
    if not force and repository.stored_summaries(stamp) is not None:
        return {"version": stamp[0], "changed_at": stamp[1], "stored": False, "congresses": None}
    summaries = repository.compute_congress_summaries()
    session.execute(delete(CongressSummaryRow))
    session.add_all(
        CongressSummaryRow(congress=s.congress, version=stamp[0], changed_at=stamp[1], summary=summary_to_json(s))
        for s in summaries
    )
    session.commit()
    return {"version": stamp[0], "changed_at": stamp[1], "stored": True, "congresses": len(summaries)}


def cmd_congress_summaries(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    started = time.monotonic()
    with SessionLocal() as session:
        report = refresh_congress_summaries(session, force=args.force)
    elapsed = time.monotonic() - started
    if report["stored"]:
        print(f"congress-summaries: {report['congresses']} Congresses stored at version {report['version']} in {elapsed:.1f}s")
    else:
        print(f"congress-summaries: current at version {report['version']}; nothing stored")
    return 0
