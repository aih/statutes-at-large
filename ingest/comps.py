"""GovInfo `COMPS` (Statute Compilations): parser, loader, poller, command line.

A compilation file (`statuteCompilation` root, USLM 2.0.x) carries GPO's own
identifiers on every level (`/us/sComp/83/703/tI/ch1./s1/a`), so nothing is
assigned here; the identifiers are read and kept as written (CLAUDE.md gotcha
7). The prefix `/us/sComp/{congress}/{number}` names a public law or, before
1901, a chapter (gotcha 8), and several files may share it (the Social Security
Act has one file per title).

Sections are the storage atom, as for the volumes: a `CompUnitRecord` per
hierarchy node and per section that carries an `@identifier`; levels below a
section travel inside the section's XML. A section without an identifier (the
Sherman Act's short-title paragraph) is counted and stays in the document XML.

Each fetch whose content hash differs from every stored version of the file
becomes a new `comp_versions` row; GovInfo keeps only the current text, so the
history starts at the first ingest (design section 4).
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Comp, CompUnit, CompVersion, Law, LawAlias, SourceCheck
from ingest.identifiers import FIRST_NUMBERED_CONGRESS, HIERARCHY_LEVELS, designator
from uslmtext import USLM_NS, content_hash, local_name, plain_text, serialize

N = f"{{{USLM_NS}}}"
DC = "{http://purl.org/dc/elements/1.1/}"

TEXT_PROVENANCE = "gpo-uslm"
IDENTIFIER_PROVENANCE = "gpo-uslm"
COLLECTION = "COMPS"
DEFAULT_SINCE = datetime.datetime(1990, 1, 1, tzinfo=datetime.timezone.utc)
SINCE_OVERLAP = datetime.timedelta(days=1)

#: Subtrees in which a `section` is not a section of this compilation.
SKIP_SUBTREES = frozenset({"quotedContent", "toc", "sidenote", "footnote", "note", "editorialContent"})

_PREFIX = re.compile(r"^(/us/sComp/(?P<congress>\d+)/(?P<number>\d+))(?:/|$)")
_PL = re.compile(r"(?P<congress>\d+)\s*[-–—]\s*(?P<number>\d+)")
_TITLE_OF = re.compile(r"\bTITLE\s+(?P<num>[IVXLCDM]+|\d+)\b", re.IGNORECASE)


# ------------------------------------------------------------------- records


@dataclass(slots=True)
class CompUnitRecord:
    identifier: str
    parent_identifier: str | None
    level: str
    num: str | None
    heading: str | None
    section_num: str | None
    seq: int
    depth: int
    ancestors: list[dict]
    xml: str | None
    text: str | None
    content_hash: str | None
    usc_refs: list[str]


@dataclass(slots=True)
class CompRecord:
    file_id: str
    package_id: str
    identifier_prefix: str
    law_congress: int | None
    law_number: int | None
    congress: int | None
    """`meta/congress`."""
    approved_date: datetime.date | None
    doc_number: str | None
    """`meta/docNumber`: `ch531`."""
    citable_as: list[str]
    title: str | None
    """The summary's `title` (the long title)."""
    display_title: str | None
    dc_title: str | None
    short_titles: list[str]
    current_through_pl: str | None
    """`118-67`, hyphen."""
    current_through_date: datetime.date | None
    govinfo_last_modified: datetime.datetime | None
    partial_of: str | None
    xml: str
    content_hash: str
    units: list[CompUnitRecord]
    unidentified_sections: int = 0
    duplicate_identifiers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def sections(self) -> list[CompUnitRecord]:
        return [u for u in self.units if u.level == "section"]

    @property
    def law_identifier_candidate(self) -> str | None:
        """`/us/pl/{c}/{n}` for a law of the numbered era, else None (the
        prefix's second number is then a chapter)."""
        if self.law_congress is None or self.law_number is None:
            return None
        if self.law_congress < FIRST_NUMBERED_CONGRESS:
            return None
        return f"/us/pl/{self.law_congress}/{self.law_number}"


