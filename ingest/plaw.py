"""GovInfo `PLAW` bulk data (public laws, 113th Congress onward): parser,
loader, fetch, command line.

A bulk-data file (`PLAW-118publ22.xml`, root `pLaw`, USLM 2.0.17) is one
public law with GPO's own identifiers on every level
(`/us/pl/118/22/dB/tI/s102/c/2/A`). Nothing is assigned where GPO wrote one;
the identifiers are read and kept as written, and the law's
`provenance_identifiers` is `gpo-uslm`. Where a level carries no identifier
(the unnumbered single section of Public Law 118-1; the general-provisions
sections inside `level` blocks of appropriations acts), the rules of
`ingest/identifiers.py` fill it in from the nearest identified ancestor, the
count is reported per level, and the provenance becomes `gpo-uslm+rules-1.0`
(ADR-0011).

Sections are the storage atom, as for the volumes: a `UnitRecord` per
hierarchy node and per section outside `quotedContent`; levels below a section
travel inside the section's XML with the identifiers they came with.

A PLAW load replaces the volume-derived copy of the same law and writes, for
each law both sources held, the set difference between the rules-1.0
identifiers and GPO's, per level (`docs/verification/plaw-{congress}.json`).
Private laws are not in bulk data and stay volume-derived.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import re
import sys
import time
import zipfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from lxml import etree
from sqlalchemy.orm import Session

from db.models import SourceCheck
from ingest.hub import USER_AGENT
from ingest.identifiers import (
    HIERARCHY_LEVELS,
    LEVEL_PREFIX,
    SUBSECTION_LEVELS,
    parse_doc_number,
    segment,
)
from ingest.statute import (
    DC,
    IDENTIFIER_RULES_VERSION as _RULES,
    N,
    LawRecord,
    UnitRecord,
    _all_pages,
    _ancestor_units,
    _date,
    _designator_of,
    _doc_kind,
    _enclosing_unit,
    _heading_of,
    _inside_skipped,
    _parent_identifier,
    _short_titles,
    page_label,
)
from uslmtext import content_hash, local_name, plain_text, serialize

COLLECTION = "PLAW"
IDENTIFIER_PROVENANCE = "gpo-uslm"
MIXED_PROVENANCE = f"gpo-uslm+{_RULES}"
FIRST_USLM_CONGRESS = 113
"""Bulk-data USLM begins with the 113th Congress (2013)."""
FIRST_PLAW_CONGRESS = 104
"""GovInfo's PLAW collection begins with the 104th Congress (1995), PDF and
text only before the 113th."""

BULK_ROOT = "https://www.govinfo.gov/bulkdata"
BULK_JSON = f"{BULK_ROOT}/json"
DATA_DIR = Path("data/plaw")
COMMIT_EVERY = 50

_STAT_CITE = re.compile(r"(?P<volume>\d+)\s*Stat\.?\s*(?P<page>[0-9A-Za-z]+(?:-\d+)?)", re.IGNORECASE)
_STAT_PI = re.compile(r"(?P<volume>\d+)\s*STAT", re.IGNORECASE)
_FILE_NAME = re.compile(r"PLAW-(?P<congress>\d+)(?P<kind>publ|pvtl)(?P<number>\d+)\.xml$", re.IGNORECASE)
_LEADING_LAW = re.compile(r"^(?:Public|Private)\s+Law\s+[\d–-]+:\s*", re.IGNORECASE)

#: Every level an identifier is read for: hierarchy nodes and sections (units)
#: and the levels below a section (stamped inside the section's XML).
IDENTIFIED_LEVELS: frozenset[str] = frozenset(HIERARCHY_LEVELS) | {"section"} | frozenset(SUBSECTION_LEVELS)


# ---------------------------------------------------------------------- names


def package_id(congress: int, number: int, kind: str = "pl") -> str:
    """`PLAW-118publ22`; `PLAW-118pvtl1` for a private law."""
    return f"PLAW-{congress}{'publ' if kind == 'pl' else 'pvtl'}{number}"


def parse_package_id(text: str) -> tuple[int, str, int] | None:
    """`PLAW-118publ22` or `PLAW-118publ22.xml` → (118, `pl`, 22)."""
    match = re.search(r"PLAW-(?P<congress>\d+)(?P<kind>publ|pvtl)(?P<number>\d+)", text, re.IGNORECASE)
    if not match:
        return None
    kind = "pl" if match.group("kind").lower() == "publ" else "pvtl"
    return int(match.group("congress")), kind, int(match.group("number"))


def listing_url(congress: int) -> str:
    return f"{BULK_JSON}/PLAW/{congress}/public"


def file_url(congress: int, number: int) -> str:
    return f"{BULK_ROOT}/PLAW/{congress}/public/PLAW-{congress}publ{number}.xml"


def congress_zip_url(congress: int) -> str:
    return f"{BULK_ROOT}/PLAW/{congress}/public/PLAW-{congress}-public.zip"


def zip_path(congress: int, directory: Path = DATA_DIR) -> Path:
    return Path(directory) / f"PLAW-{congress}-public.zip"


# -------------------------------------------------------------------- parsing


def parse_plaw(xml_text: str, *, package: str | None = None) -> LawRecord:
    """One bulk-data file → a `LawRecord` with GPO's identifiers.

    `package` is the file's package id (`PLAW-118publ22`), used when the
    file's own `meta` is short of a number.
    """
    root = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    if local_name(root) != "pLaw":
        raise ValueError(f"not a pLaw document: root is {local_name(root)}")
    meta = root.find(f"{N}meta")
    if meta is None:
        raise ValueError("no meta element")
    warnings: list[str] = []

    from_name = parse_package_id(package or "")
    doc_type = (meta.findtext(f"{DC}type") or "").strip().lower()
    public_private = (meta.findtext(f"{N}publicPrivate") or "").strip().lower()
    if public_private == "private" or doc_type == "private law":
        kind = "pvtl"
    elif public_private == "public" or doc_type == "public law":
        kind = "pl"
    elif from_name is not None:
        kind = from_name[1]
    else:
        raise ValueError("neither publicPrivate nor dc:type says public or private")
    congress = parse_doc_number(meta.findtext(f"{N}congress"))
    number = parse_doc_number(meta.findtext(f"{N}docNumber"))
    if from_name is not None:
        if congress is None:
            congress = from_name[0]
        if number is None:
            number = from_name[2]
        if (congress, kind, number) != from_name:
            warnings.append(f"meta says {kind} {congress}-{number}; the package id is {package}")
    if congress is None or number is None:
        raise ValueError("no congress or docNumber in meta")
    identifier = f"/us/{kind}/{congress}/{number}"
    package = package or package_id(congress, number, kind)

    enacted = _date(meta.findtext(f"{N}approvedDate"))
    if enacted is None:
        approved = root.find(f".//{N}approvedDate")
        if approved is not None:
            enacted = _date(approved.get("date"))

    citation, volume, first_page, last_page = _pages_of(meta, root, warnings)

    long_title = root.find(f".//{N}longTitle")
    official_title = None
    if long_title is not None:
        ot = long_title.find(f"{N}officialTitle")
        if ot is not None:
            official_title = plain_text(ot)
    if not official_title:
        title = meta.findtext(f"{DC}title")
        official_title = _LEADING_LAW.sub("", " ".join(title.split())) if title else None
    doc_title = root.find(f".//{N}docTitle")
    doc_kind = _doc_kind(plain_text(doc_title) if doc_title is not None else None)

    main = root.find(f"{N}main")
    units: list[UnitRecord] = []
    page_units: dict[str, str | None] = {}
    assigned: collections.Counter[str] = collections.Counter()
    quoted = 0
    if main is None:
        warnings.append("no main element")
    else:
        units, page_units, quoted, assigned = _walk_units(root, main, identifier, warnings, first_page)
    short_titles = _short_titles(main) if main is not None else []
    for label in _all_pages(root):
        page_units.setdefault(label, None)
    if first_page is not None:
        page_units.setdefault(first_page, None)

    xml = serialize(root)
    record = LawRecord(
        identifier=identifier,
        kind=kind,
        congress=congress,
        number=number,
        chapter=None,
        enacted=enacted,
        doc_type=doc_kind,
        official_title=official_title,
        short_titles=short_titles,
        stat_volume=volume,
        stat_page_first=first_page,
        stat_page_last=last_page,
        citation=citation,
        source_package=package,
        seq_in_volume=number,
        xml=xml,
        content_hash=content_hash(xml),
        aliases=[identifier],
        units=units,
        page_units=page_units,
        warnings=warnings,
        source_collection=COLLECTION,
        provenance_identifiers=MIXED_PROVENANCE if assigned else IDENTIFIER_PROVENANCE,
        identifiers_assigned=dict(assigned),
        sections_in_quoted_content=quoted,
    )
    return record


def _pages_of(meta: etree._Element, root: etree._Element, warnings: list[str]) -> tuple[str | None, int, str | None, str | None]:
    """(`137 Stat. 112`, 137, first page label, last page label).

    The volume comes from `citableAs`, checked against the running head the
    file carries as a processing instruction (`<?I97 137 STAT. ?>`); when the
    two disagree the running head wins (three files of the 116th to 118th
    Congresses cite `131 Stat.` under a `134 STAT.` running head). With no
    `citableAs` naming a Stat. page, the running head alone; else the first
    page marker.
    """
    citation = None
    cited_volume: int | None = None
    first = None
    page_text = None
    for citable in meta.findall(f"{N}citableAs"):
        match = _STAT_CITE.search(citable.text or "")
        if match:
            cited_volume = int(match.group("volume"))
            page_text = match.group("page")
            first = "".join(page_text.split()).lower()
            break
    head_volume: int | None = None
    for node in root.iter():
        if isinstance(node, etree._ProcessingInstruction) and node.target in ("I97", "I98", "I99"):
            match = _STAT_PI.search(node.text or "")
            if match:
                head_volume = int(match.group("volume"))
                break
    volume = cited_volume
    if cited_volume is not None and head_volume is not None and head_volume != cited_volume:
        warnings.append(f"citableAs says {cited_volume} Stat.; the running head says {head_volume} STAT. and is used")
        volume = head_volume
    elif cited_volume is None and head_volume is not None:
        volume = head_volume
        warnings.append("Stat. volume taken from the running-head instruction")
    pages = _all_pages(root)
    if volume is None:
        for page in root.iter(f"{N}page"):
            match = re.match(r"^/us/stat/(\d+)/", (page.get("identifier") or "").strip())
            if match:
                volume = int(match.group(1))
                warnings.append("Stat. volume taken from a page marker")
                break
    if volume is None:
        raise ValueError("no Statutes at Large volume in citableAs, running heads, or page markers")
    if first is not None:
        citation = f"{volume} Stat. {page_text}"
    elif pages:
        first = pages[0]
        citation = f"{volume} Stat. {first}"
        warnings.append("citation taken from the first page marker")
    last = pages[-1] if pages else first
    return citation, volume, first, last


def _walk_units(
    root: etree._Element,
    main: etree._Element,
    law_identifier: str,
    warnings: list[str],
    first_page: str | None,
) -> tuple[list[UnitRecord], dict[str, str | None], int, collections.Counter[str]]:
    """Collect the unit elements by GPO's identifiers, filling in by rule where
    a level has none. The page cursor runs over the whole document (the
    preface carries the first page marker)."""
    current_page: str | None = first_page
    unit_elements: list[tuple[etree._Element, str, str, str | None, str | None, int, str | None]] = []
    page_units: dict[str, str | None] = {}
    occurrences: collections.Counter[str] = collections.Counter()
    assigned: collections.Counter[str] = collections.Counter()
    quoted_sections = 0
    section_seen = False
    unnumbered_first: etree._Element | None = None
    in_main = False

    for element in root.iter():
        name = local_name(element)
        if name is None:
            continue
        if element is main:
            in_main = True
        if name == "page":
            label = page_label(element.get("identifier"))
            if label:
                current_page = label
                page_units[label] = _enclosing_unit(element, main)
            continue
        if not in_main or element is main:
            continue
        if _inside_skipped(element, main):
            if name == "section":
                quoted_sections += 1
            continue
        if name not in IDENTIFIED_LEVELS:
            continue

        identifier = (element.get("identifier") or "").strip()
        value = _designator_of(element, name)
        if identifier:
            if not identifier.startswith(law_identifier + "/"):
                warnings.append(f"{identifier} is not under {law_identifier}; kept as written")
            from_segment = _value_of_segment(identifier.rsplit("/", 1)[-1], name)
            value = from_segment or value
        else:
            if name == "section" and value is None:
                if not section_seen and unnumbered_first is None:
                    # The first section of an act is enacted without a number
                    # and cited as section 1 (CLAUDE.md gotcha 4).
                    value = "1"
                    unnumbered_first = element
                else:
                    warnings.append("section without a number after the first; not addressable")
                    continue
            elif value is None:
                continue
            parent = _parent_identifier(element, main) or law_identifier
            identifier = f"{parent}/{segment(name, value)}"
            element.set("identifier", identifier)
            assigned[name] += 1
        if name == "section":
            section_seen = True
        if name in SUBSECTION_LEVELS:
            continue
        occurrences[identifier] += 1
        occurrence = occurrences[identifier]
        if occurrence > 1:
            warnings.append(f"{identifier} occurs {occurrence} times")
        unit_elements.append((element, identifier, name, value, _heading_of(element), occurrence, current_page))

    units: list[UnitRecord] = []
    for seq, (element, identifier, level, value, heading, occurrence, page) in enumerate(unit_elements, start=1):
        ancestors = _ancestor_units(element, main)
        if level == "section":
            xml = serialize(element)
            text = plain_text(element)
            digest = content_hash(xml)
        else:
            xml, text, digest = None, None, None
        pages = [
            label
            for label in (page_label(p.get("identifier")) for p in element.iter(f"{N}page"))
            if label
        ]
        units.append(
            UnitRecord(
                identifier=identifier,
                occurrence=occurrence,
                parent_identifier=ancestors[-1]["identifier"] if ancestors else None,
                level=level,
                num=value,
                heading=heading,
                section_num=value if level == "section" else None,
                seq=seq,
                depth=len(ancestors) + 1,
                ancestors=ancestors,
                xml=xml,
                text=text,
                content_hash=digest,
                first_page=page,
                pages=pages,
            )
        )
    return units, page_units, quoted_sections, assigned


def _value_of_segment(segment_text: str, level: str) -> str | None:
    """`s101` → `101` for a section, `tI` → `I` for a title, `a` → `a` below
    a section; None when the segment does not carry the level's prefix."""
    prefix = LEVEL_PREFIX.get(level)
    if prefix is None:
        return segment_text or None
    if segment_text.startswith(prefix) and len(segment_text) > len(prefix):
        return segment_text[len(prefix):]
    return None


