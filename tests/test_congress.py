"""Acts by Congress (ADR-0033): the Congress helpers, an act's Congress and
public or private side at load, the repository's counts and filters over the
fixture database, and the two routes.

The fixture database's Congresses: the 51st (two chapter acts of vol 26, one
public and one private), the 81st (nine public laws and a private law), the
83rd, 85th, 107th, 111th, 118th and 119th, with compilations of the 51st,
74th, 75th and 83rd, and classification tables for the 104th (whole
congress) and the 118th (2nd session), whose rows name no loaded law.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from ingest.identifiers import congress_in_volume, congress_of_act, volume_congresses
from storage import congress_ordinal, congress_years
from storage.identifiers import congress_of_date, congress_term
from tests.conftest import FIXTURES

SITE = "https://statutes.linkedlegislation.org"
USCODE = "https://uscode.linkedlegislation.org"


# --------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    ("congress", "ordinal"),
    [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (13, "13th"),
     (21, "21st"), (22, "22nd"), (23, "23rd"), (111, "111th"), (112, "112th"), (113, "113th"), (119, "119th")],
)
def test_congress_ordinal(congress, ordinal):
    assert congress_ordinal(congress) == ordinal


def test_congress_years():
    assert congress_years(1) == (1789, 1791)
    assert congress_years(51) == (1889, 1891)
    assert congress_years(74) == (1935, 1937)
    assert congress_years(119) == (2025, 2027)


@pytest.mark.parametrize(
    ("day", "congress"),
    [
        (datetime.date(1789, 3, 4), 1),
        (datetime.date(1791, 3, 3), 1),
        (datetime.date(1791, 3, 4), 2),
        (datetime.date(1890, 8, 15), 51),
        (datetime.date(1891, 3, 3), 51),
        (datetime.date(1935, 1, 2), 73),
        (datetime.date(1935, 1, 3), 74),
        (datetime.date(2025, 1, 2), 118),
        (datetime.date(2025, 1, 3), 119),
    ],
)
def test_congress_of_date(day, congress):
    assert congress_of_date(day) == congress


def test_an_acts_congress_is_the_one_sitting_on_its_approval_date():
    # Vol 26's chapter 784 is tagged 52 and was approved in the 51st.
    assert congress_of_act(52, datetime.date(1890, 8, 15)) == 51
    assert congress_of_act(51, datetime.date(1890, 8, 15)) == 51
    assert congress_of_act(52, None) == 52
    # The March 4 a term ended at noon: the outgoing Congress is kept.
    assert congress_of_act(27, datetime.date(1843, 3, 4)) == 27
    assert congress_of_act(None, datetime.date(1843, 3, 4)) == 28
    assert congress_of_act(16, datetime.date(1843, 3, 4)) == 28


@pytest.mark.parametrize(
    ("volume", "congresses"),
    [(1, set(range(1, 6))), (6, set(range(1, 29))), (7, None), (13, {38}), (26, {51}), (32, {57}), (49, {74}),
     (50, {75}), (52, {75}), (54, {76}), (70, {84}), (71, {85}), (77, {87, 88}), (89, {93, 94}), (123, {111}),
     (137, {118}), (140, {119})],
)
def test_volume_congresses(volume, congresses):
    assert volume_congresses(volume) == (frozenset(congresses) if congresses is not None else None)


@pytest.mark.parametrize(
    ("meta", "enacted", "volume", "act", "congress"),
    [
        # Vol 26's chapter 784, tagged 52, approved in the 51st.
        (52, datetime.date(1890, 8, 15), 26, True, 51),
        # Vol 6 tags an act of 1836 with the 16th.
        (16, datetime.date(1836, 1, 19), 6, True, 24),
        # OCR years: 34 Stat. 2683 reads 1807, 32 Stat. 1031 reads 1901 for 1903.
        (59, datetime.date(1807, 2, 28), 34, True, 59),
        (57, datetime.date(1901, 3, 3), 32, True, 57),
        # An act of the 76th approved after its Congress ended.
        (76, datetime.date(1941, 1, 7), 54, True, 76),
        # 37 Stat. 739, Public No. 427 of the 62nd, tagged 63.
        (63, datetime.date(1913, 3, 4), 37, False, 62),
        # 44 Stat. 1762, Private No. 328 of the 69th, tagged 72.
        (72, datetime.date(1926, 12, 16), 44, False, 69),
        # 123 Stat. 2085, Public Law 111-78, tagged 110.
        (110, datetime.date(2009, 10, 19), 123, False, 111),
        # Public Law 93-650 in vol 89; an OCR date leaves a numbered law alone.
        (93, datetime.date(1975, 1, 4), 89, False, 93),
        (90, datetime.date(1958, 5, 17), 82, False, 90),
        # Neither the tag nor the date is the volume's, and the volume has two.
        (91, datetime.date(1970, 12, 25), 89, False, 91),
        # The treaty volumes have no table.
        (52, datetime.date(1890, 8, 15), 7, True, 51),
    ],
)
def test_congress_in_volume(meta, enacted, volume, act, congress):
    assert congress_in_volume(meta, enacted, volume, act=act) == congress


def test_congress_term():
    assert congress_term(1) == (datetime.date(1789, 3, 4), datetime.date(1791, 3, 4))
    assert congress_term(73) == (datetime.date(1933, 3, 4), datetime.date(1935, 2, 3))
    assert congress_term(110) == (datetime.date(2007, 1, 3), datetime.date(2009, 2, 3))


# ------------------------------------------------------------ the loaders


def test_a_chapter_act_takes_its_congress_from_its_date_and_keeps_its_side():
    from ingest.statute import LawRecord, iter_volume

    laws = [item for item in iter_volume(Path(FIXTURES / "statute-26-slice.xml")) if isinstance(item, LawRecord)]
    assert [(law.identifier, law.kind, law.congress, law.public_private) for law in laws] == [
        ("/us/act/1890-07-02/ch647", "act", 51, "public"),
        ("/us/act/1890-08-15/ch784", "act", 51, "private"),
    ]
    assert laws[0].warnings == []
    assert laws[1].warnings == ["/us/act/1890-08-15/ch784 congress taken from the approval date, not meta/congress"]


def test_a_volume_reload_drops_the_laws_it_no_longer_yields():
    """A law stored from the volume under an identifier the file no longer
    yields (a congress since moved) is deleted on the next load."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from db.base import Base, make_engine
    from db.models import Law
    from ingest.load import load_volume

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    with factory() as session:
        load_volume(session, FIXTURES / "statute-26-slice.xml")
        law = session.scalars(select(Law).where(Law.identifier == "/us/act/1890-08-15/ch784")).one()
        law.identifier = "/us/act/1890-08-15/ch999"
        session.commit()
        report = load_volume(session, FIXTURES / "statute-26-slice.xml")
        assert report.laws_dropped_as_stale == ["/us/act/1890-08-15/ch999"]
        assert sorted(session.scalars(select(Law.identifier))) == ["/us/act/1890-07-02/ch647", "/us/act/1890-08-15/ch784"]


