"""Cut a few laws out of a STATUTE volume into a small, valid volume file.

    uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-64.xml \
        tests/fixtures/statute-64-slice.xml 3 29 134 153 768 823 1212

The numbers are `meta/docNumber` values (chapters through 1957, law numbers
after). The volume `meta` and one `statutesPart` wrapper are kept, so the
slice parses exactly like the full file.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

NS = "http://schemas.gpo.gov/xml/uslm"
N = f"{{{NS}}}"


def main(source: Path, target: Path, wanted: list[str]) -> None:
    wanted_set = set(wanted)
    kept: list[bytes] = []
    volume_meta: bytes | None = None
    for _event, element in etree.iterparse(str(source), events=("end",)):
        if not isinstance(element.tag, str):
            continue
        name = etree.QName(element).localname
        if name == "meta" and element.getparent() is not None and etree.QName(element.getparent()).localname == "statutesAtLarge":
            volume_meta = etree.tostring(element)
            continue
        if name != "component" or element.get("role") is not None:
            continue
        meta = element.find(f".//{N}meta")
        number = meta.findtext(f"{N}docNumber") if meta is not None else None
        children = [c for c in element if isinstance(c.tag, str)]
        root = etree.QName(children[0]).localname if children else None
        if root == "pLaw" and number in wanted_set:
            kept.append(etree.tostring(element))
            wanted_set.discard(number)
        element.clear()
        parent = element.getparent()
        if parent is not None:
            while element.getprevious() is not None:
                del parent[0]
    if wanted_set:
        print(f"not found: {sorted(wanted_set)}", file=sys.stderr)
    head = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!-- Verbatim slice of ' + source.name.encode() + b' from the Hub dataset dreamproit/us-statutes-at-large: '
        b'the volume meta and the laws numbered ' + ", ".join(wanted).encode() + b'. Regenerate with scripts/extract_fixture.py. -->\n'
        b'<statutesAtLarge xmlns="' + NS.encode() + b'" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:dcterms="http://purl.org/dc/terms/" xml:lang="en">\n'
    )
    body = (volume_meta or b"") + b'\n<main><collection role="statutesParts">\n<component role="statutesPart"><meta><docPart>1</docPart></meta>\n'
    tail = b"\n</component>\n</collection></main>\n</statutesAtLarge>\n"
    target.write_bytes(head + body + b"\n".join(kept) + tail)
    etree.parse(str(target))  # must be well-formed
    print(f"{target}: {len(kept)} laws, {target.stat_size if hasattr(target, 'stat_size') else target.stat().st_size} bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
