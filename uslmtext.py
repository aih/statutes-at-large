"""Reading text and fragment extraction from stored USLM.

Shared by `ingest/` (which computes text at load time) and `storage/` (which cuts
a provision out of a section at request time, and a printed page's slice out of
a law). Knows three things about USLM: the apparatus elements that are not
reading text, that `@identifier` addresses a node, and that a `page` element is
a page break (ADR-0020).
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass

from lxml import etree

USLM_NS = "http://schemas.gpo.gov/xml/uslm"

#: Elements whose text is apparatus around the statute, not the statute:
#: marginal notes, page markers, footnotes, and tables of contents.
APPARATUS = frozenset({"sidenote", "page", "footnote", "toc", "editorialNote"})

_WS = re.compile(r"\s+")


def local_name(element: etree._Element) -> str | None:
    if not isinstance(element.tag, str):
        return None
    return etree.QName(element).localname


def plain_text(element: etree._Element, *, skip: frozenset[str] = APPARATUS) -> str:
    """Whitespace-normalized text of an element, apparatus removed."""
    parts: list[str] = []
    _collect(element, skip, parts)
    return _WS.sub(" ", "".join(parts)).strip()


def _collect(element: etree._Element, skip: frozenset[str], parts: list[str]) -> None:
    name = local_name(element)
    if name is None:
        if element.tail:
            parts.append(element.tail)
        return
    if name in skip:
        if element.tail:
            parts.append(element.tail)
        return
    if element.text:
        parts.append(element.text)
    for child in element:
        _collect(child, skip, parts)
        if child is not None and local_name(child) is None and child.tail:
            pass
    if name in _BLOCKISH:
        parts.append(" ")
    if element.tail:
        parts.append(element.tail)


_BLOCKISH = frozenset(
    {
        "p", "heading", "num", "content", "chapeau", "continuation", "section",
        "subsection", "paragraph", "subparagraph", "clause", "subclause", "item",
        "level", "listItem", "td", "tr", "longTitle", "officialTitle", "docTitle",
        "enactingFormula", "actionDescription", "quotedContent", "block",
        "signature", "proviso", "recital", "resolvingClause",
    }
)


def serialize(element: etree._Element) -> str:
    return etree.tostring(element, encoding="unicode")


def content_hash(xml: str) -> str:
    return hashlib.sha256(xml.encode("utf-8")).hexdigest()


_PAGE_ID = re.compile(r"^/us/stat/(?P<volume>\d+)/(?P<page>[^/@]+)")


def page_label(identifier: str | None) -> str | None:
    """`/us/stat/64/B3` → `b3`; None for a marker with no usable identifier."""
    if not identifier:
        return None
    match = _PAGE_ID.match(identifier.strip())
    if not match:
        return None
    return "".join(match.group("page").split()).lower()


@dataclass(frozen=True, slots=True)
class PageSlice:
    """What one printed page holds of a law: its USLM, its text, and the marker
    that ends it."""

    xml: str
    text: str
    to: str | None
    """The identifier of the page marker the range ends at; None at the
    document's end and when that marker carries no identifier."""


_STAT_CITE_PAGE = re.compile(r"\bStat\.?\s*([0-9A-Za-z]+(?:-\d+)?)", re.IGNORECASE)


def _starting_page_from_meta(root: etree._Element) -> str | None:
    for citable in root.iter(f"{{{USLM_NS}}}citableAs"):
        text = citable.text or ""
        match = _STAT_CITE_PAGE.search(text)
        if match:
            return "".join(match.group(1).split()).lower()
    return None


def _in_preface_or_before_main(marker: etree._Element, root: etree._Element) -> bool:
    curr = marker.getparent()
    while curr is not None and curr != root:
        if local_name(curr) == "preface":
            return True
        curr = curr.getparent()
    main = root.find(f"{{{USLM_NS}}}main")
    if main is not None:
        for elem in root.iter():
            if elem == marker:
                return True
            if elem == main:
                return False
    return False