@dataclass(slots=True)
class CompLoadReport:
    file_id: str
    package_id: str
    identifier_prefix: str
    action: str
    """`new` (first version of a new compilation) | `new_version` | `unchanged`."""
    version_id: int | None
    current_through_pl: str | None
    current_through_date: str | None
    content_hash: str
    law_identifier: str | None
    units: int = 0
    sections: int = 0
    units_by_level: dict[str, int] = field(default_factory=dict)
    unidentified_sections: int = 0
    duplicate_identifiers: list[str] = field(default_factory=list)
    versions: int = 0
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


@dataclass(slots=True)
class PollReport:
    collection: str
    since: str
    checked_at: str
    seen: int = 0
    fetched: int = 0
    new: int = 0
    new_versions: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    newest_last_modified: str | None = None
    newest_package: str | None = None
    new_packages: list[str] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    seconds: float = 0.0


# -------------------------------------------------------------------- parsing


def parse_comp(xml_text: str, *, summary: dict | None = None) -> CompRecord:
    """One COMPS USLM document (plus its GovInfo package summary, when given)
    → a `CompRecord` with its units."""
    summary = summary or {}
    root = etree.fromstring(xml_text.encode("utf-8"))
    if local_name(root) != "statuteCompilation":
        raise ValueError(f"not a statuteCompilation document: root is {local_name(root)}")
    meta = root.find(f"{N}meta")
    if meta is None:
        raise ValueError("no meta element")
    warnings: list[str] = []

    file_id = _text(meta.find(f"{N}property[@role='fileId']"))
    package_id = _str(summary.get("packageId")) or (f"COMPS-{file_id}" if file_id else None)
    if not file_id:
        if package_id and package_id.startswith("COMPS-"):
            file_id = package_id.removeprefix("COMPS-")
            warnings.append("no fileId property; taken from the package id")
        else:
            raise ValueError("no fileId property and no packageId in the summary")
    assert package_id is not None

    dc_title = _text(meta.find(f"{DC}title"))
    contains = [t for t in (_text(e) for e in meta.findall(f"{N}containsShortTitle")) if t]
    congress = _int(_text(meta.find(f"{N}congress")))
    approved = _date(_text(meta.find(f"{N}approvedDate")))
    doc_number = _text(meta.find(f"{N}docNumber"))
    citable_as = [t for t in (_text(e) for e in meta.findall(f"{N}citableAs")) if t]
    through_pl = normalize_pl(_text(meta.find(f"{N}currentThroughPublicLaw")))

    preface = root.find(f"{N}preface")
    through_date = None
    if preface is not None:
        for note in preface.findall(f"{N}editionNote"):
            date = note.find(f".//{N}date")
            if date is not None and date.get("date"):
                through_date = _date(date.get("date"))
                break
            if through_pl is None:
                through_pl = normalize_pl(_text(note.find(f".//{N}currentThroughPublicLaw")))
    amended = _amended_through(summary)
    if through_pl is None and amended:
        through_pl = amended.get("pl")
        if through_pl:
            warnings.append("currentThroughPublicLaw taken from the summary")
    if through_date is None and amended:
        through_date = amended.get("enacted")
        if through_date:
            warnings.append("current-through date taken from the summary")

    prefix, law_congress, law_number = _prefix_of(root)
    if (
        through_date is None
        and approved is not None
        and through_pl is not None
        and law_congress is not None
        and through_pl == f"{law_congress}-{law_number}"
    ):
        # "[This law has not been amended]": current through its own enactment.
        through_date = approved
        warnings.append("current-through date is the approval date (the law has not been amended)")
    if prefix is None:
        law_congress = _int(_nested(summary, "law", "congress")) or congress
        law_number = _int(_nested(summary, "law", "number")) or _chapter_of(doc_number)
        if law_congress is None or law_number is None:
            raise ValueError("no /us/sComp/ identifier in the document and no law in the summary")
        prefix = f"/us/sComp/{law_congress}/{law_number}"
        warnings.append("no identifier in the document; prefix built from the summary")

    main = root.find(f"{N}main")
    units: list[CompUnitRecord] = []
    unidentified = 0
    duplicates: list[str] = []
    if main is None:
        warnings.append("no main element")
    else:
        units, unidentified, duplicates = _walk_units(main, warnings)

    summary_short = [
        t for t in (_str(s.get("title")) for s in _as_list(summary.get("shortTitle")) if isinstance(s, dict)) if t
    ]
    short_titles = _dedupe(summary_short + contains)
    display_title = _str(summary.get("displayTitle")) or dc_title
    top_levels = [u for u in units if u.depth == 1]
    partial_of = _partial_of([display_title or ""] + contains, top_levels)

    return CompRecord(
        file_id=file_id,
        package_id=package_id,
        identifier_prefix=prefix,
        law_congress=law_congress,
        law_number=law_number,
        congress=congress,
        approved_date=approved,
        doc_number=doc_number,
        citable_as=citable_as,
        title=_str(summary.get("title")),
        display_title=display_title,
        dc_title=dc_title,
        short_titles=short_titles,
        current_through_pl=through_pl,
        current_through_date=through_date,
        govinfo_last_modified=_datetime(_str(summary.get("lastModified"))),
        partial_of=partial_of,
        xml=xml_text,
        content_hash=content_hash(xml_text),
        units=units,
        unidentified_sections=unidentified,
        duplicate_identifiers=duplicates,
        warnings=warnings,
    )


