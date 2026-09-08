"""The identifier rules (OCR plan section 7) and the parser of served identifiers."""

import datetime

import pytest

from ingest.identifiers import designator, identify_law, segment
from storage.identifiers import law_label, normalize_page, parse_identifier, parse_stat_page


def test_a_numbered_law_after_1901_gets_both_forms():
    identity = identify_law(
        congress=81, doc_type="Chapter", doc_number="3", public_private="public",
        enacted=datetime.date(1950, 2, 8),
        long_title_text="[H. R. 322] [Public Law 443]",
        long_title_hrefs=["/us/bill/81/hr/322", "/us/pl/81/443"],
    )
    assert identity.kind == "pl"
    assert identity.primary == "/us/pl/81/443"
    assert identity.aliases == ("/us/pl/81/443", "/us/act/1950-02-08/ch3")


def test_a_private_law_reads_its_number_from_the_note_even_when_ocr_slips():
    identity = identify_law(
        congress=81, doc_type="Chapter", doc_number="413", public_private="private",
        enacted=datetime.date(1950, 6, 29), long_title_text="[S. 2511] [Private Lavr 621]",
    )
    assert identity.primary == "/us/pvtl/81/621"
    assert identity.chapter == 413


def test_the_vendor_bill_href_form_is_read():
    identity = identify_law(
        congress=81, doc_type="Chapter", doc_number="153", public_private="public",
        enacted=datetime.date(1950, 5, 3), long_title_hrefs=["/us/bill/81/pl/500"],
    )
    assert identity.primary == "/us/pl/81/500"


def test_a_law_after_1957_has_only_its_number():
    identity = identify_law(congress=85, doc_type="Public Law", doc_number="910",
                            public_private="public", enacted=datetime.date(1958, 9, 2))
    assert identity.aliases == ("/us/pl/85/910",)
    assert identity.chapter is None


def test_an_act_before_1901_is_cited_by_chapter():
    identity = identify_law(congress=51, doc_type="Chapter", doc_number="647",
                            public_private="public", enacted=datetime.date(1890, 7, 2))
    assert identity.kind == "act"
    assert identity.aliases == ("/us/act/1890-07-02/ch647",)


def test_a_chapter_with_no_number_and_no_date_is_unidentified():
    assert identify_law(congress=81, doc_type="Chapter", doc_number="9", public_private="public", enacted=None) is None


@pytest.mark.parametrize(
    ("level", "value", "text", "expected"),
    [
        ("section", "2", None, "2"),
        ("section", None, "Sec. 12. ", "12"),
        ("section", None, "SECTION 1.", "1"),
        ("section", "101A", None, "101A"),
        ("title", None, "TITLE I—", "I"),
        ("title", "I", "TITLE I—", "I"),
        ("chapter", "1.", None, "1"),
        ("subsection", None, "(a) ", "a"),
        ("paragraph", "1", "(1) ", "1"),
        ("section", None, None, None),
    ],
)
def test_designators(level, value, text, expected):
    assert designator(level, value, text) == expected


def test_segments_follow_the_plaw_scheme():
    assert segment("division", "A") == "dA"
    assert segment("title", "VIII") == "tVIII"
    assert segment("subtitle", "B") == "stB"
    assert segment("chapter", "1") == "ch1"
    assert segment("subchapter", "II") == "schII"
    assert segment("part", "I") == "ptI"
    assert segment("section", "814") == "s814"
    assert segment("subsection", "e") == "e"


def test_parse_identifier_splits_law_and_path():
    parsed = parse_identifier("/us/pl/104/333/dI/tVIII/s814/e/1")
    assert parsed.law_identifier == "/us/pl/104/333"
    assert parsed.path == "/dI/tVIII/s814/e/1"
    assert parsed.section_num == "814"
    assert parsed.section_identifier == "/us/pl/104/333/dI/tVIII/s814"
    assert parsed.below_section == ("e", "1")


def test_parse_identifier_acts_and_compilations():
    act = parse_identifier("/us/act/1916-08-25/ch408/s1")
    assert act.kind == "act" and act.enacted == datetime.date(1916, 8, 25) and act.chapter == 408
    comp = parse_identifier("/us/sComp/83/703/tI/ch1./s1/a")
    assert comp.kind == "sComp" and comp.section_identifier == "/us/sComp/83/703/tI/ch1./s1"
    assert parse_identifier("/us/usc/t16/s45f") is None
    assert parse_identifier("/us/act/1916-13-45/ch1") is None


def test_stat_pages_are_lower_case():
    page = parse_stat_page("/us/stat/64/B3")
    assert page.volume == 64 and page.page == "b3"
    assert page.pdf == "https://www.govinfo.gov/link/statute/64/b3"
    assert normalize_page("A 12") == "a12"
    assert parse_stat_page("/us/stat/110/3009-1").page == "3009-1"


def test_law_labels():
    assert law_label("pl", 83, 703, 1073, datetime.date(1954, 8, 30)) == "Public Law 83-703"
    assert law_label("pvtl", 81, 375, 29, None) == "Private Law 81-375"
    assert law_label("act", 51, None, 647, datetime.date(1890, 7, 2)) == "Act of July 2, 1890, ch. 647"


def test_roman_chapter_numbers_of_the_first_volumes():
    from ingest.identifiers import parse_doc_number, roman_to_int

    assert roman_to_int("CXLVII") == 147 and roman_to_int("IV") == 4 and roman_to_int("x") == 10
    assert roman_to_int("12") is None and roman_to_int("") is None
    assert parse_doc_number("I") == 1 and parse_doc_number("3]") == 3 and parse_doc_number("[CHAPTER 5") == 5
    identity = identify_law(congress=1, doc_type="Chapter", doc_number="I", public_private="public",
                            enacted=datetime.date(1789, 6, 1))
    assert identity.primary == "/us/act/1789-06-01/ch1"