# ----------------------------------------------------------------- comparing


def identifiers_by_level(xml: str) -> dict[str, set[str]]:
    """Every `@identifier` on a hierarchy node, section, or level below a
    section in the law's `main`, outside quoted content and apparatus, keyed
    by element name."""
    root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    main = root.find(f"{N}main")
    out: dict[str, set[str]] = collections.defaultdict(set)
    if main is None:
        return {}
    for element in main.iter():
        name = local_name(element)
        if name is None or name not in IDENTIFIED_LEVELS:
            continue
        if _inside_skipped(element, main):
            continue
        identifier = (element.get("identifier") or "").strip()
        if identifier:
            out[name].add(identifier)
    return dict(out)


def compare_identifiers(volume_xml: str, plaw_xml: str) -> dict:
    """Per level: how many identifiers the rules-1.0 stamping and GPO's file
    agree on, and the ones each has alone."""
    rules = identifiers_by_level(volume_xml)
    gpo = identifiers_by_level(plaw_xml)
    by_level: dict[str, dict] = {}
    for level in sorted(set(rules) | set(gpo), key=_level_order):
        a, b = rules.get(level, set()), gpo.get(level, set())
        by_level[level] = {
            "agree": len(a & b),
            "rules_only": sorted(a - b),
            "gpo_only": sorted(b - a),
        }
    return by_level


