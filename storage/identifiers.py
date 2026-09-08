"""Pure parsing of the identifier forms this site serves (design section 3).

No database and no XML here: this module knows the *shape* of an identifier and
nothing about what exists. Both `storage/` and `api/` import it.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

_LAW = re.compile(
    r"^/us/(?P<kind>pl|pvtl)/(?P<congress>\d+)/(?P<number>\d+)(?P<path>/.*)?$"
)
_ACT = re.compile(
    r"^/us/act/(?P<date>\d{4}-\d{2}-\d{2})/ch(?P<chapter>\d+)(?P<path>/.*)?$"
)
_COMP = re.compile(r"^/us/sComp/(?P<congress>\d+)/(?P<number>\d+)(?P<path>/.*)?$")
_STAT = re.compile(r"^/us/stat/(?P<volume>\d+)/(?P<page>[0-9A-Za-z]+(?:-\d+)?)$")

#: The last segment of a section-or-lower identifier: `s814`, `e`, `1`, `A`.
_SECTION_SEGMENT = re.compile(r"^s(?P<num>\d.*)$")

#: Prefixes of the hierarchy segments in GPO's PLAW scheme, longest first so
#: `sch` is tried before `s` and `spt` before `s`.
LEVEL_PREFIXES: tuple[tuple[str, str], ...] = (
    ("sch", "subchapter"),
    ("spt", "subpart"),
    ("st", "subtitle"),
    ("ch", "chapter"),
    ("pt", "part"),
    ("d", "division"),
    ("t", "title"),
)


@dataclass(frozen=True, slots=True)
class ParsedIdentifier:
    """A served identifier split into the law it names and the path under it."""

    kind: str
    """`pl` | `pvtl` | `act` | `sComp`."""

    law_identifier: str
    """`/us/pl/83/703`, `/us/act/1954-08-30/ch1073`, `/us/sComp/83/703`."""

    path: str
    """Everything after the law, `/tI/ch1/s1`; `''` for the law itself."""

    congress: int | None = None
    number: int | None = None
    chapter: int | None = None
    enacted: datetime.date | None = None

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(seg for seg in self.path.split("/") if seg)

    @property
    def section_num(self) -> str | None:
        """The `s…` segment's number, when the path reaches a section."""
        for seg in self.segments:
            match = _SECTION_SEGMENT.match(seg)
            if match:
                return match.group("num")
        return None

    @property
    def section_identifier(self) -> str | None:
        """The identifier cut at its section segment, or None above a section."""
        parts: list[str] = []
        for seg in self.segments:
            parts.append(seg)
            if _SECTION_SEGMENT.match(seg):
                return self.law_identifier + "/" + "/".join(parts)
        return None

    @property
    def below_section(self) -> tuple[str, ...]:
        """Segments after the section: `('e', '1')`."""
        segs = self.segments
        for index, seg in enumerate(segs):
            if _SECTION_SEGMENT.match(seg):
                return segs[index + 1 :]
        return ()


def _is_hierarchy_segment(segment: str) -> bool:
    """`tI`, `stA`, `sch1`, `dA` are hierarchy segments; `s814` is a section."""
    if _SECTION_SEGMENT.match(segment):
        return False
    return any(
        segment.startswith(prefix) and len(segment) > len(prefix)
        for prefix, _ in LEVEL_PREFIXES
    )


def parse_identifier(identifier: str) -> ParsedIdentifier | None:
    """`/us/pl/104/333/dI/tVIII/s814/e/1` → its parts; None for anything else."""
    text = normalize_identifier(identifier)
    match = _LAW.match(text)
    if match:
        congress, number = int(match.group("congress")), int(match.group("number"))
        return ParsedIdentifier(
            kind=match.group("kind"),
            law_identifier=f"/us/{match.group('kind')}/{congress}/{number}",
            path=(match.group("path") or "").rstrip("/"),
            congress=congress,
            number=number,
        )
    match = _ACT.match(text)
    if match:
        try:
            enacted = datetime.date.fromisoformat(match.group("date"))
        except ValueError:
            return None
        chapter = int(match.group("chapter"))
        return ParsedIdentifier(
            kind="act",
            law_identifier=f"/us/act/{enacted.isoformat()}/ch{chapter}",
            path=(match.group("path") or "").rstrip("/"),
            chapter=chapter,
            enacted=enacted,
        )
    match = _COMP.match(text)
    if match:
        congress, number = int(match.group("congress")), int(match.group("number"))
        return ParsedIdentifier(
            kind="sComp",
            law_identifier=f"/us/sComp/{congress}/{number}",
            path=(match.group("path") or "").rstrip("/"),
            congress=congress,
            number=number,
        )
    return None


@dataclass(frozen=True, slots=True)
class StatPageId:
    volume: int
    page: str
    """Lower-case label."""

    @property
    def identifier(self) -> str:
        return f"/us/stat/{self.volume}/{self.page}"

    @property
    def pdf(self) -> str:
        return f"https://www.govinfo.gov/link/statute/{self.volume}/{self.page}"


def parse_stat_page(identifier: str) -> StatPageId | None:
    """`/us/stat/64/B3` → volume 64, page `b3`."""
    match = _STAT.match(normalize_identifier(identifier))
    if not match:
        return None
    return StatPageId(int(match.group("volume")), normalize_page(match.group("page")))


def normalize_page(label: str) -> str:
    """Page labels are lower case (`b3`, not `B3`), spaces removed."""
    return "".join(label.split()).lower()


def normalize_identifier(path: str) -> str:
    """URL path → identifier. Both `/us/pl/81/443` and `us/pl/81/443/`."""
    cleaned = path.strip().strip("/")
    return f"/{cleaned}" if cleaned else "/"


def law_label(kind: str, congress: int | None, number: int | None,
              chapter: int | None, enacted: datetime.date | None) -> str:
    """`Public Law 83-703`, `Private Law 81-375`, `Act of August 30, 1954, ch. 1073`."""
    if kind == "pl" and congress is not None and number is not None:
        return f"Public Law {congress}-{number}"
    if kind == "pvtl" and congress is not None and number is not None:
        return f"Private Law {congress}-{number}"
    date = long_date(enacted) if enacted else "unknown date"
    if chapter is not None:
        return f"Act of {date}, ch. {chapter}"
    return f"Act of {date}"


def long_date(value: datetime.date) -> str:
    """`August 30, 1954` on every platform (no `%-d`)."""
    return f"{value:%B} {value.day}, {value.year}"


_PL_SECTION = re.compile(r"^\s*(?:sec(?:tion)?s?\.?\s*)?(?:§+\s*)?(?P<num>\d+[A-Za-z]*(?:-\d+)?)", re.IGNORECASE)


def section_number_of(pl_section_raw: str | None) -> str | None:
    """The section designator of a classification table's `Sec.` cell, in the
    form `units.section_num` uses: `101(3)` → `101`, `2(a)(1)` → `2`, `''` and
    `title I` → None."""
    if not pl_section_raw:
        return None
    match = _PL_SECTION.match(pl_section_raw)
    return match.group("num") if match else None


def law_label_of_identifier(identifier: str) -> str:
    """`/us/pl/104/333` → `Public Law 104-333`; an act by date and chapter;
    the identifier itself when it is neither."""
    parsed = parse_identifier(identifier)
    if parsed is None:
        return identifier
    return law_label(parsed.kind, parsed.congress, parsed.number, parsed.chapter, parsed.enacted)
