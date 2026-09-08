"""The citation index (design section 6, `citations`): what the loader
extracts from the `dreamproit/uscode` rows, and what the repository answers
from it. The fixture is 57 verbatim dataset rows
(`scripts/extract_citations_fixture.py`)."""

from __future__ import annotations

import datetime

import pyarrow.parquet as pq
import pytest

from ingest.citations import extract_refs, section_refs
from tests.conftest import CITATIONS_SLICE


@pytest.fixture(scope="module")
def rows() -> dict[str, dict]:
    table = pq.read_table(CITATIONS_SLICE)
    return {row["identifier"]: row for row in table.to_pylist()}


# ------------------------------------------------------------- extraction


def test_the_fixture_is_the_dataset_shape(rows):
    assert len(rows) == 57
    assert {"identifier", "xml", "source_credit", "release_label", "title", "citation", "heading"} <= set(next(iter(rows.values())))
    assert "/us/usc/t16/s45f" in rows and "/us/usc/t16/s1" in rows


def test_source_credit_refs_carry_their_dates(rows):
    refs = extract_refs(rows["/us/usc/t16/s45f"]["xml"])
    credit = [r for r in refs if r.context == "sourceCredit"]
    assert [(r.to_identifier, r.to_law, r.to_section_num, r.to_date) for r in credit] == [
        ("/us/pl/95/625/tIII/s314", "/us/pl/95/625", "314", datetime.date(1978, 11, 10)),
        ("/us/stat/92/3479", None, None, None),
        ("/us/pl/103/437/s6/d/5", "/us/pl/103/437", "6", datetime.date(1994, 11, 2)),
        ("/us/stat/108/4583", None, None, None),
        ("/us/pl/108/447/dE/tI/s139/b", "/us/pl/108/447", "139", datetime.date(2004, 12, 8)),
        ("/us/stat/118/3068", None, None, None),
    ]
    stat = credit[1]
    assert (stat.to_kind, stat.to_volume, stat.to_page) == ("stat", 92, "3479")


def test_a_date_in_prose_is_not_paired_with_a_ref(rows):
    """`section 314 of Pub. L. 95–625` in the References in Text note is
    followed by prose naming the Act of August 25, 1916; that date is not the
    law's."""
    refs = extract_refs(rows["/us/usc/t16/s45f"]["xml"])
    note = [r for r in refs if r.context == "note" and r.to_identifier == "/us/pl/95/625/s314"]
    assert note and all(r.to_date is None for r in note)
    assert all(r.note_topic in ("referencesInText", "codification", "amendments", "shortTitle") or r.note_topic for r in note)


def test_note_context_and_the_full_hierarchy_form(rows):
    """16 U.S.C. § 1's removal note cites `/us/pl/104/333/dI/tVIII/s814/e/1`;
    the index keys it under the law and section 814."""
    refs = extract_refs(rows["/us/usc/t16/s1"]["xml"])
    hit = next(r for r in refs if r.to_identifier == "/us/pl/104/333/dI/tVIII/s814/e/1")
    assert hit.context == "note" and hit.note_topic == "removalDescription"
    assert (hit.to_law, hit.to_path, hit.to_section_num, hit.to_congress, hit.to_number) == (
        "/us/pl/104/333", "/dI/tVIII/s814/e/1", "814", 104, 333)
    assert hit.to_date == datetime.date(1996, 11, 12)
    heading = next(r for r in refs if r.to_identifier == "/us/pl/113/287/s7")
    assert heading.context == "text"


def test_act_refs_take_their_date_from_the_identifier(rows):
    refs = extract_refs(rows["/us/usc/t15/s1"]["xml"])
    sherman = next(r for r in refs if r.to_law == "/us/act/1890-07-02/ch647")
    assert sherman.to_kind == "act" and sherman.to_chapter == 647 and sherman.to_date == datetime.date(1890, 7, 2)
    assert sherman.context == "sourceCredit"