def _level_order(level: str) -> int:
    order = list(HIERARCHY_LEVELS) + ["section"] + list(SUBSECTION_LEVELS)
    return order.index(level) if level in order else len(order)


# -------------------------------------------------------------------- loading


@dataclass(slots=True)
class PlawLawReport:
    package: str
    identifier: str
    action: str
    """`new` | `replaced_statute` | `replaced_plaw`."""
    citation: str | None
    units: int
    sections: int
    sections_in_quoted_content_skipped: int
    identifiers_assigned: dict[str, int]
    provenance_identifiers: str
    stat_pages: int
    comparison: dict | None = None
    """Per level, the identifier agreement with the volume-derived copy this
    load replaced; None when no such copy was stored."""
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlawLoadReport:
    congress: int
    source: str
    source_sha256: str | None
    loaded_at: str
    seconds: float = 0.0
    files: int = 0
    laws_loaded: int = 0
    laws_new: int = 0
    laws_replaced_statute: int = 0
    laws_replaced_plaw: int = 0
    laws_failed: int = 0
    units: int = 0
    units_by_level: dict[str, int] = field(default_factory=dict)
    sections: int = 0
    sections_in_quoted_content_skipped: int = 0
    duplicate_section_identifiers: int = 0
    stat_pages: int = 0
    stat_volumes: list[int] = field(default_factory=list)
    identifiers_assigned: dict[str, int] = field(default_factory=dict)
    """Per level, identifiers the rules filled in because the file had none."""
    laws_with_assigned_identifiers: list[str] = field(default_factory=list)
    provenance: dict[str, int] = field(default_factory=dict)
    """Laws per `provenance_identifiers` value."""
    comparison: dict = field(default_factory=dict)
    """`laws_compared`, `by_level` totals (`agree`, `rules_only`, `gpo_only`),
    and `laws`: each compared law whose identifiers differed, with the
    differing identifiers per level."""
    warnings: dict[str, int] = field(default_factory=dict)
    failures: list[dict] = field(default_factory=list)
    identifier_provenance: str = IDENTIFIER_PROVENANCE
    identifier_rules: str = _RULES
    first_law: str | None = None
    last_law: str | None = None


