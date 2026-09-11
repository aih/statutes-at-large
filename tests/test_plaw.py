"""The PLAW bulk-data parser and loader over the four whole laws in
`tests/fixtures/plaw/`: GPO's identifiers read rather than assigned, the rule
fallback where a level has none, replacement of the volume-derived copy,
precedence between the two sources, and the served answers over PLAW-derived
units."""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from db.base import Base, make_engine
from ingest.plaw import (
    MIXED_PROVENANCE,
    compare_identifiers,
    identifiers_by_level,
    load_congress,
    package_id,
    parse_package_id,
    parse_plaw,
)
from ingest.statute import parse_volume
from tests.conftest import CITATIONS_SLICE, CLASSIFICATIONS_FIXTURES, FIXTURES, PLAW_FILES, PLAW_FIXTURES


def read(name: str) -> str:
    return (PLAW_FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pl22():
    return parse_plaw(read("PLAW-118publ22.xml"), package="PLAW-118publ22")


@pytest.fixture(scope="module")
def pl34():
    return parse_plaw(read("PLAW-118publ34.xml"), package="PLAW-118publ34")


@pytest.fixture(scope="module")
def pl1():
    return parse_plaw(read("PLAW-118publ1.xml"))


@pytest.fixture(scope="module")
def pl119():
    return parse_plaw(read("PLAW-119publ1.xml"))


# ---------------------------------------------------------------- the parser


def test_names():
    assert package_id(118, 22) == "PLAW-118publ22" and package_id(118, 1, "pvtl") == "PLAW-118pvtl1"
    assert parse_package_id("PLAW-118publ22.xml") == (118, "pl", 22)
    assert parse_package_id("PLAW-118pvtl3") == (118, "pvtl", 3)
    assert parse_package_id("STATUTE-137.xml") is None


def test_the_law_is_read_from_meta(pl22):
    assert pl22.identifier == "/us/pl/118/22" and pl22.kind == "pl"
    assert pl22.congress == 118 and pl22.number == 22 and pl22.chapter is None
    assert pl22.aliases == ["/us/pl/118/22"]
    assert pl22.enacted.isoformat() == "2023-11-17"
    assert pl22.doc_type == "An Act"
    assert pl22.official_title == "Making further continuing appropriations for fiscal year 2024, and for other purposes."
    assert pl22.short_titles[0] == "Further Continuing Appropriations and Other Extensions Act, 2024"
    assert pl22.source_collection == "PLAW" and pl22.source_package == "PLAW-118publ22"
    assert pl22.provenance_identifiers == "gpo-uslm" and pl22.identifiers_assigned == {}
    assert pl22.seq_in_volume == 22
    assert pl22.warnings == []


def test_identifiers_are_gpos_not_assigned(pl22):
    """Every unit identifier is the one written in the file; levels below a
    section keep theirs inside the section's XML."""
    assert [u.identifier for u in pl22.units][:9] == [
        "/us/pl/118/22/s1", "/us/pl/118/22/s2", "/us/pl/118/22/s3",
        "/us/pl/118/22/dA", "/us/pl/118/22/dA/s101",
        "/us/pl/118/22/dB", "/us/pl/118/22/dB/tI", "/us/pl/118/22/dB/tI/s101", "/us/pl/118/22/dB/tI/s102",
    ]
    assert len(pl22.units) == 29 and len(pl22.sections) == 19
    s102 = next(u for u in pl22.units if u.identifier == "/us/pl/118/22/dB/tI/s102")
    assert s102.level == "section" and s102.num == "102" and s102.section_num == "102"
    assert s102.parent_identifier == "/us/pl/118/22/dB/tI" and s102.depth == 3
    assert [a["identifier"] for a in s102.ancestors] == ["/us/pl/118/22/dB", "/us/pl/118/22/dB/tI"]
    assert 'identifier="/us/pl/118/22/dB/tI/s102/c/2/A/i"' in s102.xml
    assert s102.xml.startswith("<section") and len(s102.content_hash) == 64
    title = next(u for u in pl22.units if u.identifier == "/us/pl/118/22/dB/tI")
    assert title.level == "title" and title.num == "I" and title.xml is None


def test_the_section_number_is_the_identifier_segment(pl34):
    assert [(u.identifier, u.section_num) for u in pl34.units if u.level == "section"][:3] == [
        ("/us/pl/118/34/s1", "1"), ("/us/pl/118/34/tI/s101", "101"), ("/us/pl/118/34/tI/s102", "102"),
    ]
    assert pl34.units[0].heading == "SHORT TITLE; TABLE OF CONTENTS."


def test_quoted_sections_are_not_units(pl22):
    """Nine `<section>` elements sit inside `quotedContent` (amendments to
    other acts); they stay in the enclosing section's XML."""
    assert pl22.sections_in_quoted_content == 9
    units = {u.identifier for u in pl22.units}
    assert "/us/pl/118/22/dB/tI/s102" in units
    assert not any("/s2101" in u for u in units)


def test_pages_come_from_the_markers(pl22, pl34):
    assert pl22.citation == "137 Stat. 112" and pl22.stat_volume == 137
    assert pl22.stat_page_first == "112" and pl22.stat_page_last == "124"
    assert pl22.page_units["112"] is None
    assert pl22.page_units["113"] == "/us/pl/118/22/dA/s101"
    assert pl22.page_units["115"] == "/us/pl/118/22/dB/tI/s102"
    s102 = next(u for u in pl22.units if u.identifier == "/us/pl/118/22/dB/tI/s102")
    assert s102.first_page == "114" and s102.pages == ["115", "116", "117", "118", "119"]
    assert pl34.citation == "137 Stat. 1112" and pl34.stat_page_last == "1116"
    assert sorted(pl34.page_units) == ["1112", "1113", "1114", "1115", "1116"]


def test_an_unidentified_section_is_filled_in_by_rule(pl1):
    """Public Law 118-1 is one unnumbered inline section with no identifier
    anywhere in the file: cited as section 1, stamped by rules-1.0, and the
    provenance says so."""
    assert pl1.identifier == "/us/pl/118/1" and pl1.doc_type == "Joint Resolution"
    assert [u.identifier for u in pl1.units] == ["/us/pl/118/1/s1"]
    assert pl1.units[0].num == "1" and pl1.units[0].text.startswith("That the Congress disapproves")
    assert 'identifier="/us/pl/118/1/s1"' in pl1.xml
    assert pl1.identifiers_assigned == {"section": 1}
    assert pl1.provenance_identifiers == MIXED_PROVENANCE == "gpo-uslm+rules-1.0"
    assert pl1.citation == "137 Stat. 3" and pl1.page_units == {"3": None}


def test_a_119th_congress_law(pl119):
    assert pl119.identifier == "/us/pl/119/1" and pl119.stat_volume == 139
    assert pl119.citation == "139 Stat. 3" and pl119.stat_page_last == "5"
    assert [u.identifier for u in pl119.units] == ["/us/pl/119/1/s1", "/us/pl/119/1/s2", "/us/pl/119/1/s3"]
    assert pl119.short_titles == ["Laken Riley Act"]
    assert pl119.page_units["4"] == "/us/pl/119/1/s3"


def test_a_private_law_or_a_wrong_root_is_refused():
    with pytest.raises(ValueError):
        parse_plaw("<statuteCompilation xmlns='http://schemas.gpo.gov/xml/uslm'/>")
    text = read("PLAW-118publ34.xml").replace("<publicPrivate>public</publicPrivate>", "<publicPrivate>private</publicPrivate>")
    private = parse_plaw(text, package="PLAW-118pvtl34")
    assert private.kind == "pvtl" and private.identifier == "/us/pvtl/118/34"
    assert private.units[0].identifier == "/us/pl/118/34/s1"
    assert any("is not under /us/pvtl/118/34" in w for w in private.warnings)


def test_the_running_head_wins_over_a_wrong_citable_as():
    """Three bulk-data files (116-131, 117-121, 118-79) cite `131 Stat.` under
    a running head that says the printed volume; the running head is used."""
    text = read("PLAW-118publ34.xml").replace("<citableAs>137 Stat. 1112</citableAs>", "<citableAs>131 Stat. 1112</citableAs>")
    law = parse_plaw(text)
    assert law.stat_volume == 137 and law.citation == "137 Stat. 1112" and law.stat_page_first == "1112"
    assert law.warnings == ["citableAs says 131 Stat.; the running head says 137 STAT. and is used"]
    no_head = "".join(line for line in text.splitlines(keepends=True) if "STAT. ?>" not in line)
    assert parse_plaw(no_head).stat_volume == 131


# ------------------------------------------------------------ the comparison


def test_rules_and_gpo_agree_on_the_two_laws_in_both_sources(pl22, pl34):
    volume = parse_volume(FIXTURES / "statute-137-slice.xml")
    for record in (pl22, pl34):
        old = next(law for law in volume.laws if law.identifier == record.identifier)
        comparison = compare_identifiers(old.xml, record.xml)
        assert set(comparison) >= {"section", "subsection", "paragraph"}
        assert all(c["rules_only"] == [] and c["gpo_only"] == [] for c in comparison.values()), comparison
    assert comparison["section"]["agree"] == 9  # pl34


def test_the_comparison_lists_what_differs(pl34):
    changed = pl34.xml.replace('identifier="/us/pl/118/34/tI/s103"', 'identifier="/us/pl/118/34/tI/s103a"')
    comparison = compare_identifiers(pl34.xml, changed)
    assert comparison["section"] == {"agree": 8, "rules_only": ["/us/pl/118/34/tI/s103"], "gpo_only": ["/us/pl/118/34/tI/s103a"]}
    assert comparison["title"] == {"agree": 2, "rules_only": [], "gpo_only": []}
    levels = identifiers_by_level(pl34.xml)
    assert len(levels["section"]) == 9 and len(levels["subsection"]) == 36


# -------------------------------------------------------------- the loader


@pytest.fixture(scope="module")
def fresh():
    """A database with the volume-137 slice and the indexes, before any PLAW
    load, plus a session factory over it."""
    from ingest.citations import load_citations
    from ingest.classifications import DirectorySource, load_classifications
    from ingest.load import load_volume

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        load_volume(session, FIXTURES / "statute-137-slice.xml")
        load_citations(session, [CITATIONS_SLICE], revision="fixture")
        load_classifications(session, DirectorySource(CLASSIFICATIONS_FIXTURES))
    return factory


def _decisions(factory, identifiers):
    from api.alternatives import alternatives_for
    from api.currency import amended_for_unit
    from storage.postgres import PostgresRepository

    out = {}
    with factory() as session:
        repo = PostgresRepository(session)
        for identifier in identifiers:
            result = repo.get_unit(identifier)
            amended = amended_for_unit(repo, result)
            out[identifier] = (
                result.served_identifier,
                result.resolution,
                dataclasses.asdict(amended),
                [a.model_dump() for a in alternatives_for(repo, result)],
            )
    return out


WATCHED = ["/us/pl/118/22/s101", "/us/pl/118/22/s2", "/us/pl/118/22/s3", "/us/pl/118/34/s1", "/us/pl/118/34/tI/s102"]


def test_a_plaw_load_replaces_the_volume_copy_and_keeps_the_answers(fresh):
    from db.models import Comp, Law

    before = _decisions(fresh, WATCHED)
    assert before["/us/pl/118/22/s101"][0] == "/us/pl/118/22/dA/s101"
    assert before["/us/pl/118/34/s1"][2]["status"] == "no_record"
    with fresh() as session:
        old = session.scalars(select(Law).where(Law.identifier == "/us/pl/118/22")).one()
        assert old.source_collection == "STATUTE" and old.provenance_identifiers == "rules-1.0"
        session.add(Comp(file_id="test-22", package_id="COMPS-test-22", identifier_prefix="/us/sComp/118/22",
                         law_congress=118, law_number=22, law_id=old.id, short_titles=[]))
        session.commit()
        files = ((p.name, p.read_text(encoding="utf-8")) for p in PLAW_FILES if "PLAW-118" in p.name)
        report = load_congress(session, 118, files=files)
    assert (report.files, report.laws_loaded, report.laws_new, report.laws_replaced_statute, report.laws_replaced_plaw) == (3, 3, 1, 2, 0)
    assert report.laws_failed == 0 and report.first_law == "/us/pl/118/1" and report.last_law == "/us/pl/118/34"
    assert report.units == 41 and report.sections == 29 and report.sections_in_quoted_content_skipped == 9
    assert report.identifiers_assigned == {"section": 1} and report.laws_with_assigned_identifiers == ["/us/pl/118/1"]
    assert report.provenance == {"gpo-uslm": 2, "gpo-uslm+rules-1.0": 1}
    assert report.comparison["laws_compared"] == 2 and report.comparison["laws"] == []
    assert report.comparison["by_level"]["section"] == {"agree": 28, "rules_only": 0, "gpo_only": 0}
    assert report.stat_volumes == [137]
    with fresh() as session:
        new = session.scalars(select(Law).where(Law.identifier == "/us/pl/118/22")).one()
        assert new.id != old.id and new.source_collection == "PLAW" and new.source_package == "PLAW-118publ22"
        assert new.provenance_identifiers == "gpo-uslm" and new.provenance_text == "gpo-uslm"
        assert session.scalars(select(Law.source_collection).where(Law.identifier == "/us/pl/118/3")).one() == "STATUTE"
        assert session.scalars(select(Comp.law_id).where(Comp.file_id == "test-22")).one() == new.id
        from db.models import SourceCheck

        check = session.scalars(select(SourceCheck).where(SourceCheck.collection == "PLAW")).one()
        assert check.ok and check.newest_package == "PLAW-118publ34" and check.packages_seen == 3
        assert check.new_packages == ["PLAW-118publ1", "PLAW-118publ22", "PLAW-118publ34"]
    after = _decisions(fresh, WATCHED)
    assert after == before


def test_a_volume_load_does_not_overwrite_a_plaw_law(fresh):
    """Precedence (ADR-0011): re-loading the volume leaves the two PLAW-derived
    laws alone and reports them; a second PLAW load replaces its own copy."""
    from db.models import Law
    from ingest.load import load_volume

    with fresh() as session:
        report = load_volume(session, FIXTURES / "statute-137-slice.xml")
        assert report.laws_kept_from_plaw == ["/us/pl/118/22", "/us/pl/118/34"]
        assert report.laws_loaded == 1 and report.laws_replaced == 1
        rows = session.execute(select(Law.identifier, Law.source_collection).where(Law.congress == 118).order_by(Law.number)).all()
        assert rows == [("/us/pl/118/1", "PLAW"), ("/us/pl/118/3", "STATUTE"), ("/us/pl/118/22", "PLAW"), ("/us/pl/118/34", "PLAW")]
        again = load_congress(session, 118, files=[("PLAW-118publ34.xml", read("PLAW-118publ34.xml"))], record_check=False)
        assert (again.laws_new, again.laws_replaced_statute, again.laws_replaced_plaw) == (0, 0, 1)
        assert again.comparison["laws_compared"] == 0


def test_a_re_load_compares_against_the_volume_file_on_disk(fresh, tmp_path):
    """With `volumes_dir`, the comparison reads the volume file, so a re-load
    after the volume-derived copy is gone still reports the agreement."""
    (tmp_path / "STATUTE-137.xml").write_bytes((FIXTURES / "statute-137-slice.xml").read_bytes())
    with fresh() as session:
        report = load_congress(
            session, 118,
            files=[(p.name, p.read_text(encoding="utf-8")) for p in PLAW_FILES if "PLAW-118" in p.name],
            volumes_dir=tmp_path, record_check=False,
        )
    assert report.laws_replaced_plaw == 3 and report.comparison["laws_compared"] == 2
    assert list(report.comparison["by_level"])[:3] == ["division", "title", "subtitle"]
    assert report.comparison["by_level"]["section"] == {"agree": 28, "rules_only": 0, "gpo_only": 0}


def test_a_file_of_another_congress_or_a_bad_file_is_reported(fresh):
    with fresh() as session:
        report = load_congress(
            session, 119,
            files=[("PLAW-118publ1.xml", read("PLAW-118publ1.xml")), ("PLAW-119publ7.xml", "<pLaw/>"),
                   ("PLAW-119publ1.xml", read("PLAW-119publ1.xml"))],
            record_check=False,
        )
    assert report.laws_loaded == 1 and report.laws_failed == 2
    assert [f["file"] for f in report.failures] == ["PLAW-118publ1.xml", "PLAW-119publ7.xml"]
    assert "118th Congress" in report.failures[0]["error"] and "ValueError" in report.failures[1]["error"]


# ------------------------------------------- the served answers (session db)


def test_resolution_rules_over_plaw_units(repo):
    exact = repo.get_unit("/us/pl/118/22/dB/tI/s102")
    assert exact.resolution == "exact" and exact.law.source_collection == "PLAW"
    assert exact.law.source_package == "PLAW-118publ22" and exact.law.provenance_identifiers == "gpo-uslm"
    assert [p.identifier for p in exact.pages][:2] == ["/us/stat/137/114", "/us/stat/137/115"]
    provision = repo.get_unit("/us/pl/118/22/dB/tI/s102/c/2/A/i")
    assert provision.resolution == "exact" and provision.served_identifier == "/us/pl/118/22/dB/tI/s102"
    assert provision.provision.found and provision.provision.xml.startswith("<clause")
    missing = repo.get_unit("/us/pl/118/22/dB/tI/s102/z")
    assert missing.resolution == "prefix" and missing.provision.found is False
    by_number = repo.get_unit("/us/pl/118/22/s102")
    assert by_number.resolution == "section_number" and by_number.served_identifier == "/us/pl/118/22/dB/tI/s102"
    node = repo.get_unit("/us/pl/118/22/dB/tII/stA")
    assert node.level == "subtitle" and node.text == "" and len(node.children) == 3
    assert repo.get_unit("/us/pl/118/22/dB/tII/stA", wanted="xml").xml == ""
    law = repo.get_unit("/us/pl/118/22")
    assert law.level == "law" and law.text == "" and len(law.children) == 5
    assert repo.get_unit("/us/pl/118/22", wanted="xml").xml == ""
    filled = repo.get_unit("/us/pl/118/1/s1")
    assert filled.resolution == "exact" and filled.law.provenance_identifiers == "gpo-uslm+rules-1.0"
    assert repo.get_law("/us/pl/119/1").section_count == 3


def test_stat_pages_still_answer_for_plaw_derived_laws(repo):
    page = repo.stat_page(137, "112")
    assert [(d.law.identifier, d.starts_here, d.unit_identifier, d.law.source_collection) for d in page.documents] == [
        ("/us/pl/118/22", True, None, "PLAW"),
    ]
    assert repo.stat_page(137, "115").documents[0].unit_identifier == "/us/pl/118/22/dB/tI/s102"
    assert repo.stat_page(137, "1116").documents[0].law.identifier == "/us/pl/118/34"
    assert repo.stat_page(139, "4").documents[0].unit_identifier == "/us/pl/119/1/s3"
    assert repo.stat_page(137, "3").documents[0].law.identifier == "/us/pl/118/1"


def test_law_sources(repo):
    served = repo.law_sources("/us/pl/118/22/dB/tI/s102")
    assert served.served_from == "PLAW" and served.package == "PLAW-118publ22"
    assert served.volume == 137 and served.volume_package == "STATUTE-137" and served.volume_loaded
    assert served.plaw_package == "PLAW-118publ22" and served.plaw_uslm and served.provenance_identifiers == "gpo-uslm"
    volume_only = repo.law_sources("/us/pl/118/3")
    assert volume_only.served_from == "STATUTE" and volume_only.package == "STATUTE-137" and volume_only.volume_loaded
    assert volume_only.plaw_package == "PLAW-118publ3" and volume_only.plaw_uslm
    assert volume_only.provenance_identifiers == "rules-1.0"
    no_volume = repo.law_sources("/us/pl/119/1")
    assert no_volume.served_from == "PLAW" and not no_volume.volume_loaded and no_volume.volume_package == "STATUTE-139"
    old = repo.law_sources("/us/act/1950-08-30/ch823")
    assert old.law_identifier == "/us/pl/81/740" and old.plaw_package is None and not old.plaw_uslm
    private = repo.law_sources("/us/pvtl/111/2")
    assert private is None or (private.plaw_package == "PLAW-111pvtl2" and not private.plaw_uslm)
    assert repo.law_sources("/us/pl/1/1") is None and repo.law_sources("/us/sComp/83/703") is None


def test_the_api_serves_plaw_units(client):
    response = client.get("/api/v1/us/pl/118/22/dB/tI/s102/c/2/A")
    assert response.status_code == 200
    body = response.json()
    assert body["served_identifier"] == "/us/pl/118/22/dB/tI/s102" and body["provision"]["found"] is True
    assert body["provenance"] == {"text": "gpo-uslm", "identifiers": "gpo-uslm", "sha256": body["provenance"]["sha256"]}
    assert body["law"]["source"] == {"collection": "PLAW", "package": "PLAW-118publ22", "granule": None}
    assert body["pages"][0] == {"page": "/us/stat/137/114", "pdf": "https://www.govinfo.gov/link/statute/137/114"}
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    law_xml = client.get("/api/v1/us/pl/118/22?format=xml")
    assert law_xml.headers["content-type"] == "application/json" and law_xml.json()["level"] == "law"
    assert client.get("/api/v1/us/pl/118/22/dB/tI/s102?format=xml").text.startswith("<section")
    assert client.get("/api/v1/us/pl/118/1/s1").json()["provenance"]["identifiers"] == "gpo-uslm+rules-1.0"
    page = client.get("/api/v1/us/stat/137/112").json()
    assert page["documents"][0]["identifier"] == "/us/pl/118/22" and page["documents"][0]["starts_here"] is True
    filled = client.get("/api/v1/us/pl/118/22/s101").json()
    assert filled["served_identifier"] == "/us/pl/118/22/dA/s101" and filled["resolution"] == "section_number"
    assert filled["currency"]["amended"]["status"] == "no_record" and filled["alternatives"] == []
