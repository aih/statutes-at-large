"""`python -m ingest …` — the loaders' command line.

    python -m ingest fetch-statute 64 124            # from the Hub into data/statute/xmls
    python -m ingest statute data/statute/xmls/STATUTE-64.xml --report docs/verification
    python -m ingest statute --volumes 1-137         # fetch what is missing, then load
    python -m ingest comps ...                       # the COMPS poller (ingest/comps.py)
    python -m ingest citations --from-hub            # the citation index (ingest/citations.py)
    python -m ingest classifications                 # the classification tables mirror (ingest/classifications.py)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

DATA_DIR = Path("data/statute/xmls")


def _volumes(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return out


def cmd_fetch_statute(args: argparse.Namespace) -> int:
    from ingest.hub import fetch_volume

    for volume in _volumes(",".join(args.volumes)):
        path = fetch_volume(volume, Path(args.dir), force=args.force)
        print(f"{volume}\t{path}\t{path.stat().st_size} bytes")
    return 0


def cmd_statute(args: argparse.Namespace) -> int:
    from db.base import SessionLocal
    from ingest.hub import fetch_volume
    from ingest.load import load_volume, write_report

    paths = [Path(p) for p in args.paths]
    if args.volumes:
        for volume in _volumes(args.volumes):
            paths.append(fetch_volume(volume, Path(args.dir)))
    if not paths:
        print("nothing to load: give file paths or --volumes", file=sys.stderr)
        return 2
    failures = 0
    for path in paths:
        with SessionLocal() as session:
            try:
                report = load_volume(session, path)
            except Exception as exc:  # one bad volume must not stop the run
                session.rollback()
                failures += 1
                print(f"{path}: FAILED {exc!r}", file=sys.stderr)
                continue
        line = (
            f"{report.package}: {report.laws_loaded} laws {report.laws_by_kind}, "
            f"{report.units} units, {report.sections} sections, "
            f"{report.stat_pages} pages, {report.seconds}s"
        )
        print(line)
        if args.report:
            target = write_report(report, Path(args.report))
            print(f"  report {target}")
        if args.json:
            print(json.dumps(asdict(report), indent=2))
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch-statute", help="download volume USLM from the Hub")
    fetch.add_argument("volumes", nargs="+", help="`64`, `64 72`, or `1-137`")
    fetch.add_argument("--dir", default=str(DATA_DIR))
    fetch.add_argument("--force", action="store_true")
    fetch.set_defaults(func=cmd_fetch_statute)

    statute = sub.add_parser("statute", help="load STATUTE volume USLM")
    statute.add_argument("paths", nargs="*", help="volume XML files")
    statute.add_argument("--volumes", help="fetch (if needed) and load these volumes: `64,124` or `1-137`")
    statute.add_argument("--dir", default=str(DATA_DIR))
    statute.add_argument("--report", help="directory for the per-volume JSON report")
    statute.add_argument("--json", action="store_true", help="print the report")
    statute.set_defaults(func=cmd_statute)

    try:
        from ingest.comps import add_comps_commands
    except ImportError:  # the COMPS poller lands in stage 2
        add_comps_commands = None
    if add_comps_commands is not None:
        add_comps_commands(sub)

    from ingest.citations import add_citations_commands

    add_citations_commands(sub)

    from ingest.classifications import add_classifications_commands

    add_classifications_commands(sub)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
