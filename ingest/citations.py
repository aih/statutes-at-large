"""The citation index: every `<ref href>` in the US Code that points at a law,
an act, or a Statutes at Large page (design section 6, `citations`).

Source: the `dreamproit/uscode` dataset on the Hub, config `current` (one row
per US Code section, the section's verbatim USLM in `xml`). The rows are read
with pyarrow, which lives in the `dataset` dependency group; nothing in `api/`
imports this module.

What is extracted, per ref:

  * `context`: `sourceCredit` when a `sourceCredit` element encloses the ref,
    `note` when a `note` or `notes` element does, else `text`.
  * the target parsed into law, path and section number (`storage.identifiers`),
    so `/us/pl/104/333/dI/tVIII/s814/e/1` and `/us/pl/104/333/s814` both index
    under (`/us/pl/104/333`, `814`).
  * `to_date`: an act's date from its identifier; for a public law in a source
    credit or note, the `<date>` element that follows the ref before the next
    law ref (`Pub. L. 95–625, § 314, <date>Nov. 10, 1978</date>, 92 Stat. 3479`).

Rows are replaced per US Code title: the dataset carries one release label per
title, and a new export replaces every row whose citing section is in that
title. A `source_checks` row with collection `USCODE` records the run and the
dataset revision.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lxml import etree
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from db.models import Citation, LawAlias, SourceCheck
from storage.identifiers import parse_identifier, parse_stat_page
from uslmtext import local_name

COLLECTION = "USCODE"
CONFIG = "current"
DATA_DIR = Path("data/uscode")
STORED_PREFIXES = ("/us/pl/", "/us/pvtl/", "/us/act/", "/us/stat/")
COLUMNS = ["identifier", "citation", "title", "heading", "release_label", "release_seq", "xml"]
BATCH_ROWS = 500
COMMIT_EVERY_ROWS = 20_000
_PUNCTUATION = re.compile(r"^[\s,;.()]*$")
_ACT_BY_DATE = re.compile(r"^/us/act/(?P<date>\d{4}-\d{2}-\d{2})(?P<path>/(?!ch\d).*)?$")


# ------------------------------------------------------------------- records


@dataclass(slots=True)
class RefRecord:
    """One ref, parsed. Field names match the `citations` columns."""

    context: str
    note_topic: str | None
    seq: int
    to_identifier: str
    to_kind: str
    to_law: str | None = None
    to_path: str | None = None
    to_section_num: str | None = None
    to_congress: int | None = None
    to_number: int | None = None
    to_chapter: int | None = None
    to_date: datetime.date | None = None
    to_volume: int | None = None
    to_page: str | None = None
    parsed: bool = True


@dataclass(slots=True)
class SectionRefs:
    identifier: str
    title: str
    citation: str | None
    heading: str | None
    release_label: str
    release_seq: int | None
    refs: list[RefRecord]
    refs_total: int = 0
    refs_without_href: int = 0
    anchors: int = 0
    """`<a href>` citations in revision-note tables, stored like refs."""
    refs_by_prefix: Counter = field(default_factory=Counter)


@dataclass(slots=True)
class CitationLoadReport:
    config: str
    shards: list[str]
    dataset_revision: str | None
    loaded_at: str
    seconds: float = 0.0
    sections_read: int = 0
    sections_with_stored_refs: int = 0
    titles: int = 0
    refs_seen: int = 0
    """Every `ref` element in every section."""
    refs_without_href: int = 0
    anchors_stored: int = 0
    """`<a href>` citations from the XHTML tables in revision notes, stored like refs."""
    refs_by_prefix: dict[str, int] = field(default_factory=dict)
    """`usc`, `pl`, `pvtl`, `act`, `stat`, `other`: what the refs point at."""
    rows_written: int = 0
    rows_replaced: int = 0
    rows_by_context: dict[str, int] = field(default_factory=dict)
    rows_by_kind: dict[str, int] = field(default_factory=dict)
    rows_by_context_and_kind: dict[str, int] = field(default_factory=dict)
    """`sourceCredit/pl` → rows."""
    rows_act_by_date_only: int = 0
    """`/us/act/{date}/s{n}` with no chapter: indexed under the date, matched
    by no alias."""
    rows_unparsed: int = 0
    """Hrefs with a stored prefix that could not be parsed (`/us/stat/70A/641`:
    the lettered volumes 68A and 70A); stored verbatim with no law or section."""
    unparsed_samples: list[str] = field(default_factory=list)
    rows_with_date: int = 0
    distinct_targets: int = 0
    distinct_target_laws: int = 0
    distinct_target_sections: int = 0
    """(law, section number) pairs."""
    target_laws_loaded: int = 0
    """Distinct target laws that a loaded volume holds (by any alias)."""
    target_laws_not_loaded: int = 0
    release_labels: dict[str, int] = field(default_factory=dict)
    by_title: dict[str, dict] = field(default_factory=dict)
    """Per citing title: rows, sections, release labels."""


# ----------------------------------------------------------------- reading


def iter_shards(paths: Iterable[Path], *, batch_rows: int = BATCH_ROWS) -> Iterator[dict]:
    """Rows of the parquet shards, the columns the index needs, in shard order."""
    import pyarrow.parquet as pq

    for path in paths:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=batch_rows, columns=COLUMNS):
            yield from batch.to_pylist()


def shard_paths(directory: Path, *, config: str = CONFIG) -> list[Path]:
    """`train-*.parquet` under `directory`, or under `directory/{config}`."""
    directory = Path(directory)
    candidates = sorted(directory.glob("train-*.parquet")) or sorted((directory / config).glob("train-*.parquet"))
    return candidates


def _kind_of(href: str) -> str:
    parts = href.split("/")
    if len(parts) > 2 and parts[1] == "us":
        return parts[2]
    return "other"


def _law_of(href: str) -> RefRecord | None:
    """Parse a stored-prefix href into its columns."""
    kind = _kind_of(href)
    if kind == "stat":
        page = parse_stat_page(href)
        record = RefRecord(context="", note_topic=None, seq=0, to_identifier=href, to_kind="stat")
        if page is None:
            record.parsed = False
            return record
        record.to_volume, record.to_page = page.volume, page.page
        return record
    parsed = parse_identifier(href)
    record = RefRecord(context="", note_topic=None, seq=0, to_identifier=href, to_kind=kind)
    if parsed is None and kind == "act":
        # `/us/act/1934-06-18/s3`: an act cited by date alone, no chapter. Kept
        # under the date as its law; it answers to no loaded alias.
        match = _ACT_BY_DATE.match(href)
        if match:
            try:
                record.to_date = datetime.date.fromisoformat(match.group("date"))
            except ValueError:
                record.parsed = False
                return record
            record.to_law = f"/us/act/{match.group('date')}"
            record.to_path = (match.group("path") or "").rstrip("/")
            section = re.search(r"/s(\d[^/]*)", record.to_path)
            record.to_section_num = section.group(1) if section else None
            return record
    if parsed is None or parsed.kind not in ("pl", "pvtl", "act"):
        record.parsed = False
        return record
    record.to_kind = parsed.kind
    record.to_law = parsed.law_identifier
    record.to_path = parsed.path
    record.to_section_num = parsed.section_num
    record.to_congress = parsed.congress
    record.to_number = parsed.number
    record.to_chapter = parsed.chapter
    record.to_date = parsed.enacted
    return record


def extract_refs(xml: str, *, sink: SectionRefs | None = None) -> list[RefRecord]:
    """Every ref in the section's USLM that points at a law, an act, or a Stat.
    page, in document order, with its context and, in a source credit or note,
    the date the text gives for a public law."""
    root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    out: list[RefRecord] = []
    counts: Counter = Counter()
    without_href = 0
    total = 0
    anchors = 0
    pending: RefRecord | None = None
    pending_element: etree._Element | None = None
    for element in root.iter():
        name = local_name(element)
        if name == "date":
            # `<ref>Pub. L. 95–625, § 314</ref>, <date date="1978-11-10">…</date>`:
            # the date belongs to the ref when it is the very next element and
            # only punctuation lies between; a date further on is prose.
            if (
                pending is not None
                and pending.to_date is None
                and element.getprevious() is pending_element
                and _PUNCTUATION.match(pending_element.tail or "")
                and element.get("date")
            ):
                try:
                    pending.to_date = datetime.date.fromisoformat(element.get("date")[:10])
                except ValueError:
                    pass
            continue
        if name == "a":
            # The revision notes of positive-law titles hold XHTML tables whose
            # citations are `<a href>` rather than `<ref>`; same target forms.
            href = element.get("href")
            if not href or not href.startswith(STORED_PREFIXES):
                continue
            anchors += 1
        elif name != "ref":
            continue
        else:
            total += 1
            href = element.get("href")
            if not href:
                without_href += 1
                continue
        href = href.strip()
        kind = _kind_of(href)
        counts[kind if kind in ("usc", "pl", "pvtl", "act", "stat") else "other"] += 1
        if not href.startswith(STORED_PREFIXES):
            continue
        record = _law_of(href)
        if record is None:
            continue
        record.context, record.note_topic = _context(element, _container(element))
        record.seq = len(out)
        out.append(record)
        if record.to_kind in ("pl", "pvtl"):
            pending, pending_element = record, element
    if sink is not None:
        sink.refs_total = total
        sink.refs_without_href = without_href
        sink.anchors = anchors
        sink.refs_by_prefix = counts
    return out


def _container(element: etree._Element) -> etree._Element | None:
    """The nearest `sourceCredit`, `note`, or `notes` ancestor; None in text."""
    for ancestor in element.iterancestors():
        name = local_name(ancestor)
        if name in ("sourceCredit", "note", "notes"):
            return ancestor
    return None


def _context(element: etree._Element, container: etree._Element | None) -> tuple[str, str | None]:
    if container is None:
        return "text", None
    name = local_name(container)
    if name == "sourceCredit":
        return "sourceCredit", None
    topic = container.get("topic") or container.get("type") or container.get("role")
    if name == "notes":
        return "note", topic
    return "note", topic


def section_refs(row: dict) -> SectionRefs:
    section = SectionRefs(
        identifier=row["identifier"],
        title=str(row["title"]),
        citation=row.get("citation"),
        heading=row.get("heading"),
        release_label=row["release_label"],
        release_seq=row.get("release_seq"),
        refs=[],
    )
    section.refs = extract_refs(row["xml"], sink=section)
    return section


# ------------------------------------------------------------------ loading


def load_citations(session: Session, paths: list[Path], *, revision: str | None = None,
                   record_check: bool = True) -> CitationLoadReport:
    started = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    report = CitationLoadReport(
        config=CONFIG,
        shards=[str(p) for p in paths],
        dataset_revision=revision,
        loaded_at=now.isoformat(),
    )
    titles_seen: set[str] = set()
    prefixes: Counter = Counter()
    by_context: Counter = Counter()
    by_kind: Counter = Counter()
    by_both: Counter = Counter()
    labels: Counter = Counter()
    per_title: dict[str, dict] = {}
    targets: set[str] = set()
    target_laws: set[str] = set()
    target_sections: set[tuple[str, str]] = set()
    pending_rows: list[dict] = []
    since_commit = 0

    def flush() -> None:
        nonlocal pending_rows, since_commit
        if pending_rows:
            session.execute(insert(Citation), pending_rows)
            since_commit += len(pending_rows)
            pending_rows = []
        if since_commit >= COMMIT_EVERY_ROWS:
            session.commit()
            since_commit = 0

    for row in iter_shards(paths):
        section = section_refs(row)
        report.sections_read += 1
        report.refs_seen += section.refs_total
        report.refs_without_href += section.refs_without_href
        report.anchors_stored += section.anchors
        prefixes.update(section.refs_by_prefix)
        if section.title not in titles_seen:
            flush()
            titles_seen.add(section.title)
            deleted = session.execute(delete(Citation).where(Citation.from_title == section.title)).rowcount
            report.rows_replaced += max(int(deleted or 0), 0)
            per_title[section.title] = {"rows": 0, "sections": 0, "release_labels": Counter()}
        if not section.refs:
            continue
        report.sections_with_stored_refs += 1
        entry = per_title[section.title]
        entry["sections"] += 1
        entry["release_labels"][section.release_label] += 1
        for ref in section.refs:
            pending_rows.append(
                {
                    "from_identifier": section.identifier,
                    "from_title": section.title,
                    "from_citation": section.citation,
                    "from_heading": section.heading,
                    "release_label": section.release_label,
                    "release_seq": section.release_seq,
                    "context": ref.context,
                    "note_topic": ref.note_topic,
                    "seq": ref.seq,
                    "to_identifier": ref.to_identifier,
                    "to_kind": ref.to_kind,
                    "to_law": ref.to_law,
                    "to_path": ref.to_path,
                    "to_section_num": ref.to_section_num,
                    "to_congress": ref.to_congress,
                    "to_number": ref.to_number,
                    "to_chapter": ref.to_chapter,
                    "to_date": ref.to_date,
                    "to_volume": ref.to_volume,
                    "to_page": ref.to_page,
                }
            )
            report.rows_written += 1
            entry["rows"] += 1
            by_context[ref.context] += 1
            by_kind[ref.to_kind] += 1
            by_both[f"{ref.context}/{ref.to_kind}"] += 1
            labels[section.release_label] += 1
            targets.add(ref.to_identifier)
            if ref.to_law:
                target_laws.add(ref.to_law)
                if ref.to_section_num:
                    target_sections.add((ref.to_law, ref.to_section_num))
            if ref.to_kind == "act" and ref.to_chapter is None and ref.parsed:
                report.rows_act_by_date_only += 1
            if not ref.parsed:
                report.rows_unparsed += 1
                if len(report.unparsed_samples) < 20:
                    report.unparsed_samples.append(f"{section.identifier} → {ref.to_identifier}")
            if ref.to_date is not None:
                report.rows_with_date += 1
        if len(pending_rows) >= 5_000:
            flush()
    flush()

    report.titles = len(titles_seen)
    report.refs_by_prefix = dict(prefixes.most_common())
    report.rows_by_context = dict(by_context.most_common())
    report.rows_by_kind = dict(by_kind.most_common())
    report.rows_by_context_and_kind = dict(by_both.most_common())
    report.release_labels = dict(labels.most_common())
    report.distinct_targets = len(targets)
    report.distinct_target_laws = len(target_laws)
    report.distinct_target_sections = len(target_sections)
    report.by_title = {
        title: {"rows": v["rows"], "sections": v["sections"], "release_labels": dict(v["release_labels"].most_common())}
        for title, v in sorted(per_title.items(), key=lambda kv: _title_key(kv[0]))
    }
    loaded = _loaded_aliases(session, target_laws)
    report.target_laws_loaded = len(loaded)
    report.target_laws_not_loaded = len(target_laws) - len(loaded)
    if record_check:
        session.add(
            SourceCheck(
                collection=COLLECTION,
                checked_at=now,
                ok=True,
                newest_last_modified=None,
                newest_package=revision,
                packages_seen=len(paths),
                new_packages=[Path(p).name for p in paths],
                error=None,
            )
        )
    session.commit()
    report.seconds = round(time.monotonic() - started, 1)
    return report


def _loaded_aliases(session: Session, identifiers: set[str]) -> set[str]:
    found: set[str] = set()
    wanted = sorted(identifiers)
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        found.update(session.scalars(select(LawAlias.identifier).where(LawAlias.identifier.in_(chunk))).all())
    return found


def _title_key(title: str) -> tuple[int, str]:
    digits = "".join(ch for ch in title if ch.isdigit())
    return (int(digits) if digits else 0, title)


def write_report(report: CitationLoadReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "citations.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n")
    return target


# ------------------------------------------------------------- command line


def cmd_citations(args) -> int:
    import sys

    from db.base import SessionLocal

    revision: str | None = None
    if args.from_hub:
        from ingest.hub import fetch_uscode_shards

        revision, paths = fetch_uscode_shards(Path(args.dir), config=CONFIG, force=args.force)
    else:
        directory = Path(args.from_dir or args.dir)
        paths = shard_paths(directory)
        marker = directory / "REVISION"
        if marker.exists():
            revision = marker.read_text().strip() or None
    if not paths:
        print("no parquet shards found; use --from-hub or --from-dir PATH", file=sys.stderr)
        return 2
    with SessionLocal() as session:
        report = load_citations(session, paths, revision=revision)
    print(
        f"{COLLECTION} {CONFIG}: {report.sections_read} sections read, {report.rows_written} rows "
        f"{report.rows_by_context} over {report.titles} titles, {report.seconds}s"
    )
    if args.report:
        target = write_report(report, Path(args.report))
        print(f"  report {target}")
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    return 0


def add_citations_commands(sub) -> None:
    parser = sub.add_parser("citations", help="build the citation index from the dreamproit/uscode dataset")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-hub", action="store_true", help="download the `current` shards into --dir, then load")
    source.add_argument("--from-dir", help="load the parquet shards in this directory")
    parser.add_argument("--dir", default=str(DATA_DIR), help="where --from-hub keeps the shards")
    parser.add_argument("--force", action="store_true", help="re-download shards already present")
    parser.add_argument("--report", help="directory for citations.json")
    parser.add_argument("--json", action="store_true", help="print the report")
    parser.set_defaults(func=cmd_citations)
