"""STATUTE volume USLM → law and unit records, with identifiers assigned by rule.

One GovInfo volume file (`STATUTE-{n}.xml`, root `statutesAtLarge`) holds every
document of a Statutes at Large volume as a `component`. The ones this loader
keeps are the `pLaw` components: public laws, private laws, and joint
resolutions. Concurrent resolutions (`resolution`), proclamations and treaties
(`presidentialDoc`), and part prefaces are counted and skipped.

The volume USLM carries no `@identifier` on any level. This module stamps one on
every division, title, chapter, section, subsection, paragraph and so on, by the
rules in `ingest/identifiers.py`, before the fragments are serialized — so the
stored XML is GPO's text with identifiers added (`provenance_identifiers =
"rules-1.0"`).

Sections are the storage atom. A `UnitRecord` is emitted for every hierarchy
node and every section outside `quotedContent`; levels below a section are
stamped and travel inside the section's XML.
"""

from __future__ import annotations

import collections
import datetime
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from ingest.identifiers import (
    HIERARCHY_LEVELS,
    SUBSECTION_LEVELS,
    designator,
    identify_law,
    segment,
)
from uslmtext import USLM_NS, content_hash, local_name, plain_text, serialize

if False:  # imported for type names only
    from ingest.numbering import Claim, NumberingPlan

N = f"{{{USLM_NS}}}"
DC = "{http://purl.org/dc/elements/1.1/}"

IDENTIFIER_RULES_VERSION = "rules-1.0"
TEXT_PROVENANCE = "gpo-uslm"

#: Subtrees in which nothing is a unit of *this* law: quoted text of another
#: act, tables of contents, marginal notes, footnotes.
SKIP_SUBTREES = frozenset({"quotedContent", "toc", "sidenote", "footnote", "note"})

_STAT_CITE = re.compile(r"(?P<volume>\d+)\s*Stat\.?\s*(?P<page>[0-9A-Za-z]+(?:-\d+)?)", re.IGNORECASE)
_PAGE_ID = re.compile(r"^/us/stat/(?P<volume>\d+)/(?P<page>[^/@]+)")
_LEADING_LAW = re.compile(r"^(?:Public|Private)\s+Law\s+[\d–-]+:\s*", re.IGNORECASE)
_PREFACE_CHAPTER = re.compile(r"\bchapter\s+(\d+)", re.IGNORECASE)


@dataclass(slots=True)
class UnitRecord:
    identifier: str
    occurrence: int
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
    first_page: str | None
    pages: list[str]


@dataclass(slots=True)
class LawRecord:
    identifier: str
    kind: str
    congress: int | None
    number: int | None
    chapter: int | None
    enacted: datetime.date | None
    doc_type: str | None
    official_title: str | None
    short_titles: list[str]
    stat_volume: int
    stat_page_first: str | None
    stat_page_last: str | None
    citation: str | None
    source_package: str
    seq_in_volume: int
    xml: str
    content_hash: str
    aliases: list[str]
    units: list[UnitRecord]
    page_units: dict[str, str | None]
    """Page label → identifier of the unit the page marker falls in (None when
    it falls outside every unit)."""
    warnings: list[str] = field(default_factory=list)
    source_collection: str = "STATUTE"
    """`STATUTE` (a volume file) or `PLAW` (a GovInfo public-law package)."""
    provenance_identifiers: str = IDENTIFIER_RULES_VERSION
    """`rules-1.0` when this module assigned every identifier; `gpo-uslm` when
    the source carried them (`ingest/plaw.py`); `gpo-uslm+rules-1.0` when a
    PLAW file left some levels unidentified and the rules filled them in."""
    identifiers_assigned: dict[str, int] = field(default_factory=dict)
    """Per level, how many identifiers were assigned by rule rather than read
    from the source. Empty for a volume law, where every one is assigned."""
    sections_in_quoted_content: int = 0
    """`<section>` elements inside `quotedContent`, kept in the XML and not
    units. The volume parser counts these on `VolumeParse` instead."""

    @property
    def sections(self) -> list[UnitRecord]:
        return [u for u in self.units if u.level == "section"]