def test_every_loaded_law_records_its_side(db):
    from sqlalchemy import func, select

    from db.models import Law

    rows = db.execute(select(Law.kind, Law.public_private, func.count()).group_by(Law.kind, Law.public_private)).tuples().all()
    assert sorted(rows) == [("act", "private", 1), ("act", "public", 1), ("pl", "public", 27), ("pvtl", "private", 2)]


# ------------------------------------------------------------- overview


def test_the_overview_lists_every_congress_to_the_latest(repo):
    overview = repo.congresses_overview()
    assert overview.total_congresses == 119
    assert [s.congress for s in overview.congresses] == list(range(1, 120))
    assert (overview.total_laws, overview.total_public_laws, overview.total_private_laws, overview.total_chapter_acts) == (31, 27, 2, 2)
    assert overview.total_sections == 140
    assert overview.total_compilations == 4

    by = {s.congress: s for s in overview.congresses}
    empty = by[2]
    assert (empty.total_laws, empty.volumes, empty.first_enacted, empty.compilations_count) == (0, (), None, 0)


def test_an_approval_date_outside_the_term_is_left_out_of_the_range(repo, db):
    from sqlalchemy import select

    from db.models import Law

    before = {s.congress: s for s in repo.congresses_overview().congresses}[81]
    law = db.scalars(select(Law).where(Law.congress == 81, Law.kind == "pl").order_by(Law.id)).first()
    law.enacted = datetime.date(1, 1, 1)
    db.flush()
    after = {s.congress: s for s in repo.congresses_overview().congresses}[81]
    assert after.first_enacted is not None and after.first_enacted >= datetime.date(1949, 1, 3)
    assert after.last_enacted == before.last_enacted
    assert after.total_laws == before.total_laws
    db.rollback()