def load_plaw(
    session: Session, record: LawRecord, *, now: datetime.datetime | None = None, volume_xml: str | None = None
) -> PlawLawReport:
    """Write one law, replacing a stored copy from either collection, and
    compare identifiers with the volume-derived copy: the one replaced, or
    `volume_xml` (the law as the volume file parses it) when the caller has
    it. Does not commit."""
    from ingest.load import _write_law

    now = now or datetime.datetime.now(datetime.timezone.utc)
    outcome = _write_law(session, record, now)
    action = "new"
    comparison = None
    if outcome.action == "replaced":
        action = "replaced_statute" if outcome.replaced_from == "STATUTE" else "replaced_plaw"
    elif outcome.action == "kept":  # cannot happen: PLAW outranks every other source
        raise RuntimeError(f"{record.identifier}: a {outcome.replaced_from} copy outranks the PLAW file")
    rules_xml = outcome.replaced_xml if outcome.replaced_from == "STATUTE" else volume_xml
    if rules_xml:
        comparison = compare_identifiers(rules_xml, record.xml)
    return PlawLawReport(
        package=record.source_package,
        identifier=record.identifier,
        action=action,
        citation=record.citation,
        units=len(record.units),
        sections=len(record.sections),
        sections_in_quoted_content_skipped=record.sections_in_quoted_content,
        identifiers_assigned=dict(record.identifiers_assigned),
        provenance_identifiers=record.provenance_identifiers,
        stat_pages=len(record.page_units),
        comparison=comparison,
        warnings=list(record.warnings),
    )


