"""Shrink a COMPS USLM file to its meta, preface (without the table of
contents), and the first N sections, keeping every identifier intact.

    uv run python scripts/extract_comp_fixture.py data/comps/COMPS-1630.xml \
        tests/fixtures/comps/COMPS-1630-slice.xml 6
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

NS = "http://schemas.gpo.gov/xml/uslm"
N = f"{{{NS}}}"


def main(source: Path, target: Path, keep: int) -> None:
    tree = etree.parse(str(source))
    root = tree.getroot()
    for toc in root.iter(f"{N}toc"):
        parent = toc.getparent()
        if parent is not None:
            parent.remove(toc)
    sections = list(root.iter(f"{N}section"))
    for section in sections[keep:]:
        parent = section.getparent()
        if parent is not None:
            parent.remove(section)
    # Drop hierarchy nodes left with no section at all.
    changed = True
    while changed:
        changed = False
        for name in ("subchapter", "chapter", "subtitle", "title", "division", "part"):
            for node in list(root.iter(f"{N}{name}")):
                if node.find(f".//{N}section") is None:
                    parent = node.getparent()
                    if parent is not None:
                        parent.remove(node)
                        changed = True
    comment = etree.Comment(
        f" Verbatim slice of GovInfo {source.stem} USLM: meta, preface without the table of "
        f"contents, and the first {keep} sections. Regenerate with scripts/extract_comp_fixture.py. "
    )
    root.addprevious(comment)
    tree.write(str(target), xml_declaration=True, encoding="UTF-8")
    print(f"{target}: {target.stat().st_size} bytes, {min(keep, len(sections))} of {len(sections)} sections")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