def test_the_overview_counts_each_congress(repo):
    by = {s.congress: s for s in repo.congresses_overview().congresses}
    row = lambda s: (  # noqa: E731
        s.total_laws, s.public_laws, s.private_laws, s.chapter_acts, s.public_acts, s.private_acts, s.volumes,
        s.section_count, s.compilations_count, s.compiled_laws_count, s.cited_laws_count, s.citing_sections_count,
        s.classified_laws_count, s.classification_sessions, s.pending_laws_count,
    )
    assert row(by[51]) == (2, 0, 0, 2, 1, 1, (26,), 9, 1, 1, 1, 8, 0, (), 0)
    assert row(by[74]) == (0, 0, 0, 0, 0, 0, (), 0, 1, 0, 0, 0, 0, (), 0)
    assert row(by[81]) == (10, 9, 1, 0, 0, 0, (64,), 48, 0, 0, 1, 3, 0, (), 0)
    assert row(by[83]) == (1, 1, 0, 0, 0, 0, (68,), 3, 1, 1, 1, 8, 0, (), 0)
    assert row(by[104]) == (0, 0, 0, 0, 0, 0, (), 0, 0, 0, 0, 0, 0, (0,), 0)
    assert row(by[118]) == (4, 4, 0, 0, 0, 0, (137,), 30, 0, 0, 2, 16, 0, (2,), 0)
    assert (by[51].public_count, by[51].private_count) == (1, 1)
    assert (by[51].ordinal, by[51].start_year, by[51].end_year) == ("51st", 1889, 1891)
    assert (by[51].first_enacted, by[51].last_enacted) == (datetime.date(1890, 7, 2), datetime.date(1890, 8, 15))


# --------------------------------------------------------------- detail


def _ids(detail):
    return [law.identifier for law in detail.laws]


def test_the_51st_splits_its_acts_by_side(repo):
    detail = repo.congress_detail(51)
    assert _ids(detail) == ["/us/act/1890-07-02/ch647", "/us/act/1890-08-15/ch784"]
    assert [(v.volume, v.page) for v in detail.volume_starts] == [(26, "209")]
    assert _ids(repo.congress_detail(51, public_private="public")) == ["/us/act/1890-07-02/ch647"]
    assert _ids(repo.congress_detail(51, public_private="private")) == ["/us/act/1890-08-15/ch784"]
    assert repo.congress_detail(51, kind="act").total == 2

    sherman = detail.laws[0]
    assert (sherman.label, sherman.volume, sherman.page_first, sherman.section_count) == ("Act of July 2, 1890, ch. 647", 26, "209", 8)
    assert [c.identifier_prefix for c in sherman.compilations] == ["/us/sComp/51/647"]
    assert (sherman.usc_citing_sections_count, sherman.usc_titles) == (8, ("15",))
    assert (sherman.usc_classifications_count, sherman.classification_session) == (0, None)


def test_the_81st_filters_and_sorts(repo):
    assert repo.congress_detail(81).total == 10
    assert repo.congress_detail(81, kind="pl").total == 9
    assert _ids(repo.congress_detail(81, kind="pvtl")) == ["/us/pvtl/81/375"]
    assert repo.congress_detail(81, public_private="public").total == 9
    assert _ids(repo.congress_detail(81, public_private="private")) == ["/us/pvtl/81/375"]
    assert _ids(repo.congress_detail(81, q="740")) == ["/us/pl/81/740"]
    assert _ids(repo.congress_detail(81, cited=True)) == ["/us/pl/81/740"]
    assert repo.congress_detail(81, classified=True).total == 0

    by_sections = repo.congress_detail(81, sort="sections").laws
    assert [law.section_count for law in by_sections] == sorted((law.section_count for law in by_sections), reverse=True)
    assert by_sections[0].identifier == "/us/pl/81/740"
    by_date = [law.enacted for law in repo.congress_detail(81, sort="date").laws]
    assert by_date == sorted(by_date)

    page = repo.congress_detail(81, limit=3, offset=3)
    assert (page.total, len(page.laws), page.limit, page.offset) == (10, 3, 3, 3)


def test_the_83rd_has_its_compilation_and_citations(repo):
    assert _ids(repo.congress_detail(83, has_comp=True)) == ["/us/pl/83/703"]
    assert _ids(repo.congress_detail(83, cited=True)) == ["/us/pl/83/703"]
    assert [c.identifier_prefix for c in repo.congress_detail(83).laws[0].compilations] == ["/us/sComp/83/703"]


def test_a_congress_with_nothing_loaded_has_a_page_and_one_past_the_latest_none(repo):
    detail = repo.congress_detail(104)
    assert (detail.total, detail.laws, detail.volume_starts, detail.summary.classification_sessions) == (0, (), (), (0,))
    assert detail.latest_congress == 119
    assert repo.congress_detail(120) is None
    assert repo.congress_detail(0) is None


