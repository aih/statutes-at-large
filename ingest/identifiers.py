"""Identifier rules for volume USLM (OCR plan section 7).

Pure functions over strings and numbers. What comes out matches the forms the
Office of the Law Revision Counsel writes in US Code source credits:

    /us/pl/85/910                 public law, 57th Congress (1901) onward
    /us/pvtl/85/12                private law
    /us/act/1916-08-25/ch408      chapter-numbered act
    /s{n}, /s{n}/{a}/{1}          section and below, GPO's PLAW scheme
    /dA/tI/s101                   with division and title segments

Laws from 1901 to 1957 carry both a law number and a chapter number; both
identifiers are emitted, the law number as the primary form.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from storage.identifiers import congress_of_date, roman_to_int

FIRST_NUMBERED_CONGRESS = 57
"""Public-law numbering begins with the 57th Congress (1901)."""

LAST_CHAPTER_YEAR = 1957

#: `Public Law 443`, `Private law 375`, `Private Lavr 621` (OCR), `Public Law, No. 5`.
_LAW_NUMBER_IN_TEXT = re.compile(
    r"\[?\s*(?P<kind>Public|Private)\s+La\w*\.?,?\s*(?:No\.?\s*)?(?P<number>\d[\d,]*)",
    re.IGNORECASE,
)
_LAW_NUMBER_IN_HREF = re.compile(
    r"^/us/(?:(?P<kind>pl|pvtl)|bill/\d+/(?P<billkind>pl|pvtl))/(?:\d+/)?(?P<number>\d+)$"
)

#: Element name → identifier segment prefix, GPO's PLAW scheme.
LEVEL_PREFIX: dict[str, str] = {
    "division": "d",
    "title": "t",
    "subtitle": "st",
    "chapter": "ch",
    "subchapter": "sch",
    "part": "pt",
    "subpart": "spt",
    "section": "s",
}

#: Levels below a section carry the bare designator: `/a`, `/1`, `/A`, `/i`.
SUBSECTION_LEVELS: tuple[str, ...] = (
    "subsection", "paragraph", "subparagraph", "clause", "subclause", "item",
    "subitem", "subsubitem",
)

HIERARCHY_LEVELS: tuple[str, ...] = tuple(
    name for name in LEVEL_PREFIX if name != "section"
)


@dataclass(frozen=True, slots=True)
class LawIdentity:
    kind: str
    """`pl` | `pvtl` | `act`."""
    number: int | None
    chapter: int | None
    primary: str
    aliases: tuple[str, ...] = field(default=())
    """Every identifier, the primary first."""


def law_number_from_text(text: str) -> tuple[str, int] | None:
    """`… [H. R. 322] [Public Law 443]` → (`pl`, 443)."""
    match = _LAW_NUMBER_IN_TEXT.search(text)
    if not match:
        return None
    kind = "pl" if match.group("kind").lower() == "public" else "pvtl"
    return kind, int(match.group("number").replace(",", ""))


def law_number_from_hrefs(hrefs: list[str]) -> tuple[str, int] | None:
    """`/us/pl/81/443` or the vendor's `/us/bill/81/pl/500` → (`pl`, n)."""
    for href in hrefs:
        match = _LAW_NUMBER_IN_HREF.match(href.strip())
        if match:
            kind = match.group("kind") or match.group("billkind")
            return kind, int(match.group("number"))
    return None


def identify_law(
    *,
    congress: int | None,
    doc_type: str | None,
    doc_number: str | None,
    public_private: str | None,
    enacted: datetime.date | None,
    long_title_text: str = "",
    long_title_hrefs: list[str] | None = None,
    preface_chapter: int | None = None,
) -> LawIdentity | None:
    """Decide what a `pLaw` component is and which identifiers it answers to.

    `doc_type` is the component's `dc:type`: `Public Law`, `Private Law`, or
    `Chapter` (1957 and before, where `docNumber` is the chapter). For a
    chapter, the law number is read from the long title's marginal note. Some
    volumes of the numbered-and-chaptered years (68, 1954) type the law as
    `Public Law` and print the chapter in the preface; that is `preface_chapter`.

    None when nothing identifies the law: no number, no chapter, or a chapter
    with no enactment date.
    """
    number: int | None = None
    chapter: int | None = None
    kind: str | None = None
    doc_type = (doc_type or "").strip().lower()
    parsed_number = _int(doc_number)

    if doc_type in ("public law", "private law"):
        number = parsed_number
        kind = "pl" if doc_type == "public law" else "pvtl"
        chapter = preface_chapter
    else:
        if doc_type == "chapter":
            chapter = parsed_number
        found = law_number_from_text(long_title_text) or law_number_from_hrefs(
            long_title_hrefs or []
        )
        if found:
            kind, number = found
            if public_private in ("public", "private"):
                # The body's own flag wins over an OCR reading of the note.
                kind = "pl" if public_private == "public" else "pvtl"
        elif public_private == "private" and parsed_number is not None and doc_type != "chapter":
            kind, number = "pvtl", parsed_number
        elif public_private == "public" and parsed_number is not None and doc_type != "chapter":
            kind, number = "pl", parsed_number

    identifiers: list[str] = []
    numbered = (
        kind in ("pl", "pvtl")
        and number is not None
        and congress is not None
        and congress >= FIRST_NUMBERED_CONGRESS
    )
    if numbered:
        identifiers.append(f"/us/{kind}/{congress}/{number}")
    if chapter is not None and enacted is not None:
        identifiers.append(f"/us/act/{enacted.isoformat()}/ch{chapter}")
    if not identifiers:
        return None
    if not numbered:
        kind = "act"
    return LawIdentity(
        kind=kind or "act",
        number=number if numbered else number,
        chapter=chapter,
        primary=identifiers[0],
        aliases=tuple(identifiers),
    )


