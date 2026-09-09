"""`python -m ingest reindex-search` — the OpenSearch build (ADR-0023).

Three modes over `ingest/search_sync.py`, mutually exclusive:

    reindex-search                 rebuild(recreate=False): build beside the
                                    live alias and move it
    reindex-search --recreate      rebuild(recreate=True): drop every index
                                    named for the alias first
    reindex-search --if-changed    rebuild only when the live alias was built
                                    from a mapping this code no longer declares
    reindex-search --since DATE    resync_since(DATE): re-sync the laws loaded
                                    and the compilation versions fetched at or
                                    after that date, through the live alias

`DISABLE_SEARCH_SYNC=1` exits 0 with a message before a client is built, so
`make test` and a load never need a cluster. A cluster with no
`SEARCH_PASSWORD` set (`storage.search.SearchNotConfigured`) is a one-line
error and exit 1.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

from db.base import SessionLocal
from ingest import search_sync
from storage.search import SearchNotConfigured, get_search_client


def add_reindex_search_command(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "reindex-search", help="build or refresh the OpenSearch index (ADR-0023)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--if-changed", action="store_true",
        help="rebuild only when the live alias was built from an older mapping",
    )
    mode.add_argument(
        "--since",
        help="YYYY-MM-DD; re-sync laws loaded and compilation versions fetched at or after this date, through the live alias",
    )
    mode.add_argument(
        "--recreate", action="store_true",
        help="drop every index named for the alias first, then rebuild",
    )
    parser.set_defaults(func=cmd_reindex_search)


def _summary(report: dict) -> str:
    documents = report.get("documents") or {}
    counted = f"{documents.get('enacted', 0)} enacted, {documents.get('compiled', 0)} compiled"
    if "since" in report:
        return f"reindex-search: resynced since {report['since']}: {counted}"
    return f"reindex-search: {report['alias']} -> {report['index']} ({report['fingerprint']}): {counted}"


def cmd_reindex_search(args: argparse.Namespace) -> int:
    if os.environ.get("DISABLE_SEARCH_SYNC") == "1":
        print("DISABLE_SEARCH_SYNC=1: reindex-search is a no-op")
        return 0

    try:
        client = get_search_client()
    except SearchNotConfigured as exc:
        print(exc, file=sys.stderr)
        return 1

    with SessionLocal() as session:
        if args.since:
            since = datetime.date.fromisoformat(args.since)
            report = search_sync.resync_since(session, client, since)
        elif args.if_changed:
            if search_sync.alias_is_current(client):
                print(
                    f"the search index is current ({search_sync.mapping_fingerprint()}); "
                    "nothing rebuilt"
                )
                return 0
            report = search_sync.rebuild(session, client)
        else:
            report = search_sync.rebuild(session, client, recreate=args.recreate)

    print(_summary(report))
    return 0