# ------------------------------------------------- matching the indexes


def test_a_compilation_without_law_id_finds_its_law_by_alias(repo, db):
    from db.models import Comp

    db.add(Comp(file_id="99990", package_id="COMPS-99990", identifier_prefix="/us/sComp/81/740",
                law_congress=81, law_number=740, display_title="Compiled 81-740", short_titles=[]))
    db.flush()
    try:
        assert _ids(repo.congress_detail(81, has_comp=True)) == ["/us/pl/81/740"]
        summary = repo.congress_detail(81).summary
        assert (summary.compilations_count, summary.compiled_laws_count) == (1, 1)
    finally:
        db.rollback()


def test_a_compilation_is_not_matched_on_a_chapter_or_a_private_law_number(repo, db):
    """Public Law 81-740 is chapter 823 and Private Law 81-375 shares its
    number with Public Law 81-375, which is not loaded: a compilation of
    Public Law 81-823 or 81-375 compiles neither."""
    from db.models import Comp

    db.add_all([
        Comp(file_id="99991", package_id="COMPS-99991", identifier_prefix="/us/sComp/81/823",
             law_congress=81, law_number=823, display_title="Compiled 81-823", short_titles=[]),
        Comp(file_id="99992", package_id="COMPS-99992", identifier_prefix="/us/sComp/81/375",
             law_congress=81, law_number=375, display_title="Compiled 81-375", short_titles=[]),
    ])
    db.flush()
    try:
        detail = repo.congress_detail(81)
        assert [law.identifier for law in detail.laws if law.compilations] == []
        assert (detail.summary.compilations_count, detail.summary.compiled_laws_count) == (2, 0)
        assert repo.congress_detail(81, has_comp=True).total == 0
    finally:
        db.rollback()


def test_a_classification_row_names_a_public_law_only(repo, db):
    from sqlalchemy import select

    from db.models import ClassificationFile, ClassificationEntry

    table = db.scalars(select(ClassificationFile).where(ClassificationFile.congress == 118)).one()
    for seq, number in enumerate((22, 9999), start=90000):
        db.add(ClassificationEntry(file_id=table.id, congress=118, session=2, row_seq=seq, title_num="7",
                                   pl_congress=118, pl_num=number, pl_section_raw=""))
    db.add(ClassificationEntry(file_id=table.id, congress=81, session=2, row_seq=90002, title_num="36",
                               pl_congress=81, pl_num=375, pl_section_raw=""))
    db.flush()
    try:
        law = next(law for law in repo.congress_detail(118).laws if law.identifier == "/us/pl/118/22")
        assert (law.usc_classifications_count, law.classification_session, law.usc_titles) == (1, 2, ("6", "7", "16"))
        assert _ids(repo.congress_detail(118, classified=True)) == ["/us/pl/118/22"]
        assert repo.congress_detail(118).summary.classified_laws_count == 1
        private = next(law for law in repo.congress_detail(81).laws if law.identifier == "/us/pvtl/81/375")
        assert (private.usc_classifications_count, private.classification_session) == (0, None)
        assert repo.congress_detail(81).summary.classified_laws_count == 0
    finally:
        db.rollback()


def test_a_law_cited_under_two_aliases_counts_once(repo, db):
    """The fixture cites Public Law 81-740 as `/us/act/1950-08-30/ch823`; a
    second citation by its number is the same law."""
    from db.models import Citation

    db.add(Citation(from_identifier="/us/usc/t36/s1", from_title="36", release_label="fixture", context="sourceCredit",
                    seq=1, to_identifier="/us/pl/81/740", to_kind="pl", to_law="/us/pl/81/740", to_congress=81, to_number=740))
    db.flush()
    try:
        summary = repo.congress_detail(81).summary
        assert (summary.cited_laws_count, summary.citing_sections_count) == (1, 4)
        law = next(law for law in repo.congress_detail(81).laws if law.identifier == "/us/pl/81/740")
        assert law.usc_citing_sections_count == 4
    finally:
        db.rollback()


