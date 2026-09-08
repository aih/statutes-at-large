"""Reading text and fragment extraction from stored USLM.

Shared by `ingest/` (which computes text at load time) and `storage/` (which cuts
a provision out of a section at request time). Knows two things about USLM: the
apparatus elements that are not reading text, and that `@identifier` addresses a
node.
"""

from __future__ import annotations

import hashlib
import re

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


def fragment_by_identifier(xml: str, identifier: str) -> etree._Element | None:
    """The first descendant (or the root) carrying `@identifier`."""
    root = etree.fromstring(xml.encode("utf-8"))
    if root.get("identifier") == identifier:
        return root
    found = root.xpath(".//*[@identifier=$id]", id=identifier)
    return found[0] if found else None