@dataclass(slots=True)
class SkippedComponent:
    seq: int
    root: str | None
    doc_type: str | None
    doc_number: str | None
    reason: str


@dataclass(slots=True)
class VolumeParse:
    volume: int
    package: str
    components: int = 0
    laws: list[LawRecord] = field(default_factory=list)
    skipped: list[SkippedComponent] = field(default_factory=list)
    sections_in_quoted_content: int = 0
    merged_components: int = 0
    """Components holding more than one `pLaw` (vol 116 packs 47 laws into one)."""

    @property
    def skipped_by_reason(self) -> dict[str, int]:
        return dict(collections.Counter(s.reason for s in self.skipped))


def volume_number(path: Path, root: etree._Element | None = None) -> int:
    """From `meta/volume`, else from the file name `STATUTE-64.xml`."""
    if root is not None:
        text = root.findtext(f"{N}meta/{N}volume")
        if text and text.strip().isdigit():
            return int(text.strip())
    match = re.search(r"statute-(\d+)", path.name, re.IGNORECASE)
    if not match:
        # `meta/volume` inside the file sets it as the stream starts.
        return 0
    return int(match.group(1))


def iter_claims(path: Path) -> Iterator["Claim"]:
    """The light pass: every law's identity and citation, no units, no XML.
    What `ingest.numbering.plan_numbering` decides collisions from."""
    from ingest.numbering import Claim

    path = Path(path)
    volume = volume_number(path)
    seq = 0
    for _event, element in etree.iterparse(str(path), events=("end",)):
        name = local_name(element)
        if name == "meta":
            parent = element.getparent()
            if parent is not None and local_name(parent) == "statutesAtLarge":
                text = element.findtext(f"{N}volume")
                if text and text.strip().isdigit():
                    volume = int(text.strip())
            continue
        if name != "component":
            continue
        if element.get("role") is not None:
            element.clear()
            continue
        try:
            for plaw in _plaws(element):
                seq += 1
                found = _identity_of(plaw)
                if found is None:
                    continue
                identity, meta = found
                citation, _first, _last = _pages_of(meta, plaw, volume)
                title = meta.findtext(f"{DC}title")
                yield Claim(
                    seq=seq,
                    kind=identity.kind,
                    number=identity.number,
                    primary=identity.primary,
                    chapter_form=next((a for a in identity.aliases if a.startswith("/us/act/")), None),
                    citation=citation,
                    title=" ".join(title.split())[:80] if title else None,
                )
            if not _plaws(element):
                seq += 1
        finally:
            element.clear()
            parent = element.getparent()
            if parent is not None:
                while element.getprevious() is not None:
                    del parent[0]


def parse_volume(path: Path) -> VolumeParse:
    """Every law of a volume, in one pass, with the counts a report needs."""
    result: VolumeParse | None = None
    for item in iter_volume(path):
        if isinstance(item, VolumeParse):
            result = item
        elif isinstance(item, LawRecord):
            assert result is not None
            result.laws.append(item)
    assert result is not None
    return result


def iter_volume(path: Path, plan: "NumberingPlan | None" = None) -> Iterator[VolumeParse | LawRecord]:
    """Stream a volume: first the (initially empty) `VolumeParse` header, then one
    `LawRecord` per law. The header's counters are filled in as laws stream, so
    the caller that keeps it sees the final totals at the end.

    Streaming, because Title-42-sized volumes exist (vol 124 is 31 MB) and a
    whole tree of one is several times that in memory.
    """
    path = Path(path)
    volume = volume_number(path)
    header = VolumeParse(volume=volume, package=f"STATUTE-{volume}")
    yield header
    context = etree.iterparse(str(path), events=("end",))
    seq = 0
    for _event, element in context:
        name = local_name(element)
        if name == "meta":
            parent = element.getparent()
            if parent is not None and local_name(parent) == "statutesAtLarge":
                text = element.findtext(f"{N}volume")
                if text and text.strip().isdigit():
                    header.volume = int(text.strip())
                    header.package = f"STATUTE-{header.volume}"
            continue
        if name != "component":
            continue
        if element.get("role") is not None:
            # A statutesPart wrapper: its law components were handled as they
            # ended. Drop what is left of it.
            element.clear()
            continue
        header.components += 1
        try:
            plaws = _plaws(element)
            if not plaws:
                seq += 1
                header.skipped.append(_skipped_component(element, seq))
                continue
            if len(plaws) > 1:
                header.merged_components += 1
            for plaw in plaws:
                seq += 1
                law, quoted, skipped = _parse_law(plaw, header.volume, header.package, seq, plan)
                header.sections_in_quoted_content += quoted
                if skipped is not None:
                    header.skipped.append(skipped)
                if law is not None:
                    yield law
        finally:
            element.clear()
            parent = element.getparent()
            if parent is not None:
                while element.getprevious() is not None:
                    del parent[0]


