"""`parse_comp` over the four COMPS fixtures: prefix, currency, units,
identifiers kept as GPO wrote them, US Code references, the per-title file."""

import datetime
import json

import pytest

from ingest.comps import normalize_pl, parse_comp
from tests.conftest import COMPS_FIXTURES


def _parse(name: str):
    xml = (COMPS_FIXTURES / name).read_text(encoding="utf-8")
    summary_path = COMPS_FIXTURES / (name.replace("-slice", "").replace(".xml", ".summary.json"))
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    return parse_comp(xml, summary=summary)


@pytest.fixture(scope="module")
def atomic():
    return _parse("COMPS-1630-slice.xml")


@pytest.fixture(scope="module")
def fdc():
    return _parse("COMPS-973-slice.xml")


@pytest.fixture(scope="module")
def sherman():
    return _parse("COMPS-3055.xml")


@pytest.fixture(scope="module")
def ssa():
    return _parse("COMPS-8755-slice.xml")


def test_the_four_fixtures_parse(atomic, fdc, sherman, ssa):
    for record in (atomic, fdc, sherman, ssa):
        assert record.units and record.sections
        assert record.content_hash and len(record.content_hash) == 64
        assert all(u.identifier.startswith(record.identifier_prefix + "/") for u in record.units)
        assert all(u.xml is not None and u.text for u in record.sections)
        assert all(u.xml is None for u in record.units if u.level != "section")


def test_atomic_energy_act_meta(atomic):
    assert atomic.identifier_prefix == "/us/sComp/83/703"
    assert atomic.law_congress == 83 and atomic.law_number == 703 and atomic.congress == 83
    assert atomic.file_id == "1630" and atomic.package_id == "COMPS-1630"
    assert atomic.current_through_pl == "118-67"
    assert atomic.current_through_date == datetime.date(2024, 7, 9)
    assert atomic.approved_date == datetime.date(1954, 8, 30)
    assert atomic.display_title == "Atomic Energy Act of 1954"
    assert "Atomic Energy Act of 1954" in atomic.short_titles
    assert atomic.short_titles == ["Atomic Energy Act of 1954"]
    assert atomic.title.startswith("To amend the Atomic Energy Act of 1946")
    assert atomic.govinfo_last_modified == datetime.datetime(2026, 9, 4, 12, 8, 6, tzinfo=datetime.timezone.utc)
    assert atomic.partial_of is None
    assert atomic.law_identifier_candidate == "/us/pl/83/703"


def test_atomic_energy_act_first_section(atomic):
    first = atomic.sections[0]
    assert first.identifier == "/us/sComp/83/703/tI/ch1./s1"
    assert first.level == "section" and first.num == "1" and first.section_num == "1"
    assert first.heading == "Declaration.—"
    assert [a["identifier"] for a in first.ancestors] == ["/us/sComp/83/703/tI", "/us/sComp/83/703/tI/ch1."]
    assert [a["level"] for a in first.ancestors] == ["title", "chapter"]
    assert first.ancestors[1]["num"] == "1."
    assert first.parent_identifier == "/us/sComp/83/703/tI/ch1."
    assert first.depth == 3
    assert 'identifier="/us/sComp/83/703/tI/ch1./s1/a"' in first.xml
    assert 'identifier="/us/sComp/83/703/tI/ch1./s1/b"' in first.xml
    assert first.text.startswith("Section 1. Declaration.— Atomic energy is capable")
    assert first.usc_refs == ["/us/usc/t42/s2011"]


def test_atomic_energy_act_hierarchy(atomic):
    top = [u for u in atomic.units if u.depth == 1]
    assert [(u.level, u.identifier, u.num) for u in top] == [("title", "/us/sComp/83/703/tI", "I")]
    chapters = [u for u in atomic.units if u.level == "chapter"]
    assert chapters[0].identifier == "/us/sComp/83/703/tI/ch1." and chapters[0].num == "1."
    assert chapters[0].heading == "DECLARATION, FINDINGS, AND PURPOSE"
    assert chapters[0].parent_identifier == "/us/sComp/83/703/tI"
    assert [u.seq for u in atomic.units] == list(range(1, len(atomic.units) + 1))
    # The slice keeps the first 8 `section` elements; two of them carry no identifier.
    assert len(atomic.sections) == 6 and atomic.unidentified_sections == 2


def test_fdc_act(fdc):
    assert fdc.identifier_prefix == "/us/sComp/75/675"
    assert fdc.file_id == "973" and fdc.current_through_pl == "119-75"
    first = fdc.sections[0]
    assert first.identifier == "/us/sComp/75/675/chI/s1"
    assert first.usc_refs == ["/us/usc/t21/s301"]
    assert [a["identifier"] for a in first.ancestors] == ["/us/sComp/75/675/chI"]
    assert fdc.short_titles[0] == "Federal Food, Drug, and Cosmetic Act"
    assert "21st Century Cures Act" in fdc.short_titles