def page_slice(xml: str, page: str, *, first_page: str | None = None) -> PageSlice:
    """The slice of a law's stored XML that the page prints.

    `page` is a page label (`564`, `a12`), matched against the `page` markers
    case-insensitively. The range runs from the marker that names the page to
    the next marker in document order, whichever page that one names. A law
    that starts on the page carries no marker for it, and the range then starts
    at the root and ends at the first marker. The law's `meta` is dropped: it
    is the package's metadata, not text the page prints.
    """
    root = etree.fromstring(xml.encode("utf-8"))
    label = "".join(page.split()).lower()
    markers = [element for element in root.iter() if local_name(element) == "page" and element.get("display") != "no"]
    law_start_page = "".join(first_page.split()).lower() if first_page is not None else _starting_page_from_meta(root)

    start_at = next(
        (i for i, marker in enumerate(markers) if page_label(marker.get("identifier")) == label),
        None,
    )

    if start_at is not None:
        is_first_identified = all(page_label(m.get("identifier")) is None for m in markers[:start_at])
        if is_first_identified and (
            law_start_page == label
            or (law_start_page is None and _in_preface_or_before_main(markers[start_at], root))
        ):
            start = None
            end = markers[start_at + 1] if start_at + 1 < len(markers) else None
        else:
            start = markers[start_at]
            end = markers[start_at + 1] if start_at + 1 < len(markers) else None
    else:
        starts_on_label = False
        if law_start_page is not None and law_start_page == label:
            starts_on_label = True
        elif markers:
            first_id_marker = next(
                (m for m in markers if page_label(m.get("identifier")) is not None),
                None,
            )
            if first_id_marker is not None:
                first_label = page_label(first_id_marker.get("identifier"))
                if (
                    first_label
                    and first_label.isdigit()
                    and label.isdigit()
                    and int(first_label) == int(label) + 1
                ):
                    starts_on_label = True
        elif not markers and law_start_page is None:
            starts_on_label = False

        if not starts_on_label:
            return PageSlice(xml="", text="", to=None)

        start = None
        end = markers[0] if markers else None

    cut = slice_between(root, start, end)
    for meta in cut.findall(f"{{{USLM_NS}}}meta"):
        cut.remove(meta)
    return PageSlice(
        xml=etree.tostring(cut, encoding="unicode", with_tail=False),
        text=plain_text(cut),
        to=end.get("identifier") if end is not None else None,
    )


def slice_between(
    root: etree._Element, start: etree._Element | None, end: etree._Element | None
) -> etree._Element:
    """A copy of `root` holding what lies between two of its `page` markers.

    The range opens at the start of `start` and closes at the end of `end`;
    `None` for `start` opens at the root and `None` for `end` closes at the
    document's end. An element's text is kept when the range is open at its
    start and its tail when the range is open at its end. An element is kept
    when it or a descendant is inside the range; its ancestors are kept as
    containers. Comments and processing instructions are dropped. `root` is
    left as it was.
    """
    cut = copy.deepcopy(root)
    original = list(root.iter())
    nodes = list(cut.iter())
    positions = {id(element): i for i, element in enumerate(original)}
    start_node = nodes[positions[id(start)]] if start is not None else None
    end_node = nodes[positions[id(end)]] if end is not None else None

    inside = start_node is None
    keep: set[int] = {id(cut)}
    blank_text: set[int] = set()
    blank_tail: set[int] = set()
    open_elements: list[bool] = []
    for event, element in etree.iterwalk(cut, events=("start", "end")):
        if event == "start":
            if element is start_node:
                inside = True
            if not inside:
                blank_text.add(id(element))
            open_elements.append(inside)
        else:
            if element is end_node:
                inside = False
            if not inside:
                blank_tail.add(id(element))
            if open_elements.pop():
                keep.add(id(element))
                if open_elements:
                    open_elements[-1] = True

    for element in nodes:
        if id(element) in blank_text:
            element.text = None
        if id(element) in blank_tail:
            element.tail = None
    for element in nodes:
        if id(element) in keep or element is cut:
            continue
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)
    return cut


def fragment_by_identifier(xml: str, identifier: str) -> etree._Element | None:
    """The first descendant (or the root) carrying `@identifier`."""
    root = etree.fromstring(xml.encode("utf-8"))
    if root.get("identifier") == identifier:
        return root
    found = root.xpath(".//*[@identifier=$id]", id=identifier)
    return found[0] if found else None