def normalize_pl(text: str | None) -> str | None:
    """`118–67`, `P.L. 118-67` → `118-67`."""
    if not text:
        return None
    match = _PL.search(text)
    if not match:
        return None
    return f"{int(match.group('congress'))}-{int(match.group('number'))}"


def _prefix_of(root: etree._Element) -> tuple[str | None, int | None, int | None]:
    """The prefix from the first `/us/sComp/…` identifier in document order."""
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        identifier = element.get("identifier")
        if not identifier:
            continue
        match = _PREFIX.match(identifier.strip())
        if match:
            return match.group(1), int(match.group("congress")), int(match.group("number"))
    return None, None, None


def _walk_units(main: etree._Element, warnings: list[str]) -> tuple[list[CompUnitRecord], int, list[str]]:
    units: list[CompUnitRecord] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    unidentified = 0
    seq = 0
    for element in main.iter():
        name = local_name(element)
        if name is None or element is main:
            continue
        if name != "section" and name not in HIERARCHY_LEVELS:
            continue
        if _inside_skipped(element, main):
            continue
        identifier = (element.get("identifier") or "").strip()
        if not identifier:
            if name == "section":
                unidentified += 1
            continue
        if identifier in seen:
            duplicates.append(identifier)
            warnings.append(f"{identifier} occurs more than once; the later one stays in the document XML")
            continue
        seen.add(identifier)
        ancestors = _ancestor_units(element, main)
        seq += 1
        num = _num_of(element, name)
        if name == "section":
            xml = serialize(element)
            text = plain_text(element)
            digest = content_hash(xml)
        else:
            xml = text = digest = None
        units.append(
            CompUnitRecord(
                identifier=identifier,
                parent_identifier=ancestors[-1]["identifier"] if ancestors else None,
                level=name,
                num=num,
                heading=_heading_of(element),
                section_num=num if name == "section" else None,
                seq=seq,
                depth=len(ancestors) + 1,
                ancestors=ancestors,
                xml=xml,
                text=text,
                content_hash=digest,
                usc_refs=_usc_refs(element) if name == "section" else [],
            )
        )
    return units, unidentified, duplicates


def _inside_skipped(element: etree._Element, stop: etree._Element) -> bool:
    for ancestor in element.iterancestors():
        if ancestor is stop:
            return False
        if local_name(ancestor) in SKIP_SUBTREES:
            return True
    return False


def _ancestor_units(element: etree._Element, stop: etree._Element) -> list[dict]:
    chain: list[dict] = []
    for ancestor in element.iterancestors():
        if ancestor is stop:
            break
        name = local_name(ancestor)
        if name in HIERARCHY_LEVELS and (ancestor.get("identifier") or "").strip():
            chain.append(
                {
                    "identifier": ancestor.get("identifier").strip(),
                    "level": name,
                    "num": _num_of(ancestor, name),
                    "heading": _heading_of(ancestor),
                }
            )
    chain.reverse()
    return chain


def _num_of(element: etree._Element, level: str) -> str | None:
    """`num/@value` as GPO wrote it (`1.` for the compilations' chapters);
    the `num` text is the fallback."""
    num = element.find(f"{N}num")
    if num is None:
        return None
    value = num.get("value")
    if value is not None and value.strip():
        return "".join(value.split())
    return designator(level, None, plain_text(num, skip=frozenset({"sidenote", "footnote", "page"})))