def _plaws(component: etree._Element) -> list[etree._Element]:
    """Every `pLaw` directly under a component. Usually one; some born-digital
    volumes pack a run of consecutive laws into one component."""
    return [c for c in component if isinstance(c.tag, str) and local_name(c) == "pLaw"]


def _skipped_component(component: etree._Element, seq: int) -> SkippedComponent:
    children = [c for c in component if isinstance(c.tag, str)]
    root_name = local_name(children[0]) if children else None
    meta = component.find(f".//{N}meta")
    doc_type = meta.findtext(f"{DC}type") if meta is not None else None
    doc_number = meta.findtext(f"{N}docNumber") if meta is not None else None
    reason = {"resolution": "concurrent resolution", "presidentialDoc": "presidential document",
              "preface": "part preface"}.get(root_name or "", f"unhandled root {root_name}")
    return SkippedComponent(seq, root_name, doc_type, doc_number, reason)


def _identity_of(plaw: etree._Element):
    """(LawIdentity, meta) for a `pLaw` element, else None."""
    meta = plaw.find(f"{N}meta")
    if meta is None:
        return None
    doc_type = meta.findtext(f"{DC}type")
    doc_number = meta.findtext(f"{N}docNumber")
    congress = _int(meta.findtext(f"{N}congress"))
    public_private = (meta.findtext(f"{N}publicPrivate") or "").strip().lower() or None
    enacted = _date(meta.findtext(f"{N}approvedDate"))
    if enacted is None:
        approved = plaw.find(f".//{N}approvedDate")
        if approved is not None:
            enacted = _date(approved.get("date"))
    long_title = plaw.find(f".//{N}longTitle")
    # The law number is read from the marginal note beside the long title,
    # never from the title itself: "To extend the Rubber Act of 1948 (Public
    # Law 469, Eightieth Congress)" names another law.
    notes = list(long_title.iter(f"{N}sidenote")) if long_title is not None else []
    long_title_text = " ".join(plain_text(n, skip=frozenset()) for n in notes)
    hrefs = [r.get("href", "") for n in notes for r in n.iter(f"{N}ref")]
    preface = plaw.find(f"{N}preface")
    preface_chapter = None
    if preface is not None:
        match = _PREFACE_CHAPTER.search(plain_text(preface, skip=frozenset({"page"})))
        if match:
            preface_chapter = int(match.group(1))
    identity = identify_law(
        congress=congress,
        doc_type=doc_type,
        doc_number=doc_number,
        public_private=public_private,
        enacted=enacted,
        long_title_text=long_title_text,
        long_title_hrefs=hrefs,
        preface_chapter=preface_chapter,
    )
    if identity is None:
        return None
    return identity, meta


