"""The accepted-forms table for `parse_citation`. This file is the spec.

No database and no fixtures: `citeparse` is pure (`test_architecture.py`
enforces it), so every form runs in the default `make test`.
"""

import datetime

import pytest

from citeparse import parse_citation

# ------------------------------------------------------------ public laws

PUBLIC_LAWS = [
    ("Pub. L. 104-333", "/us/pl/104/333"),
    ("Pub. L. 104–333", "/us/pl/104/333"),
    ("Pub. L. 104—333", "/us/pl/104/333"),
    ("Pub.L. 104-333", "/us/pl/104/333"),
    ("Pub. L. No. 104-333", "/us/pl/104/333"),
    ("Public Law 118-5", "/us/pl/118/5"),
    ("Public Law No. 118-5", "/us/pl/118/5"),
    ("P.L. 81-740", "/us/pl/81/740"),
    ("P. L. 81-740", "/us/pl/81/740"),
    ("PL 81-740", "/us/pl/81/740"),
    ("pub l 104-333", "/us/pl/104/333"),
    ("pub. l. 104-333.", "/us/pl/104/333"),
    ("(Pub. L. 104-333)", "/us/pl/104/333"),
    ("  Pub. L.   104 - 333  ", "/us/pl/104/333"),
]

SECTIONS_OF_LAWS = [
    ("Pub. L. 104-333, § 814", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333 § 814", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, §814", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, sec. 814", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, Sec. 814.", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, section 814", "/us/pl/104/333/s814"),
    ("Public Law 104-333 § 814", "/us/pl/104/333/s814"),
    ("Pub. L. 104–333, title VIII, § 814(e)(1)", "/us/pl/104/333/s814/e/1"),
    ("Pub. L. 104-333, § 814(e)(1)(B)", "/us/pl/104/333/s814/e/1/B"),
    ("Pub. L. 104-333, § 814 (e)(1)", "/us/pl/104/333/s814/e/1"),
    ("Pub. L. 118–5, div. A, title I, § 101", "/us/pl/118/5/s101"),
    ("Pub. L. 118-5, division A, title I, section 101(a)", "/us/pl/118/5/s101/a"),
    ("section 3 of Public Law 81-740", "/us/pl/81/740/s3"),
    ("§ 3(a) of Pub. L. 81-740", "/us/pl/81/740/s3/a"),
    ("Sec. 3 of the Pub. L. 81-740", "/us/pl/81/740/s3"),
    # A range keeps its first section.
    ("Pub. L. 104-333, §§ 814–816", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, §§ 814-816", "/us/pl/104/333/s814"),
    # The full source-credit form.
    (
        "Pub. L. 104–333, div. I, title VIII, § 814(e)(1), Nov. 12, 1996, 110 Stat. 4196",
        "/us/pl/104/333/s814/e/1",
    ),
    ("Pub. L. 95–625, § 314, Nov. 10, 1978, 92 Stat. 3479", "/us/pl/95/625/s314"),
    ("Pub. L. 104-333, § 814, as amended", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, § 814, as added by Pub. L. 105-1", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, § 814 (1996)", "/us/pl/104/333/s814"),
    ("Pub. L. 104-333, § 814 note", "/us/pl/104/333/s814"),
    # A hierarchy level with no section keeps the level.
    ("Pub. L. 104-333, title VIII", "/us/pl/104/333/tVIII"),
    ("Pub. L. 118-5, div. A, title I", "/us/pl/118/5/dA/tI"),
]

PRIVATE_LAWS = [
    ("Private Law 81-375", "/us/pvtl/81/375"),
    ("Priv. L. 81-375", "/us/pvtl/81/375"),
    ("Pvt. L. 81-375", "/us/pvtl/81/375"),
    ("Private Law 81-375, § 1", "/us/pvtl/81/375/s1"),
    ("Priv. L. No. 81–375", "/us/pvtl/81/375"),
]

# ------------------------------------------------------------------- acts

ACTS = [
    ("Act of Aug. 25, 1916, ch. 408", "/us/act/1916-08-25/ch408"),
    ("Act of August 25, 1916, ch. 408", "/us/act/1916-08-25/ch408"),
    ("act of Aug. 25, 1916 (ch. 408)", "/us/act/1916-08-25/ch408"),
    ("the Act of June 25, 1948, ch. 645, § 1", "/us/act/1948-06-25/ch645/s1"),
    ("Aug. 30, 1954, ch. 1073, § 2", "/us/act/1954-08-30/ch1073/s2"),
    ("Aug. 30, 1954, ch. 1073, § 2(a)", "/us/act/1954-08-30/ch1073/s2/a"),
    ("Aug. 30, 1950, ch. 823, 64 Stat. 563", "/us/act/1950-08-30/ch823"),
    ("Aug. 30, 1950, ch. 823, § 3, 64 Stat. 564", "/us/act/1950-08-30/ch823/s3"),
    ("Sept. 8, 1916, ch. 463", "/us/act/1916-09-08/ch463"),
    ("Sep. 8, 1916, ch. 463", "/us/act/1916-09-08/ch463"),
    ("July 2, 1890, ch. 647", "/us/act/1890-07-02/ch647"),
    ("July 2, 1890, chapter 647, title I", "/us/act/1890-07-02/ch647/tI"),
    ("1954-08-30, ch. 1073", "/us/act/1954-08-30/ch1073"),
]

# --------------------------------------------------------------- Stat. pages

STAT_PAGES = [
    ("110 Stat. 4196", "/us/stat/110/4196"),
    ("110 Stat 4196", "/us/stat/110/4196"),
    ("110 STAT. 4196", "/us/stat/110/4196"),
    ("64 Stat. 563", "/us/stat/64/563"),
    ("64 Stat. 563, 564", "/us/stat/64/563"),
    ("110 Stat. 4196 (1996)", "/us/stat/110/4196"),
    ("64 Stat. A12", "/us/stat/64/a12"),
    ("64 Stat. B3", "/us/stat/64/b3"),
    ("113 Stat. 1501A-594", "/us/stat/113/1501a-594"),
    ("113 Stat. 1501A–594", "/us/stat/113/1501a-594"),
]

CHAPTERS_ON_PAGES = [
    ("ch. 823, 64 Stat. 563", "/us/stat/64/563"),
    ("64 Stat. 563, ch. 823", "/us/stat/64/563"),
    ("chapter 823, 64 Stat. 563", "/us/stat/64/563"),
    ("ch. 823, 64 Stat. 563, § 3", "/us/stat/64/563"),
]

# --------------------------------------------------------------- identifiers

PATHS = [
    ("/us/pl/81/740/s3", "/us/pl/81/740/s3"),
    ("us/pl/81/740/s3/", "/us/pl/81/740/s3"),
    ("/us/pl/104/333/dI/tVIII/s814/e/1", "/us/pl/104/333/s814/e/1"),
    ("/us/pl/118/5/dA/tI", "/us/pl/118/5/dA/tI"),
    ("/us/pvtl/81/375", "/us/pvtl/81/375"),
    ("/us/act/1950-08-30/ch823/s3", "/us/act/1950-08-30/ch823/s3"),
    ("us/act/1954-08-30/ch1073", "/us/act/1954-08-30/ch1073"),
    ("/us/stat/64/563", "/us/stat/64/563"),
    ("/us/stat/64/B3", "/us/stat/64/b3"),
    ("/us/sComp/83/703/tI/ch1./s1", "/us/sComp/83/703/tI/ch1./s1"),
    ("/us/sComp/83/703/tI/ch1./s1/a", "/us/sComp/83/703/tI/ch1./s1/a"),
    ("/us/sComp/51/647", "/us/sComp/51/647"),
    ("/us/usc/t16/s45f/c/5", "/us/usc/t16/s45f/c/5"),
    ("/us/usc/t42/s2011", "/us/usc/t42/s2011"),
]

# ------------------------------------------------------------------ US Code

USC = [
    ("43 U.S.C. 1701", "/us/usc/t43/s1701"),
    ("43 USC 1701", "/us/usc/t43/s1701"),
    ("43 U.S.C. § 1701", "/us/usc/t43/s1701"),
    ("43 usc 1701(a)", "/us/usc/t43/s1701/a"),
    ("16 USC 45f(c)(5)", "/us/usc/t16/s45f/c/5"),
    ("16 U.S.C. § 45f(c)(5)", "/us/usc/t16/s45f/c/5"),
    ("(11 U.S.C. 523)", "/us/usc/t11/s523"),
    ("42 USC 2000e-2", "/us/usc/t42/s2000e-2"),
    ("section 523 of title 11", "/us/usc/t11/s523"),
    ("Section 14123(a)(2), 49 U.S.C.", "/us/usc/t49/s14123/a/2"),
    ("5 U.S.C. App. 3", "/us/usc/t5a/s3"),
    ("42 U.S.C. 2011 note", "/us/usc/t42/s2011"),
    ("title 11", "/us/usc/t11"),
    ("11 usc", "/us/usc/t11"),
]

REJECTED = [
    "",
    "   ",
    "garbage",
    "523",
    "ch. 1073",
    "Aug. 30, 1954",
    "2023-01-01",
    "Pub. L. 104-333 and other words",
    "Stat. 4196",
    "Pub. L. 104",
    "section 814",
    "title VIII",
]


@pytest.mark.parametrize(
    ("text", "identifier"),
    PUBLIC_LAWS + SECTIONS_OF_LAWS + PRIVATE_LAWS + ACTS + STAT_PAGES + CHAPTERS_ON_PAGES + PATHS + USC,
)
def test_accepted_form(text, identifier):
    parsed = parse_citation(text)
    assert parsed is not None, text
    assert parsed.identifier == identifier


@pytest.mark.parametrize("text", REJECTED)
def test_rejected_form(text):
    assert parse_citation(text) is None


def test_the_table_is_large_enough():
    forms = PUBLIC_LAWS + SECTIONS_OF_LAWS + PRIVATE_LAWS + ACTS + STAT_PAGES + CHAPTERS_ON_PAGES + PATHS + USC
    assert len(forms) >= 60


# ----------------------------------------------------------------- the parts


def test_kinds():
    assert parse_citation("Pub. L. 104-333").kind == "pl"
    assert parse_citation("Private Law 81-375").kind == "pvtl"
    assert parse_citation("Act of Aug. 25, 1916, ch. 408").kind == "act"
    assert parse_citation("110 Stat. 4196").kind == "stat"
    assert parse_citation("ch. 823, 64 Stat. 563").kind == "stat"
    assert parse_citation("/us/sComp/83/703/tI/ch1./s1").kind == "sComp"
    assert parse_citation("43 U.S.C. 1701").kind == "usc"


def test_a_public_law_carries_its_numbers_and_label():
    parsed = parse_citation("Pub. L. 104–333, title VIII, § 814(e)(1)")
    assert parsed.law_identifier == "/us/pl/104/333"
    assert (parsed.congress, parsed.number) == (104, 333)
    assert parsed.section_num == "814"
    assert parsed.subdivisions == ("e", "1")
    assert parsed.section_identifier == "/us/pl/104/333/s814"
    assert parsed.below_section == "/e/1"
    assert parsed.hierarchy == ("tVIII",)
    assert parsed.label == "Public Law 104-333, section 814(e)(1)"


def test_subdivision_case_is_kept():
    assert parse_citation("Pub. L. 104-333, § 814(e)(1)(B)").subdivisions == ("e", "1", "B")
    assert parse_citation("16 USC 45f(c)(5)(A)").identifier == "/us/usc/t16/s45f/c/5/A"


def test_the_hierarchy_is_read_and_dropped_from_a_section():
    parsed = parse_citation("Pub. L. 118–5, div. A, title I, § 101")
    assert parsed.hierarchy == ("dA", "tI")
    assert parsed.identifier == "/us/pl/118/5/s101"
    assert parse_citation("/us/pl/104/333/dI/tVIII/s814/e/1").hierarchy == ("dI", "tVIII")


def test_a_stat_page_beside_a_law_is_carried_not_resolved():
    parsed = parse_citation("Pub. L. 104-333, § 814, 110 Stat. 4196")
    assert parsed.kind == "pl"
    assert parsed.identifier == "/us/pl/104/333/s814"
    assert parsed.stat_page == "/us/stat/110/4196"
    assert (parsed.volume, parsed.page) == (110, "4196")


def test_an_act_carries_its_date_and_chapter():
    parsed = parse_citation("Aug. 30, 1954, ch. 1073, § 2")
    assert parsed.enacted == datetime.date(1954, 8, 30)
    assert parsed.chapter == 1073
    assert parsed.law_identifier == "/us/act/1954-08-30/ch1073"
    assert parsed.label == "Act of August 30, 1954, ch. 1073, section 2"


def test_an_impossible_date_is_not_a_citation():
    assert parse_citation("Feb. 30, 1954, ch. 1073") is None
    assert parse_citation("/us/act/1954-13-01/ch1") is None


def test_a_chapter_on_a_page_names_the_page_and_carries_the_chapter():
    parsed = parse_citation("ch. 823, 64 Stat. 563")
    assert parsed.kind == "stat"
    assert parsed.identifier == "/us/stat/64/563"
    assert parsed.chapter == 823
    assert parsed.law_identifier is None
    assert parsed.label == "ch. 823, 64 Stat. 563"
    with_section = parse_citation("ch. 823, 64 Stat. 563, § 3")
    assert with_section.section_num == "3"
    assert with_section.label == "ch. 823, 64 Stat. 563, section 3"


def test_stat_pages_are_lower_case_in_the_identifier_and_as_printed_in_the_label():
    parsed = parse_citation("64 Stat. A12")
    assert parsed.identifier == "/us/stat/64/a12"
    assert parsed.page == "a12"
    assert parsed.label == "64 Stat. A12"
    assert parsed.volume == 64


def test_a_note_is_recorded():
    parsed = parse_citation("Pub. L. 104-333, § 814 note")
    assert parsed.note is True
    assert parsed.label == "Public Law 104-333, section 814 note"
    assert parse_citation("42 U.S.C. 2011 note").note is True


def test_a_us_code_citation_carries_the_title_and_the_section():
    parsed = parse_citation("16 USC 45f(c)(5)")
    assert parsed.usc_title == "16"
    assert parsed.section_num == "45f"
    assert parsed.section_identifier == "/us/usc/t16/s45f"
    assert parsed.label == "16 U.S.C. 45f(c)(5)"
    assert parsed.law_identifier is None
    assert parse_citation("5 U.S.C. App. 3").label == "5 U.S.C. App. 3"
    assert parse_citation("title 11").label == "Title 11, United States Code"


def test_a_compilation_path_carries_its_section():
    parsed = parse_citation("/us/sComp/83/703/tI/ch1./s1/a")
    assert parsed.law_identifier == "/us/sComp/83/703"
    assert parsed.section_num == "1"
    assert parsed.subdivisions == ("a",)
    assert parsed.section_identifier == "/us/sComp/83/703/tI/ch1./s1"


def test_a_typed_identifier_round_trips():
    for identifier in ("/us/pl/81/740/s3", "/us/act/1950-08-30/ch823/s3", "/us/stat/64/563", "/us/usc/t16/s45f/c/5"):
        assert parse_citation(identifier).identifier == identifier
