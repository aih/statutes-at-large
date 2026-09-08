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
) -> LawIdentity | None:
    """Decide what a `pLaw` component is and which identifiers it answers to.

    `doc_type` is the component's `dc:type`: `Public Law`, `Private Law`, or
    `Chapter` (1957 and before, where `docNumber` is the chapter). For a
    chapter, the law number is read from the long title's marginal note.

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


_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(text: str) -> int | None:
    """`CXLVII` → 147. None for anything that is not a Roman numeral."""
    letters = text.strip().upper().rstrip(".")
    if not letters or any(ch not in _ROMAN for ch in letters):
        return None
    total = 0
    for index, ch in enumerate(letters):
        value = _ROMAN[ch]
        if index + 1 < len(letters) and _ROMAN[letters[index + 1]] > value:
            total -= value
        else:
            total += value
    return total


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