def _parse_law(
    root: etree._Element, volume: int, package: str, seq: int, plan: "NumberingPlan | None" = None
) -> tuple[LawRecord | None, int, SkippedComponent | None]:
    """One `pLaw` element → a LawRecord, or a SkippedComponent saying why not."""
    meta = root.find(f"{N}meta")
    doc_type = meta.findtext(f"{DC}type") if meta is not None else None
    doc_number = meta.findtext(f"{N}docNumber") if meta is not None else None
    found = _identity_of(root)
    if found is None:
        return None, 0, SkippedComponent(seq, "pLaw", doc_type, doc_number, "unidentified law")
    identity, meta = found
    congress = _int(meta.findtext(f"{N}congress"))
    enacted = _date(meta.findtext(f"{N}approvedDate"))
    if enacted is None:
        approved = root.find(f".//{N}approvedDate")
        if approved is not None:
            enacted = _date(approved.get("date"))
    long_title = root.find(f".//{N}longTitle")
    decision = plan.action_for(seq) if plan is not None else None
    if decision is not None:
        if decision.action == "drop" or decision.kept_as is None:
            return None, 0, SkippedComponent(seq, "pLaw", doc_type, doc_number, "law number collision, dropped")
        from ingest.identifiers import LawIdentity

        identity = LawIdentity(kind="act", number=None, chapter=identity.chapter, primary=decision.kept_as, aliases=(decision.kept_as,))

    component = root
    warnings: list[str] = []
    citation, first_page, last_page = _pages_of(meta, component, volume)
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
    quoted = 0
    if main is None:
        warnings.append("no main element")
    else:
        units, page_units, quoted = _walk_units(component, main, identity.primary, warnings, first_page)

    short_titles = _short_titles(main) if main is not None else []
    for label in _all_pages(component):
        page_units.setdefault(label, None)
    if first_page is not None:
        page_units.setdefault(first_page, None)

    xml = serialize(root)
    law = LawRecord(
        identifier=identity.primary,
        kind=identity.kind,
        congress=congress,
        number=identity.number,
        chapter=identity.chapter,
        enacted=enacted,
        doc_type=doc_kind,
        official_title=official_title,
        short_titles=short_titles,
        stat_volume=volume,
        stat_page_first=first_page,
        stat_page_last=last_page,
        citation=citation,
        source_package=package,
        seq_in_volume=seq,
        xml=xml,
        content_hash=content_hash(xml),
        aliases=list(identity.aliases),
        units=units,
        page_units=page_units,
        warnings=warnings,
    )
    return law, quoted, None


def _walk_units(
    component: etree._Element,
    main: etree._Element,
    law_identifier: str,
    warnings: list[str],
    first_page: str | None = None,
) -> tuple[list[UnitRecord], dict[str, str | None], int]:
    """Stamp identifiers in document order and collect the unit elements.

    The page cursor runs over the whole component (the preface carries the
    law's first page marker) so every unit knows the page it starts on.
    """
    current_page: str | None = first_page
    unit_elements: list[tuple[etree._Element, str, str, str | None, str | None, int, str | None]] = []
    page_units: dict[str, str | None] = {}
    occurrences: collections.Counter[str] = collections.Counter()
    quoted_sections = 0
    section_seen = False
    unnumbered_first: etree._Element | None = None
    in_main = False

    for element in component.iter():
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
        level = name
        if level == "section":
            value = _designator_of(element, level)
            if value is None:
                if not section_seen and unnumbered_first is None:
                    # The first section of an act is enacted without a number
                    # ("That the Secretary ...") and cited as section 1.
                    value = "1"
                    unnumbered_first = element
                else:
                    warnings.append("section without a number after the first; not addressable")
                    continue
            section_seen = True
        elif level in HIERARCHY_LEVELS or level in SUBSECTION_LEVELS:
            value = _designator_of(element, level)
            if value is None:
                continue
        else:
            continue

        parent_identifier = _parent_identifier(element, main) or law_identifier
        identifier = f"{parent_identifier}/{segment(level, value)}"
        occurrences[identifier] += 1
        occurrence = occurrences[identifier]
        if occurrence > 1 and level == "section":
            warnings.append(f"{identifier} occurs {occurrence} times")
        element.set("identifier", identifier)
        if level == "section" or level in HIERARCHY_LEVELS:
            unit_elements.append(
                (element, identifier, level, value, _heading_of(element), occurrence, current_page)
            )

    units: list[UnitRecord] = []
    for seq, (element, identifier, level, value, heading, occurrence, first_page) in enumerate(
        unit_elements, start=1
    ):
        ancestors = _ancestor_units(element, main)
        parent_identifier = ancestors[-1]["identifier"] if ancestors else None
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
                parent_identifier=parent_identifier,
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
                first_page=first_page,
                pages=pages,
            )
        )
    return units, page_units, quoted_sections