def _heading_of(element: etree._Element) -> str | None:
    heading = element.find(f"{N}heading")
    if heading is None:
        return None
    text = plain_text(heading).strip()
    return text or None


def _usc_refs(section: etree._Element) -> list[str]:
    refs: list[str] = []
    for note in section.iter(f"{N}editorialNote"):
        if note.get("role") != "uscRef":
            continue
        for ref in note.iter(f"{N}ref"):
            href = (ref.get("href") or "").strip()
            if href.startswith("/us/usc/") and href not in refs:
                refs.append(href)
    return refs


def _partial_of(texts: list[str], top_levels: list[CompUnitRecord]) -> str | None:
    """`II` when the file is one title of a larger act: the display title or a
    short title says `TITLE II` and the document's only top-level unit is a
    title."""
    if len(top_levels) != 1 or top_levels[0].level != "title":
        return None
    title_num = (top_levels[0].num or "").rstrip(".")
    found: list[str] = []
    for text in texts:
        for match in _TITLE_OF.finditer(text or ""):
            num = match.group("num").upper()
            if num not in found:
                found.append(num)
    if not found:
        return None
    if title_num.upper() in found:
        return title_num
    return found[0]


def _amended_through(summary: dict) -> dict | None:
    """The summary's `amendedThrough` is a dict for one entry and a list for
    several (the same law twice, in COMPS-1630)."""
    entries = [e for e in _as_list(summary.get("amendedThrough")) if isinstance(e, dict)]
    if not entries:
        return None
    entry = entries[-1]
    congress, number = _int(_str(entry.get("congress"))), _int(_str(entry.get("publicLaw")))
    return {
        "pl": f"{congress}-{number}" if congress is not None and number is not None else None,
        "enacted": _date(_str(entry.get("enacted"))),
    }