def test_anchors_in_revision_note_tables_are_citations(rows):
    """36 U.S.C. § 70902's revision note is an XHTML table whose citations are
    `<a href>`: `Aug. 30, 1950, ch. 823, § 3` is Public Law 81-740, section 3."""
    section = section_refs(rows["/us/usc/t36/s70902"])
    hit = next(r for r in section.refs if r.to_identifier == "/us/act/1950-08-30/ch823/s3")
    assert hit.context == "note" and hit.to_law == "/us/act/1950-08-30/ch823" and hit.to_section_num == "3"
    assert section.anchors >= 1
    by_date = next(r for r in section.refs if r.to_identifier.startswith("/us/act/1968-10-16/s"))
    assert by_date.parsed and by_date.to_law == "/us/act/1968-10-16" and by_date.to_chapter is None
    assert by_date.to_date == datetime.date(1968, 10, 16) and by_date.to_section_num == "103"


def test_usc_refs_are_counted_and_not_stored(rows):
    section = section_refs(rows["/us/usc/t16/s45f"])
    assert section.refs_by_prefix["usc"] > 0
    assert all(r.to_kind in ("pl", "pvtl", "act", "stat") for r in section.refs)
    assert section.refs_without_href == 1


# --------------------------------------------------------------- the load


def test_the_load_report(loaded):
    report = loaded[CITATIONS_SLICE.name]
    assert report.sections_read == 57
    assert report.rows_written > 500
    assert set(report.rows_by_context) == {"sourceCredit", "note", "text"}
    assert set(report.rows_by_kind) <= {"pl", "pvtl", "act", "stat"}
    assert report.anchors_stored >= 3
    assert report.rows_act_by_date_only >= 1
    assert report.rows_unparsed == 4
    assert all("/us/stat/68A/" in sample for sample in report.unparsed_samples)
    assert report.target_laws_loaded >= 7
    assert report.dataset_revision == "fixture"


def test_a_reload_replaces_the_title(db):
    from ingest.citations import load_citations

    before = load_citations(db, [CITATIONS_SLICE], revision="fixture", record_check=False)
    again = load_citations(db, [CITATIONS_SLICE], revision="fixture", record_check=False)
    assert again.rows_written == before.rows_written
    assert again.rows_replaced == before.rows_written


# ------------------------------------------------------------ cited_by


def test_cited_by_a_section_through_the_chapter_alias(repo):
    """The Code cites the Atomic Energy Act as `/us/act/1954-08-30/ch1073`;
    asking by the public-law form finds it (ADR-0002)."""
    answer = repo.cited_by("/us/pl/83/703/s1")
    assert answer is not None
    assert answer.law is not None and answer.law_identifier == "/us/pl/83/703"
    assert set(answer.aliases) == {"/us/pl/83/703", "/us/act/1954-08-30/ch1073"}
    assert answer.section_num == "1"
    assert answer.total >= 1
    assert any(s.identifier == "/us/usc/t42/s2011" for s in answer.sections)
    first = answer.sections[0]
    assert all(r.to_law == "/us/act/1954-08-30/ch1073" and r.to_section_num == "1" for r in first.refs)


def test_cited_by_the_law_lists_every_section(repo):
    law = repo.cited_by("/us/pl/83/703")
    section = repo.cited_by("/us/pl/83/703/s1")
    assert law.total >= section.total
    assert law.section_num is None
    assert law.contexts["sourceCredit"] >= 8
    assert law.release_labels


def test_cited_by_an_unloaded_law_answers_from_the_index(repo):
    """Volume 110 is not loaded; the index still knows who cites
    `/us/pl/104/333/s814` (design section 5's example)."""
    answer = repo.cited_by("/us/pl/104/333/s814")
    assert answer.law is None and answer.law_identifier == "/us/pl/104/333"
    assert answer.aliases == ("/us/pl/104/333",)
    assert "/us/usc/t16/s1" in [s.identifier for s in answer.sections]
    ref = next(r for s in answer.sections if s.identifier == "/us/usc/t16/s1" for r in s.refs)
    assert ref.to_identifier == "/us/pl/104/333/dI/tVIII/s814/e/1" and ref.context == "note"
    below = repo.cited_by("/us/pl/104/333/s814/e/1")
    assert below.below == "e/1" and below.total >= 1
    other = repo.cited_by("/us/pl/104/333/s814/f")
    assert other.total == 0


