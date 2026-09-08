"""What a person types, turned into the identifier this site serves.

`Pub. L. 104-333, § 814(e)(1)` → `/us/pl/104/333/s814/e/1`;
`Act of Aug. 25, 1916, ch. 408` → `/us/act/1916-08-25/ch408`;
`110 Stat. 4196` → `/us/stat/110/4196`;
`43 U.S.C. 1701` → `/us/usc/t43/s1701`, which the US Code site serves.

Named `citeparse`, not `citations`: `citation.py` is the `/us/…` redirector
(the US Code site's ADR-0023 made the same choice for the same reason).

This module is pure. No database, no `storage/`, no `db/`, no HTTP
(`tests/test_architecture.py` enforces it). It knows what string names an
identifier and nothing about what is loaded; the accepted-forms table in
`tests/test_citeparse.py` therefore runs in `make test` with no fixtures.
Existence is `api/cite.py`'s question, answered with `Repository.labels`,
`stat_page` and `get_comp_unit`.

Rules that are easy to get wrong:

  * Subdivision case is kept. `§ 814(e)(1)(B)` → `/e/1/B`.
  * Hierarchy words in a citation (`div. A, title I`) are read into
    `hierarchy` and left out of a section's identifier: the section number is
    the join (design section 3, rule 3), and the stored form is reported by
    the API as `served_identifier`. A citation that names a hierarchy level
    and no section keeps the level in the identifier (`/us/pl/104/333/tVIII`).
  * A law cited by chapter without a date (`ch. 823, 64 Stat. 563`) has no
    `/us/act/` identifier of its own; the parse names the Statutes at Large
    page and carries `chapter`, and the API picks the document on that page.
  * A law from 1901 to 1957 cited by number is `/us/pl/…`; cited by date and
    chapter it is `/us/act/…`. Both are the same law (ADR-0002); the
    repository resolves the alias.
  * A US Code citation parses to `/us/usc/…` and is not resolved here.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["pl", "pvtl", "act", "stat", "sComp", "usc"]

USCODE_PREFIX = "/us/usc"


@dataclass(frozen=True, slots=True)
class ParsedCitation:
    """A citation resolved to the identifier that names it, and nothing more."""

    kind: Kind
    identifier: str
    """The deepest thing the citation named."""

    section_identifier: str
    """The section that contains `identifier` when the citation went below
    one; otherwise `identifier` itself."""

    label: str
    """The citation in this site's canonical written form."""

    law_identifier: str | None = None
    """`/us/pl/104/333`, `/us/act/1916-08-25/ch408`, `/us/sComp/83/703`;
    None for a Stat. page and a US Code citation."""

    congress: int | None = None
    number: int | None = None
    chapter: int | None = None
    enacted: datetime.date | None = None
    volume: int | None = None
    page: str | None = None
    """Lower case, the way pages are stored (`a12`)."""

    section_num: str | None = None
    subdivisions: tuple[str, ...] = ()
    hierarchy: tuple[str, ...] = ()
    """The hierarchy the citation wrote, as GPO segments (`dA`, `tI`)."""

    stat_page: str | None = None
    """A Stat. page the citation gave beside a law (`/us/stat/110/4196`)."""

    usc_title: str | None = None
    note: bool = False
    """A trailing `note`: the citation names a note under the section."""

    @property
    def below_section(self) -> str:
        """`/e/1` for `§ 814(e)(1)`; `''` for the section itself."""
        return "".join(f"/{s}" for s in self.subdivisions)


# ------------------------------------------------------------------ pieces