def test_pending_laws_are_listed_with_their_congress(repo, db):
    from db.models import PendingLaw

    db.add(PendingLaw(identifier="/us/pl/119/120", congress=119, number=120, bill_type="HR", bill_number="9001",
                      title="A placeholder bill", action_date=datetime.date(2026, 10, 2),
                      congress_gov_url="https://www.congress.gov/bill/119th-congress/house-bill/9001",
                      checked_at=datetime.datetime(2026, 10, 3, tzinfo=datetime.timezone.utc)))
    db.flush()
    try:
        detail = repo.congress_detail(119)
        assert [(p.identifier, p.bill_label) for p in detail.pending_laws] == [("/us/pl/119/120", "H.R. 9001")]
        assert detail.summary.pending_laws_count == 1
    finally:
        db.rollback()


# ------------------------------------------------- the stored summaries


def test_a_write_to_a_counted_table_moves_the_stamp_and_a_rollback_restores_it(repo, db):
    from sqlalchemy import select

    from db.models import Law

    before = repo.data_stamp()
    law = db.scalars(select(Law).where(Law.congress == 81).order_by(Law.id)).first()
    law.official_title = "An Act renamed"
    db.flush()
    assert repo.data_stamp()[0] > before[0]
    db.rollback()
    assert repo.data_stamp() == before


def test_the_summaries_are_stored_at_the_stamp_and_served_from_the_rows(repo, db, monkeypatch):
    from sqlalchemy import select

    import storage.postgres
    from db.models import CongressSummaryRow, Law
    from ingest.congress_summaries import refresh_congress_summaries

    computed = repo.compute_congress_summaries()
    report = refresh_congress_summaries(db)
    assert (report["stored"], report["congresses"]) == (True, 119)
    assert refresh_congress_summaries(db)["stored"] is False
    assert repo.stored_summaries(repo.data_stamp()) == computed

    # A stored row is what the overview reads when this process holds nothing.
    row = db.get(CongressSummaryRow, 81)
    row.summary = {**row.summary, "total_laws": 999}
    db.flush()
    monkeypatch.setattr(storage.postgres, "_summaries_held", None)
    assert repo.congress_detail(81).summary.total_laws == 999
    db.rollback()

    # A write moves the stamp past the rows; the counts are computed again.
    monkeypatch.setattr(storage.postgres, "_summaries_held", None)
    law = db.scalars(select(Law).where(Law.congress == 81, Law.kind == "pvtl")).first()
    db.delete(law)
    db.flush()
    try:
        assert repo.stored_summaries(repo.data_stamp()) is None
        assert repo.congress_detail(81).summary.total_laws == 9
    finally:
        db.rollback()
    assert repo.congress_detail(81).summary.total_laws == 10


# ----------------------------------------------------------------- routes


def test_the_overview_route(client):
    response = client.get("/api/v1/congress")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    body = response.json()
    assert body["note"] == "31 laws of 119 Congresses are loaded. Every count is of loaded laws."
    c104 = body["congresses"][103]
    assert c104["url"] == f"{SITE}/app/congress/104"
    assert c104["uscode_classification_urls"] == [{"session": "all", "url": f"{USCODE}/app/classification/104/all"}]
    c51 = body["congresses"][50]
    assert (c51["public_acts"], c51["private_acts"], c51["compiled_laws_count"]) == (1, 1, 1)


def test_the_detail_route_links_by_citation_url(client):
    body = client.get("/api/v1/congress/51").json()
    assert body["note"] == "The 51st Congress sat from 1889 to 1891; 2 of its laws are loaded."
    assert body["volume_starts"] == [{"volume": 26, "page": "209", "url": f"{SITE}/us/stat/26/209"}]
    sherman, private = body["laws"]
    assert sherman["url"] == f"{SITE}/us/act/1890-07-02/ch647"
    assert sherman["stat_url"] == f"{SITE}/us/stat/26/209"
    assert sherman["cited_by_url"] == f"{SITE}/us/act/1890-07-02/ch647#cited-by"
    assert sherman["compilations"][0]["url"] == f"{SITE}/us/sComp/51/647"
    assert (private["public_private"], private["cited_by_url"], private["uscode_classification_url"]) == ("private", None, None)
    assert [law["identifier"] for law in client.get("/api/v1/congress/51?public_private=private").json()["laws"]] == [
        "/us/act/1890-08-15/ch784"
    ]


def test_the_detail_route_refuses_what_it_cannot_answer(client):
    response = client.get("/api/v1/congress/150")
    assert response.status_code == 404
    assert response.json()["detail"] == "nothing for the 150th Congress in the loaded Statutes at Large volumes"
    assert client.get("/api/v1/congress/0").status_code == 422
    assert client.get("/api/v1/congress/201").status_code == 422
    assert client.get("/api/v1/congress/81?public_private=both").status_code == 422
    assert client.get("/api/v1/congress/81?sort=title").status_code == 422