def test_cited_by_filters_by_context_and_pages(repo):
    everything = repo.cited_by("/us/act/1890-07-02/ch647")
    credits = repo.cited_by("/us/act/1890-07-02/ch647", contexts=["sourceCredit"])
    assert credits.total <= everything.total
    assert set(credits.contexts) == {"sourceCredit"}
    page = repo.cited_by("/us/act/1890-07-02/ch647", limit=2, offset=0)
    next_page = repo.cited_by("/us/act/1890-07-02/ch647", limit=2, offset=2)
    assert len(page.sections) == 2 and page.total == everything.total
    assert {s.identifier for s in page.sections}.isdisjoint({s.identifier for s in next_page.sections})


def test_cited_by_a_stat_page(repo):
    answer = repo.cited_by("/us/stat/92/3479")
    assert answer is not None
    assert "/us/usc/t16/s45f" in [s.identifier for s in answer.sections]


def test_cited_by_is_none_for_a_compilation_identifier(repo):
    assert repo.cited_by("/us/sComp/83/703/s1") is None
    assert repo.cited_by("/us/pl/81/999999") .total == 0


# ------------------------------------------------------------- evidence


def test_source_credit_evidence_lists_the_credit_laws_in_order(repo):
    evidence = repo.source_credit_evidence("/us/act/1890-07-02/ch647", "1")
    assert evidence
    one = next(e for e in evidence if e.from_identifier == "/us/usc/t15/s1")
    assert one.cites == ("/us/act/1890-07-02/ch647/s1",)
    assert one.laws[0].identifier == "/us/act/1890-07-02/ch647"
    assert one.laws[0].date == datetime.date(1890, 7, 2)
    later = [law for law in one.laws if law.kind == "pl"]
    assert later and later[-1].congress >= 108
    assert [law.seq for law in one.laws] == sorted(law.seq for law in one.laws)


def test_source_credit_evidence_by_public_law_form(repo):
    evidence = repo.source_credit_evidence("/us/pl/83/703", "1")
    assert {e.from_identifier for e in evidence} >= {"/us/usc/t42/s2011"}
    assert repo.source_credit_evidence("/us/pl/81/740", "3") == ()
    ffa = repo.cited_by("/us/pl/81/740/s3")
    assert ffa.total >= 1 and ffa.sections[0].refs[0].context == "note"


def test_index_coverage(repo):
    ffa = repo.index_coverage("/us/pl/81/740")
    assert (ffa.cited, ffa.classified, ffa.tables_cover) == (True, False, False)
    private = repo.index_coverage("/us/pvtl/81/375")
    assert (private.cited, private.classified) == (False, False)
    sherman = repo.index_coverage("/us/act/1890-07-02/ch647")
    assert sherman.cited and not sherman.classified


def test_enacted_dates_by_any_alias(repo):
    dates = repo.enacted_dates(["/us/act/1954-08-30/ch1073", "/us/pl/85/910", "/us/pl/104/333"])
    assert dates == {"/us/act/1954-08-30/ch1073": datetime.date(1954, 8, 30), "/us/pl/85/910": datetime.date(1958, 9, 2)}


def test_citation_index_status(repo):
    status = repo.citation_index_status()
    assert status.rows > 500 and status.citing_sections == 57
    assert status.dataset_revision == "fixture"
    assert status.release_labels[0][1] >= status.release_labels[-1][1]


def test_classification_methods_for_a_law_the_mirror_does_not_hold(repo):
    """The fixture tables hold Public Laws 118-35 to 118-41 and 104-1; 118-22
    is in the 118-1 table, which is not loaded."""
    assert repo.classification_rows("/us/pl/118/22") == ()
    assert repo.classification_amendments("/us/pl/118/22", "101") == ()
    status = repo.classification_status()
    assert status.rows == 80 and [(f.congress, f.session) for f in status.files] == [(118, 2), (104, 0)]
    assert status.last_check is not None and status.last_check.ok
