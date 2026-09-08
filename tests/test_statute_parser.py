"""The volume parser against verbatim slices of four volumes: the chapter era
(64, 1950), the first numbered-only year (72, 1958), and two born-digital
volumes (124, 137)."""

import pytest

from ingest.statute import parse_volume
from tests.conftest import FIXTURES, VOLUME_DIR, require


@pytest.fixture(scope="module")
def vol64():
    return parse_volume(FIXTURES / "statute-64-slice.xml")


@pytest.fixture(scope="module")
def vol72():
    return parse_volume(FIXTURES / "statute-72-slice.xml")


@pytest.fixture(scope="module")
def vol124():
    return parse_volume(FIXTURES / "statute-124-slice.xml")


@pytest.fixture(scope="module")
def vol137():
    return parse_volume(FIXTURES / "statute-137-slice.xml")


def by_id(parsed, identifier):
    return next(law for law in parsed.laws if law.identifier == identifier)


def test_slice_counts(vol64, vol72, vol124, vol137):
    assert (vol64.volume, len(vol64.laws), sum(len(l.units) for l in vol64.laws), sum(len(l.sections) for l in vol64.laws)) == (64, 10, 53, 48)
    assert (vol72.volume, len(vol72.laws), sum(len(l.units) for l in vol72.laws), sum(len(l.sections) for l in vol72.laws)) == (72, 6, 26, 18)
    assert (vol124.volume, len(vol124.laws), sum(len(l.units) for l in vol124.laws), sum(len(l.sections) for l in vol124.laws)) == (124, 4, 34, 24)
    assert (vol137.volume, len(vol137.laws), sum(len(l.units) for l in vol137.laws), sum(len(l.sections) for l in vol137.laws)) == (137, 2, 40, 28)


def test_chapter_era_law_has_both_identifiers(vol64):
    law = by_id(vol64, "/us/pl/81/443")
    assert law.kind == "pl" and law.congress == 81 and law.number == 443 and law.chapter == 3
    assert law.aliases == ["/us/pl/81/443", "/us/act/1950-02-08/ch3"]
    assert law.citation == "64 Stat. 4" and law.stat_page_first == "4"
    assert law.enacted.isoformat() == "1950-02-08"
    assert law.doc_type == "An Act"
    assert law.official_title == "To transfer funds to the town of Craig, Alaska."


def test_the_unnumbered_first_section_is_section_1(vol64):
    law = by_id(vol64, "/us/pl/81/443")
    assert [u.identifier for u in law.units] == ["/us/pl/81/443/s1"]
    assert law.units[0].text.startswith("That the Secretary of the Treasury is authorized")
    assert 'identifier="/us/pl/81/443/s1"' in law.units[0].xml
    assert 'identifier="/us/pl/81/443/s1"' in law.xml


def test_a_private_law_and_a_lettered_page(vol64):
    law = by_id(vol64, "/us/pvtl/81/375")
    assert law.kind == "pvtl" and law.chapter == 29
    assert law.stat_page_first == "a12"
    assert law.citation == "64 Stat. A12"
    assert law.aliases == ["/us/pvtl/81/375", "/us/act/1950-02-15/ch29"]


def test_the_law_number_comes_from_the_note_not_the_title(vol64):
    """Chapter 357 extends 'the Rubber Act of 1948 (Public Law 469, Eightieth
    Congress)'; its own number is 575."""
    law = by_id(vol64, "/us/pl/81/575")
    assert law.chapter == 357
    assert "Public Law 469" in law.official_title


def test_the_vendor_bill_href_form(vol64):
    law = by_id(vol64, "/us/pl/81/500")
    assert law.chapter == 153


def test_paragraphs_are_stamped_and_pages_tracked(vol64):
    law = by_id(vol64, "/us/pl/81/740")
    s3 = next(u for u in law.units if u.identifier == "/us/pl/81/740/s3")
    assert 'identifier="/us/pl/81/740/s3/1"' in s3.xml
    assert s3.pages == ["564"]
    assert s3.first_page == "563"
    s4 = next(u for u in law.units if u.identifier == "/us/pl/81/740/s4")
    assert s4.first_page == "564"
    assert law.page_units["564"] == "/us/pl/81/740/s3"
    assert law.page_units["563"] is None
    assert law.stat_page_first == "563" and law.stat_page_last == "567"


def test_titles_become_hierarchy_units_with_ancestors(vol64):
    law = by_id(vol64, "/us/pl/81/910")
    levels = [(u.identifier, u.level) for u in law.units[:3]]
    assert levels == [
        ("/us/pl/81/910/tI", "title"),
        ("/us/pl/81/910/tI/s101", "section"),
        ("/us/pl/81/910/tI–A", "title"),
    ]
    s101 = law.units[1]
    assert s101.ancestors == [{"identifier": "/us/pl/81/910/tI", "level": "title", "num": "I", "heading": None}]
    assert s101.parent_identifier == "/us/pl/81/910/tI" and s101.depth == 2
    assert law.units[0].xml is None and law.units[0].text is None


def test_quoted_sections_are_not_units(vol64):
    law = by_id(vol64, "/us/pl/81/490")
    assert [u.num for u in law.units] == ["1", "2", "3", "4"]
    assert vol64.sections_in_quoted_content == 1
    assert "<quotedContent>" in law.units[0].xml