def parse_doc_number(value: str | None) -> int | None:
    """`3`, `[3]`, `CXLVII` (the first volumes print chapter numbers in Roman
    numerals) → an integer; None when nothing numeric is there."""
    if value is None:
        return None
    text = value.strip().strip("[]").strip()
    digits = re.sub(r"[^\d]", "", text)
    if digits:
        return int(digits)
    return roman_to_int(text)


_int = parse_doc_number


_SECTION_WORDS = re.compile(r"^(?:sec(?:tion)?s?\.?|§+)\s*", re.IGNORECASE)
_LEVEL_WORDS = re.compile(
    r"^(?:division|title|subtitle|chapter|subchapter|part|subpart|article)\s*",
    re.IGNORECASE,
)
_TRAILING = re.compile(r"[\.\-—–:;,\s]+$")
_PARENS = re.compile(r"^\((.*)\)$")


def designator(level: str, value: str | None, num_text: str | None) -> str | None:
    """The identifier segment's value for a numbered level.

    `num/@value` is used when present. Otherwise the number is read out of the
    `num` text: `Sec. 2.` → `2`, `TITLE I—` → `I`, `(a)` → `a`.
    Whitespace is removed; a trailing period is dropped.
    """
    raw = value if value is not None and value.strip() else None
    if raw is None and num_text:
        text = " ".join(num_text.split())
        if level == "section":
            text = _SECTION_WORDS.sub("", text)
        elif level in HIERARCHY_LEVELS:
            text = _LEVEL_WORDS.sub("", text)
        else:
            match = _PARENS.match(text.strip())
            if match:
                text = match.group(1)
        text = _TRAILING.sub("", text.strip())
        raw = text or None
    if raw is None:
        return None
    cleaned = "".join(raw.split())
    cleaned = _TRAILING.sub("", cleaned)
    return cleaned or None


def segment(level: str, value: str) -> str:
    """`('title', 'I')` → `tI`; `('section', '814')` → `s814`; `('subsection', 'e')` → `e`."""
    prefix = LEVEL_PREFIX.get(level)
    if prefix is None:
        return value
    return f"{prefix}{value}"


def congress_of_act(meta_congress: int | None, enacted: datetime.date | None) -> int | None:
    """The Congress a chapter act belongs to: the one sitting on the day it
    was approved. A volume's `meta/congress` names another for 450 of the
    2,101 laws in volume 26 and 518 of the 3,145 in volume 6 (ADR-0033). It
    is kept when the act has no date, and on the March 4 a term ended at
    noon, when it names the outgoing Congress."""
    if enacted is None:
        return meta_congress
    dated = congress_of_date(enacted)
    end_of_term = enacted < datetime.date(1935, 1, 3) and (enacted.month, enacted.day) == (3, 4) and enacted.year % 2 == 1
    if end_of_term and meta_congress == dated - 1:
        return meta_congress
    return dated


_VOLUME_CONGRESSES: dict[int, frozenset[int]] = {
    1: frozenset(range(1, 6)),
    2: frozenset(range(6, 13)),
    3: frozenset(range(13, 18)),
    4: frozenset(range(18, 24)),
    5: frozenset(range(24, 29)),
    6: frozenset(range(1, 29)),
    9: frozenset(range(29, 32)),
    10: frozenset({32, 33}),
    11: frozenset({34, 35}),
    12: frozenset({36, 37}),
    50: frozenset({75}),
    77: frozenset({87, 88}),
    89: frozenset({93, 94}),
}


def volume_congresses(volume: int) -> frozenset[int] | None:
    """The Congresses whose laws a volume prints: volumes 1 to 5 the public
    laws to 1845, volume 6 the private laws to 1845, one volume a Congress
    from 13 (the 38th) to 49 (the 74th), two a Congress from 51 (the 75th).
    Volume 77 reprints Public Laws 87-456 and 87-794; volume 89 prints laws
    of the 93rd approved in January 1975. None for the treaty volumes 7
    and 8."""
    if volume in _VOLUME_CONGRESSES:
        return _VOLUME_CONGRESSES[volume]
    if 13 <= volume <= 49:
        return frozenset({volume + 25})
    if volume >= 51:
        return frozenset({(volume - 55) // 2 + 77})
    return None


def congress_in_volume(
    meta_congress: int | None, enacted: datetime.date | None, volume: int, *, act: bool
) -> int | None:
    """The Congress of a law printed in `volume` (ADR-0036). A chapter act
    takes `congress_of_act` and a numbered law `meta/congress`, each when the
    volume prints that Congress; else the Congress of the approval date when
    the volume prints it; else the volume's one Congress; else
    `meta/congress`. An OCR year (34 Stat. 2683 is dated 1807), an act
    approved after its Congress ended (54 Stat. 1397, January 3, 1941), and
    a `meta/congress` naming the next Congress (37 Stat. 739) are kept to the
    volume's Congress."""
    allowed = volume_congresses(volume)
    if allowed is None:
        return congress_of_act(meta_congress, enacted) if act else meta_congress
    if act:
        dated_act = congress_of_act(meta_congress, enacted)
        if dated_act in allowed:
            return dated_act
    if meta_congress in allowed:
        return meta_congress
    if enacted is not None and congress_of_date(enacted) in allowed:
        return congress_of_date(enacted)
    if len(allowed) == 1:
        return next(iter(allowed))
    return meta_congress