_DASH = r"[-‐-―]"
_WS = re.compile(r"[\s ]+")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH = (
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_DATE = _MONTH + r"\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})"
_ISO_DATE = r"(?P<iso>\d{4}-\d{2}-\d{2})"

_PL_WORD = r"(?:Pub(?:lic)?\.?\s*L(?:aw)?\.?|P\.\s?L\.|PL)(?:\s*No\.?)?"
_PVTL_WORD = r"(?:Priv(?:ate)?\.?\s*L(?:aw)?\.?|Pvt\.?\s*L(?:aw)?\.?)(?:\s*No\.?)?"
_LAW_NUM = r"(?P<congress>\d{1,3})\s*" + _DASH + r"\s*(?P<number>\d{1,5})"

_CHAPTER = r"ch(?:ap(?:ter)?)?\.?\s*(?P<chapter>\d+)"
_STAT_PAGE = r"(?P<page>\d+[A-Za-z]?(?:" + _DASH + r"\d+)?|[A-Za-z]\d+)"
_STAT = r"(?P<volume>\d{1,3})\s*Stat\.?\s*" + _STAT_PAGE + r"(?:\s*,\s*\d+[A-Za-z]?)*(?:\s*\(\d{4}\))?"

#: `814`, `2A`; a range (`§§ 814–816`) keeps its first number.
_SECTION_NUM = r"(?P<section>\d+[A-Za-z]?)"
#: `(a)(1)(B)`; a four-digit parenthetical is a year, not a subdivision.
_PARENS = r"(?P<subs>(?:\s*\((?!\d{4}\))[A-Za-z0-9]+\))*)"
_SECTION_WORD = r"(?:§§?|[Ss]ecs?\.?|[Ss]ections?)"
_SECTION = _SECTION_WORD + r"\s*" + _SECTION_NUM + _PARENS + r"(?:\s*" + _DASH + r"\s*\d+[A-Za-z]?)?"

_LEVELS: tuple[tuple[str, str], ...] = (
    (r"div(?:ision)?\.?", "d"),
    (r"subtit(?:le)?\.?", "st"),
    (r"title", "t"),
    (r"subch(?:ap(?:ter)?)?\.?", "sch"),
    (r"ch(?:ap(?:ter)?)?\.?", "ch"),
    (r"subpt\.?|subpart", "spt"),
    (r"pt\.?|part", "pt"),
)
_LEVEL = re.compile(
    r"^(?:" + "|".join(f"(?P<l{i}>{word})" for i, (word, _) in enumerate(_LEVELS)) + r")\s+(?P<num>[A-Za-z0-9]+)\.?$",
    re.IGNORECASE,
)

#: Pieces of a source credit that carry no address.
_NOISE = re.compile(
    r"^(?:as\s+(?:amended|added|redesignated|renumbered|revised)(?:\s+by.*)?|formerly.*|renumbered.*|eff\..*|effective.*)$",
    re.IGNORECASE,
)

# ------------------------------------------------------------------ patterns

_LAW = re.compile(
    r"^(?:(?P<pl>" + _PL_WORD + r")|(?P<pvtl>" + _PVTL_WORD + r"))\s*" + _LAW_NUM + r"(?P<tail>(?:\s*[,;:]?\s*.+)?)$",
    re.IGNORECASE,
)
_SECTION_OF_LAW = re.compile(
    r"^" + _SECTION + r"\s+of\s+(?:the\s+)?(?:(?P<pl>" + _PL_WORD + r")|(?P<pvtl>" + _PVTL_WORD + r"))\s*" + _LAW_NUM + r"(?P<tail>(?:\s*[,;:]?\s*.+)?)$",
    re.IGNORECASE,
)
_ACT = re.compile(
    r"^(?:(?:the\s+)?act\s+of\s+)?" + _DATE + r"\s*[,;]?\s*\(?" + _CHAPTER + r"\)?(?P<tail>(?:\s*[,;:]?\s*.+)?)$",
    re.IGNORECASE,
)
_ACT_ISO = re.compile(
    r"^(?:(?:the\s+)?act\s+of\s+)?" + _ISO_DATE + r"\s*[,;]?\s*\(?" + _CHAPTER + r"\)?(?P<tail>(?:\s*[,;:]?\s*.+)?)$",
    re.IGNORECASE,
)
_CHAPTER_ON_PAGE = re.compile(
    r"^" + _CHAPTER + r"\s*[,;]?\s*" + _STAT + r"(?P<tail>(?:\s*[,;:]?\s*.+)?)$",
    re.IGNORECASE,
)
_PAGE_WITH_CHAPTER = re.compile(
    r"^" + _STAT + r"\s*[,;]?\s*\(?" + _CHAPTER + r"\)?(?P<tail>(?:\s*[,;:]?\s*.+)?)$",
    re.IGNORECASE,
)
_STAT_ONLY = re.compile(r"^" + _STAT + r"$", re.IGNORECASE)

_USC = r"U\.?\s?S\.?\s?C\.?"
_USC_APP = r"(?:\s*,?\s*(?P<app>App(?:endix|x)?)\.?)?"
_USC_SECTION_NUM = r"(?P<section>[0-9]+[A-Za-z0-9]*(?:" + _DASH + r"[A-Za-z0-9]+)*)"
_USC_TRAILER = r"(?:\s*[,;]?\s*(?P<trailer>note|et\.?\s+seq\.?))?"
_USC_STANDARD = re.compile(
    r"^(?P<title>[0-9]+[aA]?)\s*" + _USC + _USC_APP + r"\s*(?:§{1,2}\s*)?"
    r"(?:" + _USC_SECTION_NUM + _PARENS + r")?" + _USC_TRAILER + r"\.?$",
    re.IGNORECASE,
)
_USC_INVERTED = re.compile(
    r"^" + _SECTION_WORD + r"\s*" + _USC_SECTION_NUM + _PARENS + r"\s+of\s+title\s+(?P<title>[0-9]+[aA]?)" + _USC_APP + _USC_TRAILER + r"\.?$",
    re.IGNORECASE,
)
_USC_TRAILING = re.compile(
    r"^" + _SECTION_WORD + r"\s*" + _USC_SECTION_NUM + _PARENS + r"\s*,\s*(?P<title>[0-9]+[aA]?)\s*" + _USC + _USC_APP + _USC_TRAILER + r"\.?$",
    re.IGNORECASE,
)
_USC_TITLE = re.compile(r"^title\s+(?P<title>[0-9]+[aA]?)" + _USC_APP + r"\.?$", re.IGNORECASE)

_PATH_LAW = re.compile(r"^/?us/(?P<kind>pl|pvtl)/(?P<congress>\d+)/(?P<number>\d+)(?P<path>(?:/[A-Za-z0-9.]+)*)/?$")
_PATH_ACT = re.compile(r"^/?us/act/" + _ISO_DATE + r"/ch(?P<chapter>\d+)(?P<path>(?:/[A-Za-z0-9.]+)*)/?$")
_PATH_STAT = re.compile(r"^/?us/stat/(?P<volume>\d+)/" + _STAT_PAGE + r"/?$")
_PATH_COMP = re.compile(r"^/?us/sComp/(?P<congress>\d+)/(?P<number>\d+)(?P<path>(?:/[A-Za-z0-9.]+)*)/?$")
_PATH_USC = re.compile(r"^/?us/usc/t(?P<title>[0-9]+[a-zA-Z]?)(?P<path>(?:/[A-Za-z0-9.‐-―-]+)*)/?$")

_SEGMENT_SECTION = re.compile(r"^s(?P<num>\d.*)$")
_SEGMENT_LEVEL = re.compile(r"^(?:sch|spt|st|ch|pt|d|t)[A-Za-z0-9.]+$")


# ------------------------------------------------------------------ helpers


def _wraps_whole(text: str) -> bool:
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(text) - 1
    return False


def _normalize(text: str) -> str:
    """Collapse whitespace and drop the punctuation a citation is wrapped in;
    wrapping parentheses go one balanced pair at a time so `§ 3(a)` keeps its
    own. `§` is kept: it is a signal."""
    cleaned = _WS.sub(" ", text).strip()
    while True:
        stripped = cleaned.strip(" ,;\"'[]“”‘’")
        if stripped.startswith("(") and stripped.endswith(")") and _wraps_whole(stripped):
            stripped = stripped[1:-1]
        if stripped == cleaned:
            return cleaned
        cleaned = stripped


def _subdivisions(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    return tuple(re.findall(r"\((?!\d{4}\))([A-Za-z0-9]+)\)", text))


def _date(groups: dict[str, str | None]) -> datetime.date | None:
    if groups.get("iso"):
        try:
            return datetime.date.fromisoformat(groups["iso"] or "")
        except ValueError:
            return None
    month = _MONTHS.get((groups.get("month") or "").lower().rstrip("."))
    if month is None:
        return None
    try:
        return datetime.date(int(groups["year"] or 0), month, int(groups["day"] or 0))
    except ValueError:
        return None


def _long_date(value: datetime.date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


def _normalize_page(label: str) -> str:
    return re.sub(_DASH, "-", "".join(label.split())).lower()


@dataclass
class _Tail:
    """What the pieces after a law or an act said."""

    section: str | None = None
    subdivisions: tuple[str, ...] = ()
    hierarchy: list[str] = None  # type: ignore[assignment]
    stat_page: str | None = None
    volume: int | None = None
    page: str | None = None
    note: bool = False

    def __post_init__(self) -> None:
        if self.hierarchy is None:
            self.hierarchy = []


_MONTH_DAY = re.compile(r"^\(?" + _MONTH + r"\s+\d{1,2}$", re.IGNORECASE)
_TAIL_SECTION = re.compile(r"^" + _SECTION + r"(?P<note>\s+note)?(?:\s*\(\d{4}\))?$", re.IGNORECASE)
_TAIL_STAT = re.compile(r"^" + _STAT + r"$", re.IGNORECASE)
_TAIL_DATE = re.compile(r"^\(?" + _DATE + r"\)?$", re.IGNORECASE)
_TAIL_YEAR = re.compile(r"^\(\d{4}\)$")
_TAIL_NOTE = re.compile(r"^note$", re.IGNORECASE)


def _split_tail(tail: str) -> list[str]:
    """Pieces separated by commas or semicolons, except inside parentheses."""
    pieces: list[str] = []
    current: list[str] = []
    depth = 0
    for char in tail:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char in ",;" and depth == 0:
            pieces.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    pieces.append("".join(current).strip())
    cleaned = [p.strip(" .:") for p in pieces if p.strip(" .:")]
    # `Nov. 12, 1996` was split at its own comma; put the year back.
    merged: list[str] = []
    for piece in cleaned:
        if merged and _MONTH_DAY.match(merged[-1]) and re.match(r"^\d{4}\)?$", piece):
            merged[-1] = f"{merged[-1]}, {piece}"
        else:
            merged.append(piece)
    return merged


def _parse_tail(tail: str | None) -> _Tail | None:
    """None when a piece is not something a citation can carry."""
    out = _Tail()
    for piece in _split_tail(tail or ""):
        match = _TAIL_SECTION.match(piece)
        if match and out.section is None:
            out.section = match.group("section")
            out.subdivisions = _subdivisions(match.group("subs"))
            if match.group("note"):
                out.note = True
            continue
        match = _LEVEL.match(piece)
        if match:
            index = next(i for i in range(len(_LEVELS)) if match.group(f"l{i}"))
            out.hierarchy.append(f"{_LEVELS[index][1]}{match.group('num')}")
            continue
        match = _TAIL_STAT.match(piece)
        if match and out.stat_page is None:
            out.volume = int(match.group("volume"))
            out.page = _normalize_page(match.group("page"))
            out.stat_page = f"/us/stat/{out.volume}/{out.page}"
            continue
        if _TAIL_DATE.match(piece) or _TAIL_YEAR.match(piece) or _NOISE.match(piece):
            continue
        if _TAIL_NOTE.match(piece):
            out.note = True
            continue
        return None
    return out


def _law_label(kind: str, congress: int | None, number: int | None, chapter: int | None, enacted: datetime.date | None) -> str:
    if kind == "pl":
        return f"Public Law {congress}-{number}"
    if kind == "pvtl":
        return f"Private Law {congress}-{number}"
    if enacted is not None:
        return f"Act of {_long_date(enacted)}, ch. {chapter}"
    return f"ch. {chapter}"


def _section_label(section: str | None, subdivisions: tuple[str, ...], hierarchy: tuple[str, ...]) -> str:
    if section is not None:
        subs = "".join(f"({s})" for s in subdivisions)
        return f", section {section}{subs}"
    if hierarchy:
        return ", " + " ".join(_hierarchy_word(segment) for segment in hierarchy)
    return ""


_LEVEL_WORDS = {"d": "division", "st": "subtitle", "t": "title", "sch": "subchapter", "ch": "chapter", "spt": "subpart", "pt": "part"}


def _hierarchy_word(segment: str) -> str:
    for prefix in ("sch", "spt", "st", "ch", "pt", "d", "t"):
        if segment.startswith(prefix) and len(segment) > len(prefix):
            return f"{_LEVEL_WORDS[prefix]} {segment[len(prefix):]}"
    return segment


def _build_law(
    kind: Kind,
    law_identifier: str,
    tail: _Tail,
    *,
    congress: int | None = None,
    number: int | None = None,
    chapter: int | None = None,
    enacted: datetime.date | None = None,
) -> ParsedCitation:
    hierarchy = tuple(tail.hierarchy)
    if tail.section is not None:
        section_id = f"{law_identifier}/s{tail.section}"
        deepest = section_id + "".join(f"/{s}" for s in tail.subdivisions)
        lookup = section_id
    elif hierarchy:
        deepest = law_identifier + "".join(f"/{seg}" for seg in hierarchy)
        lookup = deepest
    else:
        deepest = lookup = law_identifier
    label = _law_label(kind, congress, number, chapter, enacted) + _section_label(tail.section, tail.subdivisions, hierarchy)
    if tail.note:
        label += " note"
    return ParsedCitation(
        kind=kind,
        identifier=deepest,
        section_identifier=lookup,
        label=label,
        law_identifier=law_identifier,
        congress=congress,
        number=number,
        chapter=chapter,
        enacted=enacted,
        volume=tail.volume,
        page=tail.page,
        section_num=tail.section,
        subdivisions=tail.subdivisions,
        hierarchy=hierarchy,
        stat_page=tail.stat_page,
        note=tail.note,
    )


def _build_stat(volume: int, page: str, *, chapter: int | None = None, printed: str | None = None) -> ParsedCitation:
    identifier = f"/us/stat/{volume}/{page}"
    label = f"{volume} Stat. {printed or page}"
    if chapter is not None:
        label = f"ch. {chapter}, {label}"
    return ParsedCitation(
        kind="stat",
        identifier=identifier,
        section_identifier=identifier,
        label=label,
        volume=volume,
        page=page,
        chapter=chapter,
    )


def _build_usc(title: str, app: bool, section: str | None, subdivisions: tuple[str, ...], note: bool) -> ParsedCitation:
    num = title.lstrip("0") or "0"
    if app and not num.lower().endswith("a"):
        num = f"{num}a"
    title_id = f"{USCODE_PREFIX}/t{num.lower()}"
    printed = f"{num[:-1]} U.S.C. App." if num.lower().endswith("a") else f"{num} U.S.C."
    if section is None:
        title_label = f"Title {num[:-1]}, Appendix, United States Code" if num.lower().endswith("a") else f"Title {num}, United States Code"
        return ParsedCitation(kind="usc", identifier=title_id, section_identifier=title_id, label=title_label, usc_title=num.lower(), note=note)
    section_id = f"{title_id}/s{section}"
    deepest = section_id + "".join(f"/{s}" for s in subdivisions)
    subs = "".join(f"({s})" for s in subdivisions)
    label = f"{printed} {section}{subs}" + (" note" if note else "")
    return ParsedCitation(
        kind="usc",
        identifier=deepest,
        section_identifier=section_id,
        label=label,
        usc_title=num.lower(),
        section_num=section,
        subdivisions=subdivisions,
        note=note,
    )


def _tail_from_path(path: str) -> _Tail | None:
    """`/dA/tI/s101/a` → the hierarchy, section and subdivisions it spells."""
    tail = _Tail()
    segments = [s for s in path.split("/") if s]
    after_section: list[str] = []
    for segment in segments:
        if tail.section is not None:
            after_section.append(segment)
            continue
        match = _SEGMENT_SECTION.match(segment)
        if match:
            tail.section = match.group("num")
            continue
        if _SEGMENT_LEVEL.match(segment):
            tail.hierarchy.append(segment)
            continue
        return None
    tail.subdivisions = tuple(after_section)
    return tail


# ------------------------------------------------------------------ parse


def parse_citation(text: str) -> ParsedCitation | None:
    """A citation in any accepted form → the identifier it names; None when
    the text is not a citation, which includes a bare section number and a
    chapter with no date and no page."""
    if not text or not text.strip():
        return None
    cleaned = _normalize(text)
    if not cleaned:
        return None
    return _parse_path(cleaned) or _parse_law(cleaned) or _parse_act(cleaned) or _parse_stat(cleaned) or _parse_usc(cleaned)


def _parse_path(text: str) -> ParsedCitation | None:
    match = _PATH_LAW.match(text)
    if match:
        tail = _tail_from_path(match.group("path"))
        if tail is None:
            return None
        congress, number = int(match.group("congress")), int(match.group("number"))
        kind = match.group("kind")
        return _build_law(kind, f"/us/{kind}/{congress}/{number}", tail, congress=congress, number=number)  # type: ignore[arg-type]
    match = _PATH_ACT.match(text)
    if match:
        enacted = _date(match.groupdict())
        tail = _tail_from_path(match.group("path"))
        if enacted is None or tail is None:
            return None
        chapter = int(match.group("chapter"))
        return _build_law("act", f"/us/act/{enacted.isoformat()}/ch{chapter}", tail, chapter=chapter, enacted=enacted)
    match = _PATH_STAT.match(text)
    if match:
        return _build_stat(int(match.group("volume")), _normalize_page(match.group("page")), printed=match.group("page"))
    match = _PATH_COMP.match(text)
    if match:
        congress, number = int(match.group("congress")), int(match.group("number"))
        law = f"/us/sComp/{congress}/{number}"
        segments = [s for s in match.group("path").split("/") if s]
        section = None
        subdivisions: list[str] = []
        for segment in segments:
            if section is not None:
                subdivisions.append(segment)
            elif _SEGMENT_SECTION.match(segment):
                section = segment[1:]
        identifier = law + "".join(f"/{s}" for s in segments)
        lookup = identifier if section is None else law + "".join(f"/{s}" for s in segments[: len(segments) - len(subdivisions)])
        return ParsedCitation(
            kind="sComp",
            identifier=identifier,
            section_identifier=lookup,
            label=f"Statute Compilation {identifier}",
            law_identifier=law,
            congress=congress,
            number=number,
            section_num=section,
            subdivisions=tuple(subdivisions),
        )
    match = _PATH_USC.match(text)
    if match:
        segments = [s for s in match.group("path").split("/") if s]
        section = None
        subdivisions: list[str] = []
        for segment in segments:
            if section is not None:
                subdivisions.append(segment)
            elif segment.startswith("s") and len(segment) > 1 and segment[1].isdigit():
                section = segment[1:]
            elif not _SEGMENT_LEVEL.match(segment):
                return None
        title = match.group("title")
        return _build_usc(title.rstrip("aA"), title[-1] in "aA", section, tuple(subdivisions), False)
    return None


def _parse_law(text: str) -> ParsedCitation | None:
    match = _LAW.match(text) or _SECTION_OF_LAW.match(text)
    if not match:
        return None
    groups = match.groupdict()
    tail = _parse_tail(groups.get("tail"))
    if tail is None:
        return None
    if groups.get("section") and tail.section is None:
        tail.section = groups["section"]
        tail.subdivisions = _subdivisions(groups.get("subs"))
    kind: Kind = "pl" if groups.get("pl") else "pvtl"
    congress, number = int(groups["congress"] or 0), int(groups["number"] or 0)
    return _build_law(kind, f"/us/{kind}/{congress}/{number}", tail, congress=congress, number=number)


def _parse_act(text: str) -> ParsedCitation | None:
    match = _ACT.match(text) or _ACT_ISO.match(text)
    if match:
        enacted = _date(match.groupdict())
        tail = _parse_tail(match.group("tail"))
        if enacted is None or tail is None:
            return None
        chapter = int(match.group("chapter"))
        return _build_law("act", f"/us/act/{enacted.isoformat()}/ch{chapter}", tail, chapter=chapter, enacted=enacted)
    match = _CHAPTER_ON_PAGE.match(text) or _PAGE_WITH_CHAPTER.match(text)
    if match:
        tail = _parse_tail(match.group("tail"))
        if tail is None:
            return None
        parsed = _build_stat(int(match.group("volume")), _normalize_page(match.group("page")), chapter=int(match.group("chapter")), printed=match.group("page"))
        if tail.section is not None:
            return ParsedCitation(
                kind=parsed.kind,
                identifier=parsed.identifier,
                section_identifier=parsed.section_identifier,
                label=parsed.label + _section_label(tail.section, tail.subdivisions, ()),
                volume=parsed.volume,
                page=parsed.page,
                chapter=parsed.chapter,
                section_num=tail.section,
                subdivisions=tail.subdivisions,
            )
        return parsed
    return None


def _parse_stat(text: str) -> ParsedCitation | None:
    match = _STAT_ONLY.match(text)
    if not match:
        return None
    return _build_stat(int(match.group("volume")), _normalize_page(match.group("page")), printed=match.group("page"))


def _parse_usc(text: str) -> ParsedCitation | None:
    for pattern in (_USC_TRAILING, _USC_INVERTED, _USC_STANDARD):
        match = pattern.match(text)
        if match:
            groups = match.groupdict()
            note = (groups.get("trailer") or "").lower().startswith("note")
            title = groups["title"] or ""
            app = bool(groups.get("app")) or title[-1] in "aA"
            return _build_usc(title.rstrip("aA"), app, groups.get("section"), _subdivisions(groups.get("subs")), note)
    match = _USC_TITLE.match(text)
    if match:
        title = match.group("title")
        return _build_usc(title.rstrip("aA"), bool(match.group("app")) or title[-1] in "aA", None, (), False)
    return None


if __name__ == "__main__":  # pragma: no cover
    import dataclasses
    import json
    import sys

    parsed = parse_citation(" ".join(sys.argv[1:]))
    print(json.dumps(None if parsed is None else dataclasses.asdict(parsed), indent=2, ensure_ascii=False, default=str))
