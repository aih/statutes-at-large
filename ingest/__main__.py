"""`python -m ingest …` — the loaders' command line.

    python -m ingest fetch-statute 64 124            # from the Hub into data/statute/xmls
    python -m ingest fetch-statute 1-137 --if-changed   # the Hub's tree listing against the files on disk
    python -m ingest statute data/statute/xmls/STATUTE-64.xml --report docs/verification
    python -m ingest statute --volumes 1-137         # fetch what is missing, then load
    python -m ingest statute --volumes 1-137 --changed-only   # only files that differ from their last load
    python -m ingest comps ...                       # the COMPS poller (ingest/comps.py)
    python -m ingest citations --from-hub            # the citation index (ingest/citations.py)
    python -m ingest classifications                 # the classification tables mirror (ingest/classifications.py)
    python -m ingest plaw fetch 113-119              # PLAW bulk-data zips into data/plaw
    python -m ingest plaw load 118 --report docs/verification   # public laws from the zips (ingest/plaw.py)
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

    volumes = _volumes(",".join(args.volumes))
    if args.if_changed:
        return fetch_if_changed(volumes, Path(args.dir))
    for volume in volumes:
        path = fetch_volume(volume, Path(args.dir), force=args.force)
        print(f"{volume}\t{path}\t{path.stat().st_size} bytes")
    return 0


def fetch_if_changed(volumes: list[int], directory: Path) -> int:
    """One Hub tree listing; a volume is downloaded when the file on disk is
    missing or differs from the listed one (size, then sha). Writes one
    `STATUTE` check row either way: `new_packages` names what was fetched;
    `ok` is false when the listing could not be read."""
    from db.base import SessionLocal
    from ingest.hub import fetch_volume, list_volume_files
    from ingest.load import record_source_check

    with SessionLocal() as session:
        try:
            listed = list_volume_files()
        except Exception as exc:
            record_source_check(session, "STATUTE", ok=False, packages_seen=None, new_packages=[], error=repr(exc))
            print(f"the Hub listing could not be read: {exc!r}", file=sys.stderr)
            return 1
        fetched: list[str] = []
        missing = 0
        for volume in volumes:
            entry = listed.get(volume)
            target = directory / f"STATUTE-{volume}.xml"
            if entry is None:
                missing += 1
                print(f"{volume}\tnot on the Hub", file=sys.stderr)
                continue
            if entry.matches(target):
                print(f"{volume}\t{target}\tunchanged")
                continue
            path = fetch_volume(volume, directory, force=True)
            fetched.append(f"STATUTE-{volume}")
            print(f"{volume}\t{path}\t{path.stat().st_size} bytes\tfetched")
        record_source_check(session, "STATUTE", ok=True, packages_seen=len(listed), new_packages=fetched)
    print(f"{len(listed)} volumes listed, {len(volumes) - missing} asked for, {len(fetched)} fetched")
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
    loaded: list[str] = []
    for path in paths:
        with SessionLocal() as session:
            if args.changed_only and _unchanged_since_load(session, path):
                print(f"{path}: unchanged since its last load, skipped")
                continue
            try:
                report = load_volume(session, path)
            except Exception as exc:  # one bad volume must not stop the run
                session.rollback()
                failures += 1
                print(f"{path}: FAILED {exc!r}", file=sys.stderr)
                continue
        loaded.append(report.package)
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
    if args.changed_only and not loaded and not failures:
        # Every file was the one already loaded: say so in `source_checks`,
        # so `/status` records that the files were looked at.
        from ingest.load import record_source_check

        with SessionLocal() as session:
            record_source_check(session, "STATUTE", ok=True, packages_seen=len(paths), new_packages=[])
        print(f"{len(paths)} files unchanged since their last load; nothing loaded")
    return 1 if failures else 0


def _unchanged_since_load(session, path: Path) -> bool:
    """`statute --changed-only`: the file's sha256 equals the one its last
    load recorded. A file whose name carries no volume number, or a volume
    never loaded, counts as changed."""
    from ingest.hub import sha256_of, volume_of
    from ingest.load import recorded_volume_sha

    volume = volume_of(path)
    if volume is None:
        return False
    recorded = recorded_volume_sha(session, volume)
    return recorded is not None and recorded == sha256_of(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch-statute", help="download volume USLM from the Hub")
    fetch.add_argument("volumes", nargs="+", help="`64`, `64 72`, or `1-137`")
    fetch.add_argument("--dir", default=str(DATA_DIR))
    fetch.add_argument("--force", action="store_true")
    fetch.add_argument(
        "--if-changed", action="store_true",
        help="ask the Hub's tree listing and download only volumes whose file on disk differs; records a `source_checks` row",
    )
    fetch.set_defaults(func=cmd_fetch_statute)

    statute = sub.add_parser("statute", help="load STATUTE volume USLM")
    statute.add_argument("paths", nargs="*", help="volume XML files")
    statute.add_argument("--volumes", help="fetch (if needed) and load these volumes: `64,124` or `1-137`")
    statute.add_argument("--dir", default=str(DATA_DIR))
    statute.add_argument("--report", help="directory for the per-volume JSON report")
    statute.add_argument(
        "--changed-only", action="store_true",
        help="load only files whose sha256 differs from the one their last load recorded; records a `source_checks` row when nothing changed",
    )
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

    from ingest.plaw import add_plaw_commands

    plaw_commands = add_plaw_commands(sub)
    try:
        from ingest.plaw_poll import add_poll_command
    except ImportError:  # the poller lands with stage 4, part (a)
        add_poll_command = None
    if add_poll_command is not None:
        add_poll_command(plaw_commands)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