def _chapter_of(doc_number: str | None) -> int | None:
    if not doc_number:
        return None
    match = re.search(r"ch\.?\s*(\d+)", doc_number, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _nested(data: dict, *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _dedupe(values: list[str]) -> list[str]:
    """Order kept, first form kept; `ATOMIC ENERGY ACT OF 1954` and `Atomic
    Energy Act of 1954.` are the same title."""
    out: list[str] = []
    keys: set[str] = set()
    for value in values:
        cleaned = " ".join(value.split())
        key = cleaned.casefold().rstrip(".").strip()
        if cleaned and key and key not in keys:
            keys.add(key)
            out.append(cleaned)
    return out


def _text(element: etree._Element | None) -> str | None:
    if element is None:
        return None
    text = " ".join("".join(element.itertext()).split())
    return text or None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def _date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value.strip()[:10])
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
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


# -------------------------------------------------------------------- loading


def load_comp(session: Session, record: CompRecord, *, fetched_at: datetime.datetime | None = None) -> CompLoadReport:
    """Upsert the `comps` row by `file_id`; add a `comp_versions` row (with its
    units) when the content hash is new; commit."""
    started = time.monotonic()
    now = fetched_at or datetime.datetime.now(datetime.timezone.utc)
    comp = session.scalars(select(Comp).where(Comp.file_id == record.file_id)).first()
    if comp is None:
        comp = session.scalars(select(Comp).where(Comp.package_id == record.package_id)).first()
    created = comp is None
    if comp is None:
        comp = Comp(file_id=record.file_id, package_id=record.package_id, identifier_prefix=record.identifier_prefix)
        session.add(comp)
    comp.file_id = record.file_id
    comp.package_id = record.package_id
    comp.identifier_prefix = record.identifier_prefix
    comp.law_congress = record.law_congress
    comp.law_number = record.law_number
    comp.title = record.title
    comp.display_title = record.display_title
    comp.short_titles = list(record.short_titles)
    comp.approved_date = record.approved_date
    comp.partial_of = record.partial_of
    law = _law_for(session, record)
    comp.law_id = law.id if law is not None else None
    session.flush()

    existing = session.scalars(
        select(CompVersion).where(CompVersion.comp_id == comp.id, CompVersion.content_hash == record.content_hash)
    ).first()
    report = CompLoadReport(
        file_id=comp.file_id,
        package_id=comp.package_id,
        identifier_prefix=comp.identifier_prefix,
        action="unchanged",
        version_id=None,
        current_through_pl=record.current_through_pl,
        current_through_date=record.current_through_date.isoformat() if record.current_through_date else None,
        content_hash=record.content_hash,
        law_identifier=law.identifier if law is not None else None,
        units=len(record.units),
        sections=len(record.sections),
        units_by_level=dict(Counter(u.level for u in record.units)),
        unidentified_sections=record.unidentified_sections,
        duplicate_identifiers=list(record.duplicate_identifiers),
        warnings=list(record.warnings),
    )
    if existing is not None and existing.current_through_pl == record.current_through_pl:
        report.version_id = existing.id
    elif existing is not None:
        # The same bytes under a different currentThroughPublicLaw cannot
        # happen (the law is inside the hashed text) and could not be stored
        # twice (`uq_comp_versions_hash`); the stored row takes the new label.
        existing.current_through_pl = record.current_through_pl
        existing.current_through_date = record.current_through_date
        existing.govinfo_last_modified = record.govinfo_last_modified
        existing.fetched_at = now
        _make_current(session, comp, existing)
        report.action = "new_version"
        report.version_id = existing.id
        report.warnings.append("content hash already stored under another currentThroughPublicLaw; relabeled")
    else:
        version = CompVersion(
            comp_id=comp.id,
            current_through_pl=record.current_through_pl,
            current_through_date=record.current_through_date,
            govinfo_last_modified=record.govinfo_last_modified,
            fetched_at=now,
            content_hash=record.content_hash,
            xml=record.xml,
            is_current=True,
        )
        session.add(version)
        session.flush()
        _make_current(session, comp, version)
        session.add_all(
            CompUnit(
                comp_version_id=version.id,
                identifier=u.identifier,
                parent_identifier=u.parent_identifier,
                level=u.level,
                num=u.num,
                heading=u.heading,
                section_num=u.section_num,
                seq=u.seq,
                depth=u.depth,
                ancestors=u.ancestors,
                xml=u.xml,
                text=u.text,
                content_hash=u.content_hash,
                usc_refs=u.usc_refs,
            )
            for u in record.units
        )
        report.action = "new" if created else "new_version"
        report.version_id = version.id
    session.commit()
    report.versions = len(session.scalars(select(CompVersion.id).where(CompVersion.comp_id == comp.id)).all())
    report.seconds = round(time.monotonic() - started, 2)
    return report


def _make_current(session: Session, comp: Comp, version: CompVersion) -> None:
    for other in session.scalars(select(CompVersion).where(CompVersion.comp_id == comp.id)).all():
        other.is_current = other.id == version.id
    version.is_current = True


def _law_for(session: Session, record: CompRecord) -> Law | None:
    """The enacted law the prefix names: the `/us/pl/{c}/{n}` alias, else the
    act with that congress and chapter number."""
    if record.law_congress is None or record.law_number is None:
        return None
    candidate = record.law_identifier_candidate
    if candidate is not None:
        law = session.scalars(
            select(Law).join(LawAlias, LawAlias.law_id == Law.id).where(LawAlias.identifier == candidate)
        ).first()
        if law is not None:
            return law
    return session.scalars(
        select(Law)
        .where(Law.congress == record.law_congress, Law.chapter == record.law_number, Law.kind == "act")
        .order_by(Law.id)
    ).first()


def load_comp_file(session: Session, path: Path | str, *, summary_path: Path | str | None = None) -> CompLoadReport:
    path = Path(path)
    summary = None
    if summary_path is not None:
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    record = parse_comp(path.read_text(encoding="utf-8"), summary=summary)
    return load_comp(session, record)


# -------------------------------------------------------------------- polling


def poll(
    session: Session,
    client: Any,
    *,
    since: datetime.datetime | None = None,
    limit: int | None = None,
    force: bool = False,
) -> PollReport:
    """Walk `collections/COMPS/{since}` and load what changed. A `source_checks`
    row is written whether the walk succeeded or not."""
    started = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    if since is None:
        since = default_since(session)
    report = PollReport(collection=COLLECTION, since=since.isoformat(), checked_at=now.isoformat())
    newest: datetime.datetime | None = None
    try:
        for package in client.collection(COLLECTION, since):
            # The limit counts packages fetched, not seen: a package already
            # current costs no API call, and GovInfo lists newest first, so a
            # walk of the whole collection (`--since 1990-01-01 --limit 400`,
            # repeated hourly under the 1,000 calls an hour) advances past
            # what earlier runs loaded.
            if limit is not None and report.fetched >= limit:
                break
            report.seen += 1
            package_id = str(package.get("packageId") or "").strip()
            last_modified = _datetime(_str(package.get("lastModified")))
            if last_modified is not None and (newest is None or last_modified > newest):
                newest = last_modified
                report.newest_package = package_id
            if not package_id:
                report.failed += 1
                report.failures.append({"package": None, "error": "package without a packageId"})
                continue
            if not force and _already_current(session, package_id, last_modified):
                report.skipped += 1
                continue
            report.fetched += 1
            try:
                summary = client.summary(package_id)
                xml_text = client.uslm(package_id)
                record = parse_comp(xml_text, summary=summary)
                if record.package_id != package_id:
                    record.package_id = package_id
                loaded = load_comp(session, record, fetched_at=now)
            except Exception as exc:  # one bad package must not end the walk
                session.rollback()
                report.failed += 1
                report.failures.append({"package": package_id, "error": _error_text(exc)})
                continue
            if loaded.action == "new":
                report.new += 1
                report.new_packages.append(package_id)
            elif loaded.action == "new_version":
                report.new_versions += 1
                report.new_packages.append(package_id)
            else:
                report.unchanged += 1
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
        report.error = f"{report.failed} package(s) failed: " + "; ".join(
            f"{f['package']}: {f['error']}" for f in report.failures[:10]
        )
    report.seconds = round(time.monotonic() - started, 1)
    _record_check(session, now, report, newest)
    return report


def default_since(session: Session) -> datetime.datetime:
    """The newest `lastModified` any COMPS check has seen, less a day of
    overlap; 1990-01-01 before the first poll."""
    newest = session.scalar(
        select(SourceCheck.newest_last_modified)
        .where(SourceCheck.collection == COLLECTION, SourceCheck.newest_last_modified.is_not(None))
        .order_by(SourceCheck.newest_last_modified.desc())
        .limit(1)
    )
    if newest is None:
        return DEFAULT_SINCE
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=datetime.timezone.utc)
    return newest - SINCE_OVERLAP