def test_sherman_act_before_public_law_numbering(sherman):
    assert sherman.identifier_prefix == "/us/sComp/51/647"
    assert sherman.law_congress == 51 and sherman.law_number == 647
    assert sherman.law_identifier_candidate is None
    assert sherman.doc_number == "ch647"
    assert sherman.citable_as == ["Chapter 647 of the 51st Congress, as amended", "26 Stat. 209, as amended"]
    assert sherman.current_through_pl == "108-237"
    assert sherman.current_through_date == datetime.date(2004, 6, 22)
    assert len(sherman.sections) == 8
    assert [u.identifier for u in sherman.units] == [f"/us/sComp/51/647/s{n}" for n in range(1, 9)]
    assert sherman.unidentified_sections == 1
    assert all(u.depth == 1 and u.ancestors == [] for u in sherman.units)
    # The short-title paragraph stays in the document, not in any unit.
    assert "this Act may be cited as" in sherman.xml
    assert not any("this Act may be cited as" in (u.text or "") for u in sherman.units)
    assert sherman.sections[6].usc_refs == ["/us/usc/t15/s6a"]


def test_social_security_act_title_ii(ssa):
    assert ssa.identifier_prefix == "/us/sComp/74/271"
    assert ssa.file_id == "8755" and ssa.doc_number == "ch531"
    assert ssa.partial_of == "II"
    assert ssa.current_through_pl == "119-77"
    assert ssa.current_through_date == datetime.date(2026, 2, 10)
    first = ssa.sections[0]
    assert first.identifier == "/us/sComp/74/271/tII/s201"
    assert first.usc_refs == ["/us/usc/t42/s401"]
    assert first.section_num == "201"
    assert first.heading.startswith("federal old-age and survivors insurance trust fund")
    assert ssa.short_titles[0].startswith("Social Security Act-TITLE II")
    assert "Social Security Act" in ssa.short_titles


def test_a_duplicate_section_identifier_is_kept_once(ssa):
    xml = (COMPS_FIXTURES / "COMPS-8755-slice.xml").read_text(encoding="utf-8")
    first = xml.index('<section identifier="/us/sComp/74/271/tII/s201"')
    end = xml.index("</section>", first) + len("</section>")
    doubled = xml[:end] + xml[first:end] + xml[end:]
    record = parse_comp(doubled, summary=None)
    assert [u.identifier for u in record.sections].count("/us/sComp/74/271/tII/s201") == 1
    assert record.duplicate_identifiers == ["/us/sComp/74/271/tII/s201"]
    assert record.package_id == "COMPS-8755"


def test_normalize_pl():
    assert normalize_pl("118–67") == "118-67"
    assert normalize_pl("P.L. 118–67") == "118-67"
    assert normalize_pl("118-067") == "118-67"
    assert normalize_pl(None) is None
    assert normalize_pl("no law here") is None


def test_summary_fallbacks_and_shapes():
    xml = (COMPS_FIXTURES / "COMPS-3055.xml").read_text(encoding="utf-8")
    without = parse_comp(xml, summary=None)
    assert without.package_id == "COMPS-3055" and without.display_title == "SHERMAN ACT"
    assert without.title is None and without.govinfo_last_modified is None
    assert without.short_titles == ["Sherman Act"]
    with_dict = parse_comp(xml, summary={"packageId": "COMPS-3055", "amendedThrough": {"publicLaw": "237", "congress": "108", "enacted": "2004-06-22"}})
    assert with_dict.current_through_pl == "108-237"
    stripped = xml.replace("<currentThroughPublicLaw>108–237</currentThroughPublicLaw>", "").replace(
        "<currentThroughPublicLaw>P.L. 108–237</currentThroughPublicLaw>", ""
    ).replace('<date date="2004-06-22">June 22, 2004</date>', "")
    from_summary = parse_comp(stripped, summary={"amendedThrough": [{"publicLaw": "237", "congress": "108", "enacted": "2004-06-22"}]})
    assert from_summary.current_through_pl == "108-237"
    assert from_summary.current_through_date == datetime.date(2004, 6, 22)
    assert any("summary" in w for w in from_summary.warnings)


def test_not_a_compilation():
    with pytest.raises(ValueError):
        parse_comp('<pLaw xmlns="http://schemas.gpo.gov/xml/uslm"><meta/></pLaw>', summary=None)