def test_1958_laws_carry_only_their_number(vol72):
    law = by_id(vol72, "/us/pl/85/910")
    assert law.chapter is None and law.aliases == ["/us/pl/85/910"]
    assert law.citation == "72 Stat. 1751"
    assert law.official_title.startswith("To provide for the establishment of Grand Portage")
    assert [u.identifier for u in law.units][:2] == ["/us/pl/85/910/s1", "/us/pl/85/910/s2"]


def test_joint_resolutions_are_laws(vol72):
    law = by_id(vol72, "/us/pl/85/317")
    assert law.doc_type == "Joint Resolution"


def test_short_titles_and_headings_in_a_born_digital_volume(vol124):
    law = by_id(vol124, "/us/pl/111/344")
    assert law.short_titles == ["Omnibus Trade Act of 2010"]
    assert law.units[0].heading == "SHORT TITLE; TABLE OF CONTENTS."
    identifiers = [u.identifier for u in law.units]
    assert "/us/pl/111/344/tI" in identifiers
    assert any(i.startswith("/us/pl/111/344/tI/stA/s") for i in identifiers)
    title = next(u for u in law.units if u.identifier == "/us/pl/111/344/tI")
    assert title.heading.startswith("EXTENSION OF TRADE ADJUSTMENT")


def test_a_private_law_after_2000(vol124):
    law = by_id(vol124, "/us/pvtl/111/2")
    assert law.citation == "124 Stat. 4525"
    assert law.units[0].heading.startswith("PERMANENT RESIDENT STATUS")


def test_divisions_and_subtitles(vol137):
    law = by_id(vol137, "/us/pl/118/22")
    identifiers = [u.identifier for u in law.units]
    assert "/us/pl/118/22/dA" in identifiers and "/us/pl/118/22/dB" in identifiers
    assert any(i.startswith("/us/pl/118/22/dB/tI/s") for i in identifiers)
    assert law.short_titles[0] == "Further Continuing Appropriations and Other Extensions Act, 2024"
    assert law.stat_page_first == "112" and law.stat_page_last == "124"
    assert vol137.sections_in_quoted_content == 9


def test_unit_xml_is_the_section_alone_and_hashes_are_stable(vol137):
    law = by_id(vol137, "/us/pl/118/34")
    s1 = law.units[0]
    assert s1.xml.startswith("<section") and s1.xml.rstrip().endswith("</section>")
    assert len(s1.content_hash) == 64
    again = parse_volume(FIXTURES / "statute-137-slice.xml")
    assert by_id(again, "/us/pl/118/34").units[0].content_hash == s1.content_hash


def test_1954_law_typed_as_public_law_still_gets_its_chapter():
    """Volume 68 types laws `Public Law` with the chapter in the preface
    ("chapter 1073"); the Atomic Energy Act answers to both forms."""
    parsed = parse_volume(FIXTURES / "statute-68-slice.xml")
    law = by_id(parsed, "/us/pl/83/703")
    assert law.chapter == 1073 and law.citation == "68 Stat. 919"
    assert law.aliases == ["/us/pl/83/703", "/us/act/1954-08-30/ch1073"]
    # The act restates the Atomic Energy Act of 1946 inside section 1 as quoted
    # text, so the enacted view has three sections and the restated act's own
    # sections stay inside section 1's XML (the compilation addresses them).
    assert [u.identifier for u in law.units] == ["/us/pl/83/703/s1", "/us/pl/83/703/s2", "/us/pl/83/703/s3"]
    assert parsed.sections_in_quoted_content > 100
    assert "Atomic Energy Act of 1954" in law.units[0].text


def test_an_1890_act_is_a_chapter_only():
    parsed = parse_volume(FIXTURES / "statute-26-slice.xml")
    law = by_id(parsed, "/us/act/1890-07-02/ch647")
    assert law.kind == "act" and law.number is None and law.chapter == 647
    assert law.citation == "26 Stat. 209"
    assert [u.identifier for u in law.units][:2] == ["/us/act/1890-07-02/ch647/s1", "/us/act/1890-07-02/ch647/s2"]


def test_a_component_holding_several_laws_yields_each():
    """Volume 116 packs 47 consecutive laws into one `component`; the slice keeps
    three of them."""
    parsed = parse_volume(FIXTURES / "statute-116-slice.xml")
    assert parsed.components == 1 and parsed.merged_components == 1
    assert [law.identifier for law in parsed.laws] == ["/us/pl/107/259", "/us/pl/107/260", "/us/pl/107/261"]
    assert [law.citation for law in parsed.laws] == ["116 Stat. 1741", "116 Stat. 1743", "116 Stat. 1745"]
    assert all(law.units[0].identifier == f"{law.identifier}/s1" for law in parsed.laws)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("volume", "laws", "sections", "skipped_quoted"),
    [(64, 1230, 3063, 358), (72, 1061, 3852, 871), (116, 246, 3918, 569), (124, 251, 4077, 591), (137, 34, 1291, 175)],
)
def test_full_volume_counts(volume, laws, sections, skipped_quoted):
    """The counts in docs/verification/statute-{n}.json, re-derived from the
    downloaded volume. Skips when data/statute/xmls is empty."""
    from ingest.numbering import plan_numbering
    from ingest.statute import iter_claims, iter_volume

    path = require(VOLUME_DIR / f"STATUTE-{volume}.xml")
    plan = plan_numbering(list(iter_claims(path)))
    header = None
    count = section_count = 0
    for item in iter_volume(path, plan):
        if hasattr(item, "components"):
            header = item
            continue
        count += 1
        section_count += len(item.sections)
    assert (count, section_count, header.sections_in_quoted_content) == (laws, sections, skipped_quoted)