def _already_current(session: Session, package_id: str, last_modified: datetime.datetime | None) -> bool:
    comp = session.scalars(select(Comp).where(Comp.package_id == package_id)).first()
    if comp is None:
        return False
    current = session.scalars(
        select(CompVersion).where(CompVersion.comp_id == comp.id, CompVersion.is_current.is_(True)).order_by(CompVersion.id.desc())
    ).first()
    if current is None or current.govinfo_last_modified is None or last_modified is None:
        return False
    stored = current.govinfo_last_modified
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=datetime.timezone.utc)
    return stored >= last_modified


def _record_check(session: Session, now: datetime.datetime, report: PollReport, newest: datetime.datetime | None) -> None:
    session.add(
        SourceCheck(
            collection=COLLECTION,
            checked_at=now,
            ok=report.ok,
            newest_last_modified=newest,
            newest_package=report.newest_package,
            packages_seen=report.seen,
            new_packages=list(report.new_packages),
            error=report.error,
        )
    )
    session.commit()


def _error_text(exc: BaseException) -> str:
    from ingest.govinfo import strip_query

    message = strip_query(str(exc)).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


# --------------------------------------------------------------- command line


def _client():
    from ingest.govinfo import GovInfoClient

    return GovInfoClient()


def _print_load(report: CompLoadReport) -> None:
    line = (
        f"{report.package_id}: {report.action}, {report.identifier_prefix}, through P.L. "
        f"{report.current_through_pl} ({report.current_through_date}), {report.units} units, "
        f"{report.sections} sections, {report.versions} version(s), law {report.law_identifier}"
    )
    if report.unidentified_sections:
        line += f", {report.unidentified_sections} unidentified section(s) left in the XML"
    if report.duplicate_identifiers:
        line += f", {len(report.duplicate_identifiers)} duplicate identifier(s)"
    print(line)
    for warning in report.warnings:
        print(f"  warning: {warning}")