def load_plaw_file(session: Session, path: Path | str, *, now: datetime.datetime | None = None) -> PlawLawReport:
    """Parse and load one file; commits."""
    path = Path(path)
    parsed = parse_package_id(path.name)
    record = parse_plaw(path.read_text(encoding="utf-8"), package=f"PLAW-{parsed[0]}{'publ' if parsed[1] == 'pl' else 'pvtl'}{parsed[2]}" if parsed else None)
    report = load_plaw(session, record, now=now)
    session.commit()
    return report


def iter_zip(path: Path) -> Iterator[tuple[str, str]]:
    """(`PLAW-118publ22.xml`, text) for every law file in a per-congress zip,
    in law-number order."""
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if _FILE_NAME.search(Path(n).name)]
        for name in sorted(names, key=_file_order):
            yield Path(name).name, archive.read(name).decode("utf-8")


def iter_directory(path: Path) -> Iterator[tuple[str, str]]:
    files = [p for p in Path(path).iterdir() if _FILE_NAME.search(p.name)]
    for file in sorted(files, key=lambda p: _file_order(p.name)):
        yield file.name, file.read_text(encoding="utf-8")


def _file_order(name: str) -> tuple[int, int, int]:
    parsed = parse_package_id(Path(name).name)
    if parsed is None:
        return (0, 0, 0)
    return parsed[0], 0 if parsed[1] == "pl" else 1, parsed[2]