def _inside_skipped(element: etree._Element, stop: etree._Element) -> bool:
    for ancestor in element.iterancestors():
        if ancestor is stop:
            return False
        if local_name(ancestor) in SKIP_SUBTREES:
            return True
    return False


def _parent_identifier(element: etree._Element, stop: etree._Element) -> str | None:
    for ancestor in element.iterancestors():
        if ancestor is stop:
            return None
        found = ancestor.get("identifier")
        if found:
            return found
    return None


def _enclosing_unit(element: etree._Element, main: etree._Element | None) -> str | None:
    """The nearest ancestor section or hierarchy node that has been stamped."""
    for ancestor in element.iterancestors():
        if ancestor is main:
            return None
        name = local_name(ancestor)
        if name == "section" or name in HIERARCHY_LEVELS:
            return ancestor.get("identifier")
    return None


def _ancestor_units(element: etree._Element, stop: etree._Element) -> list[dict]:
    chain: list[dict] = []
    for ancestor in element.iterancestors():
        if ancestor is stop:
            break
        name = local_name(ancestor)
        if name in HIERARCHY_LEVELS and ancestor.get("identifier"):
            chain.append(
                {
                    "identifier": ancestor.get("identifier"),
                    "level": name,
                    "num": _designator_of(ancestor, name),
                    "heading": _heading_of(ancestor),
                }
            )
    chain.reverse()
    return chain


def _designator_of(element: etree._Element, level: str) -> str | None:
    num = element.find(f"{N}num")
    if num is None:
        return None
    return designator(level, num.get("value"), plain_text(num, skip=frozenset({"sidenote", "footnote", "page"})))


def _heading_of(element: etree._Element) -> str | None:
    heading = element.find(f"{N}heading")
    if heading is None:
        return None
    text = plain_text(heading)
    return text or None


def page_label(identifier: str | None) -> str | None:
    """`/us/stat/64/B3` → `b3`; None for a marker with no usable identifier."""
    if not identifier:
        return None
    match = _PAGE_ID.match(identifier.strip())
    if not match:
        return None
    return "".join(match.group("page").split()).lower()


def _all_pages(component: etree._Element) -> list[str]:
    seen: list[str] = []
    for page in component.iter(f"{N}page"):
        label = page_label(page.get("identifier"))
        if label and label not in seen:
            seen.append(label)
    return seen


def _pages_of(
    meta: etree._Element, component: etree._Element, volume: int
) -> tuple[str | None, str | None, str | None]:
    """(`68 Stat. 919`, first page label, last page label)."""
    citation = None
    first = None
    for citable in meta.findall(f"{N}citableAs"):
        match = _STAT_CITE.search(citable.text or "")
        if match and int(match.group("volume")) == volume:
            first = "".join(match.group("page").split()).lower()
            citation = f"{volume} Stat. {match.group('page')}"
            break
    pages = _all_pages(component)
    if first is None and pages:
        first = pages[0]
        citation = f"{volume} Stat. {first}"
    last = pages[-1] if pages else first
    return citation, first, last


def _short_titles(main: etree._Element) -> list[str]:
    titles: list[str] = []
    for element in main.iter(f"{N}shortTitle"):
        if _inside_skipped(element, main):
            continue
        text = plain_text(element).strip("“”\"'.,; ")
        if text and text not in titles:
            titles.append(text)
    return titles[:8]


def _doc_kind(text: str | None) -> str | None:
    if not text:
        return None
    upper = " ".join(text.split()).upper()
    if "JOINT" in upper:
        return "Joint Resolution"
    if "ACT" in upper:
        return "An Act"
    return " ".join(text.split()).title()


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
