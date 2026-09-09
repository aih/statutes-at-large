"""The page slice (ADR-0020): the range between two `page` markers, over a
hand-written document and over the volume slices GPO published."""

from lxml import etree

from tests.conftest import FIXTURES
from uslmtext import USLM_NS, local_name, page_label, page_slice, plain_text, slice_between

N = f"{{{USLM_NS}}}"

DOC = f"""<pLaw xmlns="{USLM_NS}">
  <preface>[CHAPTER 1]</preface>
  <main>
    <section identifier="/us/pl/1/1/s1"><num>1.</num>
      <content>before<page identifier="/us/stat/1/2">2</page>after
        <quotedContent>quoted<page identifier="/us/stat/1/3">3</page>more</quotedContent>tail
      </content>
    </section>
    <section identifier="/us/pl/1/1/s2"><num>2.</num><content>last</content></section>
  </main>
</pLaw>"""


def markers(root):
    return [element for element in root.iter() if local_name(element) == "page"]


def test_page_label_is_lower_case():
    assert page_label("/us/stat/64/B3") == "b3"
    assert page_label("/us/stat/64/A 12") == "a12"
    assert page_label(None) is None and page_label("/us/pl/81/740") is None


def test_the_range_runs_from_one_marker_to_the_next():
    cut = page_slice(DOC, "2")
    assert cut.to == "/us/stat/1/3"
    assert cut.text == "after quoted"
    assert "before" not in cut.xml and "more" not in cut.xml


def test_a_marker_inside_quoted_content_ends_the_range():
    cut = page_slice(DOC, "3")
    assert cut.to is None
    assert cut.text == "more tail 2. last"


def test_no_marker_for_the_page_starts_at_the_root():
    cut = page_slice(DOC, "1")
    assert cut.to == "/us/stat/1/2"
    assert cut.text.startswith("[CHAPTER 1] 1. before")


def test_the_slice_keeps_the_ancestors_of_what_it_holds():
    root = etree.fromstring(page_slice(DOC, "2").xml.encode())
    section = root.find(f"{N}main/{N}section")
    assert section.get("identifier") == "/us/pl/1/1/s1"
    assert [local_name(e) for e in root.iter() if local_name(e) == "section"] == ["section"]


def test_the_original_is_not_modified():
    root = etree.fromstring(DOC.encode())
    before = etree.tostring(root)
    slice_between(root, markers(root)[0], markers(root)[1])
    assert etree.tostring(root) == before


def test_the_laws_meta_is_not_part_of_the_page():
    assert "<meta" not in page_slice(DOC.replace("<preface>", "<meta><dc>x</dc></meta><preface>"), "1").xml


def test_every_marker_of_volume_124_slices():
    """The 2010 slice carries 15 markers, one of them inside `quotedContent`
    and one with no identifier: every page it names parses and holds text the
    law prints."""
    root = etree.parse(str(FIXTURES / "statute-124-slice.xml")).getroot()
    seen = 0
    for plaw in root.iter(f"{N}pLaw"):
        xml = etree.tostring(plaw, encoding="unicode")
        whole = plain_text(plaw)
        for marker in markers(plaw):
            label = page_label(marker.get("identifier"))
            if label is None:
                continue
            seen += 1
            cut = page_slice(xml, label)
            etree.fromstring(cut.xml.encode())
            assert cut.text and cut.text in whole
    assert seen == 14