class VolumeIndex:
    """The volume files on disk, parsed lazily, one at a time, into the
    rules-1.0 XML of each law, so a re-load can still compare identifiers
    after the volume-derived copy is gone from the database."""

    def __init__(self, directory: Path | None):
        self.directory = Path(directory) if directory else None
        self._laws: dict[int, dict[str, str]] = {}

    def xml_for(self, identifier: str, volume: int) -> str | None:
        if self.directory is None:
            return None
        if volume not in self._laws:
            path = self.directory / f"STATUTE-{volume}.xml"
            laws: dict[str, str] = {}
            if path.exists():
                from ingest.numbering import plan_numbering
                from ingest.statute import iter_claims, iter_volume

                plan = plan_numbering(list(iter_claims(path)))
                for item in iter_volume(path, plan):
                    if isinstance(item, LawRecord):
                        laws.setdefault(item.identifier, item.xml)
            self._laws[volume] = laws
        return self._laws[volume].get(identifier)


def load_congress(
    session: Session,
    congress: int,
    *,
    zip_file: Path | None = None,
    directory: Path | None = None,
    files: Iterator[tuple[str, str]] | None = None,
    volumes_dir: Path | None = None,
    record_check: bool = True,
) -> PlawLoadReport:
    """Load every public law of a congress from its bulk-data zip, a directory
    of files, or an iterator of (name, text). Commits every `COMMIT_EVERY`
    laws and writes a `source_checks` row with collection `PLAW`.

    `volumes_dir` names the downloaded volume files; when given, every law
    the volume file also holds is compared, whether or not a volume-derived
    copy was in the database."""
    started = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    volumes_on_disk = VolumeIndex(volumes_dir)
    if files is None:
        if zip_file is not None:
            files = iter_zip(Path(zip_file))
            source, sha = str(zip_file), _sha256(Path(zip_file))
        elif directory is not None:
            files = iter_directory(Path(directory))
            source, sha = str(directory), None
        else:
            raise ValueError("give zip_file, directory, or files")
    else:
        source, sha = "files", None
    report = PlawLoadReport(congress=congress, source=source, source_sha256=sha, loaded_at=now.isoformat())
    levels: collections.Counter[str] = collections.Counter()
    assigned: collections.Counter[str] = collections.Counter()
    provenance: collections.Counter[str] = collections.Counter()
    warnings: collections.Counter[str] = collections.Counter()
    totals: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    compared: list[dict] = []
    laws_compared = 0
    volumes: set[int] = set()
    new_packages: list[str] = []
    newest: tuple[int, int] | None = None
    newest_package: str | None = None
    pending = 0

    for name, text in files:
        report.files += 1
        parsed = parse_package_id(name)
        if parsed is not None and parsed[0] != congress:
            report.failures.append({"file": name, "error": f"belongs to the {parsed[0]}th Congress"})
            report.laws_failed += 1
            continue
        package = package_id(*(parsed[0], parsed[2], parsed[1])) if parsed else None
        try:
            record = parse_plaw(text, package=package)
            law = load_plaw(
                session, record, now=now,
                volume_xml=volumes_on_disk.xml_for(record.identifier, record.stat_volume),
            )
        except Exception as exc:  # one bad file must not end the load
            session.rollback()
            report.laws_failed += 1
            report.failures.append({"file": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        report.laws_loaded += 1
        if law.action == "new":
            report.laws_new += 1
            new_packages.append(law.package)
        elif law.action == "replaced_statute":
            report.laws_replaced_statute += 1
            new_packages.append(law.package)
        else:
            report.laws_replaced_plaw += 1
        report.units += law.units
        report.sections += law.sections
        report.sections_in_quoted_content_skipped += law.sections_in_quoted_content_skipped
        report.stat_pages += law.stat_pages
        report.duplicate_section_identifiers += sum(1 for u in record.units if u.level == "section" and u.occurrence > 1)
        volumes.add(record.stat_volume)
        for unit in record.units:
            levels[unit.level] += 1
        for level, count in law.identifiers_assigned.items():
            assigned[level] += count
        if law.identifiers_assigned:
            report.laws_with_assigned_identifiers.append(law.identifier)
        provenance[law.provenance_identifiers] += 1
        for warning in law.warnings:
            key = warning.split(" ", 1)[-1] if warning.startswith("/") else warning
            warnings[key] += 1
        if law.comparison is not None:
            laws_compared += 1
            differs = {}
            for level, counts in law.comparison.items():
                totals[level]["agree"] += counts["agree"]
                totals[level]["rules_only"] += len(counts["rules_only"])
                totals[level]["gpo_only"] += len(counts["gpo_only"])
                if counts["rules_only"] or counts["gpo_only"]:
                    differs[level] = {"rules_only": counts["rules_only"], "gpo_only": counts["gpo_only"]}
            if differs:
                compared.append({"identifier": law.identifier, "by_level": differs})
        key = (record.congress or 0, record.number or 0)
        if newest is None or key > newest:
            newest, newest_package = key, law.package
        report.first_law = report.first_law or law.identifier
        report.last_law = law.identifier
        pending += 1
        if pending >= COMMIT_EVERY:
            session.commit()
            pending = 0

    report.units_by_level = dict(levels)
    report.identifiers_assigned = dict(assigned)
    report.provenance = dict(provenance)
    report.stat_volumes = sorted(volumes)
    report.warnings = dict(warnings.most_common())
    report.comparison = {
        "laws_compared": laws_compared,
        "by_level": {level: dict(totals[level]) for level in sorted(totals, key=_level_order)},
        "laws": compared,
    }
    if record_check:
        error = None
        if report.failures:
            error = f"{report.laws_failed} file(s) failed: " + "; ".join(
                f"{f['file']}: {f['error']}" for f in report.failures[:10]
            )
        session.add(
            SourceCheck(
                collection=COLLECTION,
                checked_at=now,
                ok=True,
                newest_last_modified=None,
                newest_package=newest_package,
                packages_seen=report.files,
                new_packages=new_packages,
                error=error,
            )
        )
    session.commit()
    report.seconds = round(time.monotonic() - started, 1)
    return report


def write_report(report: PlawLoadReport, directory: Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"plaw-{report.congress}.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n")
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------- fetching


def fetch_congress_zip(congress: int, directory: Path = DATA_DIR, *, force: bool = False) -> Path:
    """Download `PLAW-{c}-public.zip` into `directory`, skipping a file already
    there. No key: bulk data is open."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = zip_path(congress, directory)
    if target.exists() and not force:
        return target
    partial = target.with_suffix(".zip.part")
    with httpx.stream(
        "GET", congress_zip_url(congress), follow_redirects=True, timeout=300.0,
        headers={"User-Agent": USER_AGENT},
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    partial.replace(target)
    return target


# --------------------------------------------------------------- command line


def _congresses(values: list[str]) -> list[int]:
    out: list[int] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                out.extend(range(int(lo), int(hi) + 1))
            elif part:
                out.append(int(part))
    return out


def _print_load(report: PlawLoadReport) -> None:
    print(
        f"PLAW {report.congress}: {report.laws_loaded} laws ({report.laws_new} new, "
        f"{report.laws_replaced_statute} replaced volume-derived, {report.laws_replaced_plaw} re-loaded), "
        f"{report.units} units, {report.sections} sections, {report.stat_pages} pages, "
        f"{sum(report.identifiers_assigned.values())} identifiers assigned by rule in "
        f"{len(report.laws_with_assigned_identifiers)} laws, {report.laws_failed} failed, {report.seconds}s"
    )
    comparison = report.comparison
    if comparison.get("laws_compared"):
        parts = [
            f"{level} {c['agree']} agree / {c['rules_only']} rules-only / {c['gpo_only']} gpo-only"
            for level, c in comparison["by_level"].items()
        ]
        print(f"  compared with the volume copy of {comparison['laws_compared']} laws: " + "; ".join(parts))
    for failure in report.failures[:10]:
        print(f"  failed {failure['file']}: {failure['error']}", file=sys.stderr)


def cmd_fetch(args: argparse.Namespace) -> int:
    for congress in _congresses(args.congresses):
        path = fetch_congress_zip(congress, Path(args.dir), force=args.force)
        print(f"{congress}\t{path}\t{path.stat().st_size} bytes")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    from db.base import SessionLocal

    failures = 0
    reports: list[PlawLoadReport] = []
    if args.from_dir:
        directory = Path(args.from_dir)
        by_congress: dict[int, list[Path]] = collections.defaultdict(list)
        for path in directory.iterdir():
            parsed = parse_package_id(path.name)
            if parsed is not None and path.suffix.lower() == ".xml":
                by_congress[parsed[0]].append(path)
        wanted = set(_congresses(args.congresses)) if args.congresses else set(by_congress)
        for congress in sorted(wanted):
            paths = sorted(by_congress.get(congress, []), key=lambda p: _file_order(p.name))
            if not paths:
                print(f"{congress}: no PLAW files in {directory}", file=sys.stderr)
                failures += 1
                continue
            files = ((p.name, p.read_text(encoding="utf-8")) for p in paths)
            with SessionLocal() as session:
                report = load_congress(session, congress, files=files, volumes_dir=_volumes_dir(args))
            report.source = str(directory)
            reports.append(report)
    else:
        if not args.congresses:
            print("give congresses (`118`, `113-119`) or --from-dir", file=sys.stderr)
            return 2
        for congress in _congresses(args.congresses):
            path = fetch_congress_zip(congress, Path(args.dir))
            with SessionLocal() as session:
                try:
                    report = load_congress(session, congress, zip_file=path, volumes_dir=_volumes_dir(args))
                except Exception as exc:  # one bad congress must not stop the run
                    session.rollback()
                    failures += 1
                    print(f"{congress}: FAILED {exc!r}", file=sys.stderr)
                    continue
            reports.append(report)
    for report in reports:
        _print_load(report)
        if report.laws_failed:
            failures += 1
        if args.report:
            target = write_report(report, Path(args.report))
            print(f"  report {target}")
        if args.json:
            print(json.dumps(asdict(report), indent=2))
    return 1 if failures else 0


def _volumes_dir(args: argparse.Namespace) -> Path | None:
    """`--volumes-dir` when given; else the default directory when it exists."""
    if args.volumes_dir:
        return Path(args.volumes_dir)
    default = Path("data/statute/xmls")
    return default if default.is_dir() else None


def add_plaw_commands(sub: argparse._SubParsersAction) -> argparse._SubParsersAction:
    """Register `plaw fetch` and `plaw load`; returns the inner subparsers so
    the poller (`ingest/plaw_poll.py`) can add `plaw poll`."""
    plaw = sub.add_parser("plaw", help="GovInfo PLAW bulk data: fetch, load, poll")
    inner = plaw.add_subparsers(dest="plaw_command", required=True)

    fetch = inner.add_parser("fetch", help="download the per-congress zip of public laws")
    fetch.add_argument("congresses", nargs="+", help="`118`, `118 119`, or `113-119`")
    fetch.add_argument("--dir", default=str(DATA_DIR))
    fetch.add_argument("--force", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    load = inner.add_parser("load", help="load public laws from the per-congress zip or a directory of files")
    load.add_argument("congresses", nargs="*", help="`118`, `118 119`, or `113-119`")
    load.add_argument("--dir", default=str(DATA_DIR), help="where the zips are (fetched when missing)")
    load.add_argument("--from-dir", help="a directory of PLAW-{c}publ{n}.xml files instead of the zips")
    load.add_argument("--volumes-dir", help="downloaded STATUTE volumes to compare identifiers against (default data/statute/xmls when present)")
    load.add_argument("--report", help="directory for the per-congress JSON report")
    load.add_argument("--json", action="store_true", help="print the report")
    load.set_defaults(func=cmd_load)
    return inner