def cmd_poll(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    since = None
    if args.since:
        since = datetime.datetime.fromisoformat(args.since)
        if since.tzinfo is None:
            since = since.replace(tzinfo=datetime.timezone.utc)
    with _client() as client, SessionLocal() as session:
        try:
            report = poll(session, client, since=since, limit=args.limit, force=args.force)
        except Exception as exc:
            print(f"COMPS poll FAILED: {_error_text(exc)}", file=sys.stderr)
            return 1
    print(
        f"COMPS since {report.since}: {report.seen} seen, {report.skipped} already current, "
        f"{report.fetched} fetched, {report.new} new, {report.new_versions} new versions, "
        f"{report.unchanged} unchanged, {report.failed} failed, newest {report.newest_last_modified} "
        f"({report.newest_package}), {report.seconds}s"
    )
    for failure in report.failures:
        print(f"  failed {failure['package']}: {failure['error']}", file=sys.stderr)
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    return 1 if report.failed and not (report.new or report.new_versions or report.unchanged or report.skipped) else 0


def cmd_load(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    failures = 0
    with _client() as client:
        for package_id in args.packages:
            package_id = package_id if package_id.upper().startswith("COMPS-") else f"COMPS-{package_id}"
            with SessionLocal() as session:
                try:
                    summary = client.summary(package_id)
                    record = parse_comp(client.uslm(package_id), summary=summary)
                    report = load_comp(session, record)
                except Exception as exc:
                    session.rollback()
                    failures += 1
                    print(f"{package_id}: FAILED {_error_text(exc)}", file=sys.stderr)
                    continue
            _print_load(report)
            if args.json:
                print(json.dumps(asdict(report), indent=2))
    return 1 if failures else 0


def cmd_load_file(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    with SessionLocal() as session:
        report = load_comp_file(session, Path(args.path), summary_path=Path(args.summary) if args.summary else None)
    _print_load(report)
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from db.base import SessionLocal
    from storage.postgres import PostgresRepository

    with SessionLocal() as session:
        repository = PostgresRepository(session)
        status = repository.collection_status(COLLECTION)
        check = repository.last_source_check(COLLECTION)
        comps = repository.list_comps(limit=200) if args.list else []
    print(
        f"COMPS: {status.packages_loaded} compilations loaded, {status.units} units; "
        f"latest package {status.latest_package} fetched {status.latest_loaded_at}"
    )
    if check is None:
        print("last check: none")
    else:
        print(
            f"last check: {check.checked_at} ok={check.ok} seen={check.packages_seen} "
            f"newest={check.newest_last_modified} ({check.newest_package}) new={list(check.new_packages)} "
            f"stale={check.is_stale()}"
            + (f" error={check.error}" if check.error else "")
        )
    for comp in comps:
        current = comp.current
        print(
            f"  {comp.package_id}\t{comp.identifier_prefix}\t{comp.display_title}\t"
            f"through {current.current_through_pl if current else None}\tlaw {comp.law_identifier}"
        )
    return 0


def add_comps_commands(sub: argparse._SubParsersAction) -> None:
    comps = sub.add_parser("comps", help="GovInfo Statute Compilations: poll, load, report")
    inner = comps.add_subparsers(dest="comps_command", required=True)

    poll_parser = inner.add_parser("poll", help="walk collections/COMPS/{since} and load what changed")
    poll_parser.add_argument("--since", help="YYYY-MM-DD; default: the newest lastModified seen, less a day")
    poll_parser.add_argument("--limit", type=int, help="stop after fetching this many packages (already-current ones do not count)")
    poll_parser.add_argument("--force", action="store_true", help="fetch packages already current")
    poll_parser.add_argument("--json", action="store_true")
    poll_parser.set_defaults(func=cmd_poll)

    load_parser = inner.add_parser("load", help="fetch and load packages by id")
    load_parser.add_argument("packages", nargs="+", help="`COMPS-1630` or `1630`")
    load_parser.add_argument("--json", action="store_true")
    load_parser.set_defaults(func=cmd_load)

    file_parser = inner.add_parser("load-file", help="load a COMPS USLM file from disk")
    file_parser.add_argument("path")
    file_parser.add_argument("--summary", help="the package summary JSON")
    file_parser.add_argument("--json", action="store_true")
    file_parser.set_defaults(func=cmd_load_file)

    report_parser = inner.add_parser("report", help="what is loaded and the last poll")
    report_parser.add_argument("--list", action="store_true", help="list the loaded compilations")
    report_parser.set_defaults(func=cmd_report)
