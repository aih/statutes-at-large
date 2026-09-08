"""The PLAW poller over the saved bulk-data listings and the four whole laws in
`tests/fixtures/plaw/`: the listing parser, what is due, the zip and the
single-file paths, the check row, and `--from-dir`. HTTP is respx throughout;
nothing touches the network."""

from __future__ import annotations

import datetime
import io
import json
import zipfile

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from db.base import Base, make_engine
from db.models import Law, SourceCheck
from ingest.plaw import congress_zip_url, file_url, listing_url
from ingest.plaw_poll import (
    TOP_LISTING_URL,
    BulkSource,
    DirectorySource,
    default_since,
    parse_congress_listing,
    parse_time,
    parse_top_listing,
    poll,
    write_report,
)
from tests.conftest import FIXTURES, PLAW_FIXTURES

UTC = datetime.timezone.utc
mock = respx.mock(assert_all_mocked=True, assert_all_called=False)
"""One router for the module; every test registers its routes on it and
anything unrouted fails."""
KEPT = {"PLAW-118publ1.xml", "PLAW-118publ22.xml", "PLAW-118publ34.xml", "PLAW-118-public.zip"}


def read_json(name: str) -> dict:
    return json.loads((PLAW_FIXTURES / name).read_text(encoding="utf-8"))


def trimmed_118(times: dict[str, str] | None = None) -> dict:
    """PLAW-118-public.json cut to the three fixture laws and the zip, with
    listing times overridden per file name when given."""
    data = read_json("PLAW-118-public.json")
    files = [dict(f) for f in data["files"] if f["name"] in KEPT]
    for entry in files:
        if times and entry["name"] in times:
            entry["formattedLastModifiedTime"] = times[entry["name"]]
    return {"files": files}


def zip_of(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, (PLAW_FIXTURES / name).read_bytes())
    return buffer.getvalue()


def only_118() -> dict:
    data = read_json("PLAW.json")
    return {"files": [f for f in data["files"] if f["name"] in ("118", "resources")]}


def make_fresh():
    """A database with the volume-137 slice, so Public Laws 118-3, 118-22 and
    118-34 are volume-derived before any poll."""
    from ingest.load import load_volume

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        load_volume(session, FIXTURES / "statute-137-slice.xml")
    return factory


@pytest.fixture(scope="module")
def fresh():
    return make_fresh()


def mock_118(times: dict[str, str] | None = None, *, top: dict | None = None):
    """Routes for the top listing, the 118th listing, the three files, and the zip."""
    mock.get(TOP_LISTING_URL).mock(return_value=httpx.Response(200, json=top or only_118()))
    mock.get(listing_url(118)).mock(return_value=httpx.Response(200, json=trimmed_118(times)))
    for number in (1, 22, 34):
        mock.get(file_url(118, number)).mock(
            return_value=httpx.Response(200, text=(PLAW_FIXTURES / f"PLAW-118publ{number}.xml").read_text(encoding="utf-8"))
        )
    mock.get(congress_zip_url(118)).mock(
        return_value=httpx.Response(200, content=zip_of(["PLAW-118publ1.xml", "PLAW-118publ22.xml", "PLAW-118publ34.xml"]))
    )


def sources(factory, congress: int):
    with factory() as session:
        return dict(session.execute(select(Law.identifier, Law.source_collection).where(Law.congress == congress)).all())


def checks(factory):
    with factory() as session:
        return session.scalars(select(SourceCheck).where(SourceCheck.collection == "PLAW").order_by(SourceCheck.id)).all()


# --------------------------------------------------------------- the listings


def test_time_parsing():
    assert parse_time("02-Jan-2026 19:32") == datetime.datetime(2026, 1, 2, 19, 32, tzinfo=UTC)
    assert parse_time(" 15-Jun-2026 04:29 ") == datetime.datetime(2026, 6, 15, 4, 29, tzinfo=UTC)
    assert parse_time("") is None and parse_time(None) is None and parse_time("2026-01-02") is None


def test_the_top_listing_is_the_congresses_with_uslm():
    congresses = parse_top_listing(read_json("PLAW.json"))
    assert [c for c, _ in congresses] == [113, 114, 115, 116, 117, 118, 119]
    assert dict(congresses)[119] == datetime.datetime(2026, 9, 2, 16, 14, tzinfo=UTC)
    assert all(t is not None for _, t in congresses)
    assert parse_top_listing({"files": [{"name": "resources", "folder": True}]}) == []


def test_a_congress_listing_is_the_law_files_in_number_order():
    listing = parse_congress_listing(118, read_json("PLAW-118-public.json"))
    assert len(listing.files) == 274 and listing.zip is not None
    assert listing.zip.name == "PLAW-118-public.zip" and listing.zip.size == 5016204
    assert listing.zip.last_modified == datetime.datetime(2026, 6, 15, 4, 29, tzinfo=UTC)
    assert [e.number for e in listing.files[:3]] == [1, 2, 3] and listing.files[-1].number == 274
    first = listing.files[0]
    assert first.package == "PLAW-118publ1" and first.congress == 118 and first.size == 4176
    assert first.link == "https://www.govinfo.gov/bulkdata/PLAW/118/public/PLAW-118publ1.xml"
    assert first.last_modified == datetime.datetime(2026, 1, 2, 19, 32, tzinfo=UTC)
    assert len(parse_congress_listing(119, read_json("PLAW-119-public.json")).files) == 102
    stray = parse_congress_listing(118, {"files": [{"name": "PLAW-117publ1.xml", "folder": False}, {"name": "PLAW-118pvtl1.xml", "folder": False}, {"name": "public", "folder": True}]})
    assert stray.files == [] and stray.zip is None


# -------------------------------------------------------------- the HTTP path


@mock
def test_a_first_poll_takes_the_zip(fresh, tmp_path):
    mock_118()
    assert sources(fresh, 118) == {"/us/pl/118/3": "STATUTE", "/us/pl/118/22": "STATUTE", "/us/pl/118/34": "STATUTE"}
    with fresh() as session:
        assert default_since(session) is None
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, directory=tmp_path)
    assert report.ok and report.since is None and report.error is None
    assert [c.congress for c in report.congresses] == [118]
    per = report.congresses[0]
    assert (per.listed, per.due, per.fetched, per.via_zip, per.loaded) == (3, 3, 3, True, 3)
    assert (per.new, per.replaced_statute, per.replaced_plaw, per.failed, per.stored_before) == (1, 2, 0, 0, 0)
    assert (report.listed, report.due, report.fetched, report.loaded, report.new, report.replaced_statute) == (3, 3, 3, 3, 1, 2)
    assert report.new_packages == ["PLAW-118publ1", "PLAW-118publ22", "PLAW-118publ34"]
    assert report.newest_last_modified == "2026-01-02T19:32:00+00:00" and report.newest_package == "PLAW-118publ1"
    assert (tmp_path / "PLAW-118-public.zip").exists()
    assert sources(fresh, 118) == {"/us/pl/118/1": "PLAW", "/us/pl/118/3": "STATUTE", "/us/pl/118/22": "PLAW", "/us/pl/118/34": "PLAW"}
    check = checks(fresh)[-1]
    assert check.ok and check.packages_seen == 3 and check.newest_package == "PLAW-118publ1"
    assert check.new_packages == ["PLAW-118publ1", "PLAW-118publ22", "PLAW-118publ34"] and check.error is None
    assert check.newest_last_modified.replace(tzinfo=UTC) == datetime.datetime(2026, 1, 2, 19, 32, tzinfo=UTC)
    assert not mock.get(file_url(118, 22)).called


@mock
def test_a_second_poll_fetches_nothing(fresh, tmp_path):
    mock_118()
    with fresh() as session:
        assert default_since(session) == datetime.datetime(2026, 1, 1, 19, 32, tzinfo=UTC)
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, directory=tmp_path)
    assert report.since == "2026-01-01T19:32:00+00:00"
    per = report.congresses[0]
    assert (per.listed, per.due, per.fetched, per.via_zip, per.loaded, per.stored_before) == (3, 0, 0, False, 0, 3)
    assert report.ok and report.new_packages == [] and report.fetched == 0
    assert not mock.get(congress_zip_url(118)).called and not mock.get(file_url(118, 1)).called
    assert len(checks(fresh)) == 2 and checks(fresh)[-1].packages_seen == 3


@mock
def test_force_refetches_everything(fresh, tmp_path):
    mock_118()
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, force=True, directory=tmp_path)
    per = report.congresses[0]
    assert (per.due, per.fetched, per.via_zip, per.loaded, per.replaced_plaw, per.new) == (3, 3, True, 3, 3, 0)
    assert report.new_packages == [] and report.ok
    assert mock.get(congress_zip_url(118)).called


@mock
def test_a_later_listing_time_makes_one_file_due(fresh, tmp_path):
    """One file of three is due, so the single-file path is taken and only
    that file is fetched."""
    later = (datetime.datetime.now(UTC) + datetime.timedelta(hours=2)).strftime("%d-%b-%Y %H:%M")
    mock_118({"PLAW-118publ22.xml": later})
    with fresh() as session:
        before = session.scalar(select(Law.loaded_at).where(Law.identifier == "/us/pl/118/22"))
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, directory=tmp_path)
    per = report.congresses[0]
    assert (per.listed, per.due, per.fetched, per.via_zip, per.loaded, per.replaced_plaw) == (3, 1, 1, False, 1, 1)
    assert mock.get(file_url(118, 22)).called and not mock.get(file_url(118, 1)).called
    assert not mock.get(congress_zip_url(118)).called
    assert report.newest_package == "PLAW-118publ22"
    assert report.newest_last_modified == parse_time(later).isoformat()
    with fresh() as session:
        after = session.scalar(select(Law.loaded_at).where(Law.identifier == "/us/pl/118/22"))
        assert after > before
        assert session.scalar(select(Law.source_collection).where(Law.identifier == "/us/pl/118/22")) == "PLAW"
    request = mock.get(file_url(118, 22)).calls.last.request
    assert request.headers["user-agent"].startswith("statutes-linkedlegislation/")
    listing_request = mock.get(listing_url(118)).calls.last.request
    assert listing_request.headers["accept"] == "application/json"


@mock
def test_a_failing_file_is_counted_and_the_check_is_ok(fresh, tmp_path):
    """One file due of three: the single-file path; the 500 on it is a
    failure, and the check row still says `ok`."""
    later = (datetime.datetime.now(UTC) + datetime.timedelta(hours=3)).strftime("%d-%b-%Y %H:%M")
    mock_118({"PLAW-118publ34.xml": later})
    mock.get(file_url(118, 34)).mock(return_value=httpx.Response(500, text="no"))
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, directory=tmp_path)
    per = report.congresses[0]
    assert (per.due, per.fetched, per.via_zip, per.loaded, per.failed) == (1, 1, False, 0, 1)
    assert report.ok and report.failed == 1 and report.loaded == 0
    assert report.failures[0]["package"] == "PLAW-118publ34" and "500" in report.failures[0]["error"]
    assert report.error.startswith("1 file(s) failed: PLAW-118publ34: HTTPStatusError")
    check = checks(fresh)[-1]
    assert check.ok and check.error == report.error and check.packages_seen == 3
    assert sources(fresh, 118)["/us/pl/118/34"] == "PLAW"


@mock
def test_a_failing_top_listing_records_not_ok_and_raises(fresh, tmp_path):
    mock.get(TOP_LISTING_URL).mock(return_value=httpx.Response(503, text="<html>later</html>"))
    before = len(checks(fresh))
    with fresh() as session, BulkSource() as source:
        with pytest.raises(httpx.HTTPStatusError):
            poll(session, source, directory=tmp_path)
    rows = checks(fresh)
    assert len(rows) == before + 1
    check = rows[-1]
    assert check.ok is False and check.packages_seen == 0 and check.newest_package is None
    assert check.error.startswith("HTTPStatusError")


@mock
def test_a_failing_congress_listing_is_the_walk_failing(fresh, tmp_path):
    mock_118()
    mock.get(listing_url(118)).mock(return_value=httpx.Response(500, text="no"))
    with fresh() as session, BulkSource() as source:
        with pytest.raises(httpx.HTTPStatusError):
            poll(session, source, congresses=[118], directory=tmp_path)
    assert checks(fresh)[-1].ok is False
    assert not mock.get(TOP_LISTING_URL).called


@mock
def test_since_filters_the_listing(fresh, tmp_path):
    later = (datetime.datetime.now(UTC) + datetime.timedelta(hours=4)).strftime("%d-%b-%Y %H:%M")
    mock_118({"PLAW-118publ1.xml": later})
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, since=datetime.datetime(2030, 1, 1, tzinfo=UTC), force=True, directory=tmp_path)
    assert report.since == "2030-01-01T00:00:00+00:00"
    per = report.congresses[0]
    assert (per.listed, per.due, per.fetched, per.via_zip, per.loaded) == (3, 0, 0, False, 0)
    assert report.newest_package == "PLAW-118publ1"
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, since=datetime.datetime.now(UTC) + datetime.timedelta(hours=1), directory=tmp_path)
    per = report.congresses[0]
    assert (per.due, per.fetched, per.via_zip, per.loaded, per.replaced_plaw) == (1, 1, False, 1, 1)
    assert mock.get(file_url(118, 1)).called and not mock.get(file_url(118, 22)).called


@mock
def test_limit_stops_after_n_files(fresh, tmp_path):
    mock_118()
    with fresh() as session, BulkSource() as source:
        report = poll(session, source, since=datetime.datetime(2020, 1, 1, tzinfo=UTC), force=True, limit=2, directory=tmp_path)
    per = report.congresses[0]
    assert (per.due, per.fetched, per.via_zip, per.loaded) == (3, 2, False, 2)
    assert mock.get(file_url(118, 1)).called and mock.get(file_url(118, 22)).called
    assert not mock.get(file_url(118, 34)).called and not mock.get(congress_zip_url(118)).called


@mock
def test_a_stale_zip_on_disk_is_refetched(tmp_path):
    """A congress with nothing PLAW-derived takes the zip; the file on disk is
    older than the listing's zip time, so it is downloaded again."""
    factory = make_fresh()
    later = (datetime.datetime.now(UTC) + datetime.timedelta(hours=1)).strftime("%d-%b-%Y %H:%M")
    mock_118({"PLAW-118-public.zip": later})
    stale = tmp_path / "PLAW-118-public.zip"
    stale.write_bytes(zip_of(["PLAW-118publ1.xml"]))
    with factory() as session, BulkSource() as source:
        report = poll(session, source, congresses=[118], directory=tmp_path)
    assert mock.get(congress_zip_url(118)).called
    assert report.congresses[0].via_zip and report.loaded == 3
    assert stale.stat().st_size == len(zip_of(["PLAW-118publ1.xml", "PLAW-118publ22.xml", "PLAW-118publ34.xml"]))


# -------------------------------------------------------------- the directory


def test_from_dir_loads_the_four_laws_with_no_network(tmp_path):
    factory = make_fresh()
    with mock:
        with factory() as session, DirectorySource(PLAW_FIXTURES) as source:
            report = poll(session, source, directory=tmp_path)
    assert [c.congress for c in report.congresses] == [118, 119]
    by_congress = {c.congress: c for c in report.congresses}
    assert (by_congress[118].listed, by_congress[118].due, by_congress[118].fetched, by_congress[118].via_zip) == (274, 274, 274, False)
    assert (by_congress[118].loaded, by_congress[118].new, by_congress[118].replaced_statute, by_congress[118].failed) == (3, 1, 2, 271)
    assert (by_congress[119].listed, by_congress[119].loaded, by_congress[119].new, by_congress[119].failed) == (102, 1, 1, 101)
    assert report.ok and report.loaded == 4 and report.new == 2 and report.replaced_statute == 2
    assert report.new_packages == ["PLAW-118publ1", "PLAW-118publ22", "PLAW-118publ34", "PLAW-119publ1"]
    assert report.failures[0]["error"].startswith("FileNotFoundError")
    assert sources(factory, 118) == {"/us/pl/118/1": "PLAW", "/us/pl/118/3": "STATUTE", "/us/pl/118/22": "PLAW", "/us/pl/118/34": "PLAW"}
    assert sources(factory, 119) == {"/us/pl/119/1": "PLAW"}
    check = checks(factory)[-1]
    assert check.ok and check.packages_seen == 376 and check.newest_package == "PLAW-119publ93"
    assert check.error.startswith("372 file(s) failed")
    target = write_report(report, tmp_path / "verification")
    assert target.name == "plaw-poll.json" and json.loads(target.read_text())["loaded"] == 4


def test_from_dir_without_a_listing_is_the_walk_failing(tmp_path):
    factory = make_fresh()
    with factory() as session, DirectorySource(PLAW_FIXTURES) as source:
        with pytest.raises(FileNotFoundError):
            poll(session, source, congresses=[113], directory=tmp_path)
    assert checks(factory)[-1].ok is False
    with factory() as session, DirectorySource(tmp_path) as source:
        report = poll(session, source, directory=tmp_path)
    assert report.ok and report.congresses == [] and report.listed == 0


def test_the_command_line(tmp_path, monkeypatch, capsys):
    import db.base
    from ingest.__main__ import main

    factory = make_fresh()
    monkeypatch.setattr(db.base, "SessionLocal", factory)
    with mock:
        code = main(["plaw", "poll", "--from-dir", str(PLAW_FIXTURES), "--congress", "118", "--report", str(tmp_path), "--json", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("PLAW 118: 274 listed, 274 due, 274 fetched via files, 3 loaded (1 new, 2 replaced volume-derived, 0 re-loaded), 271 failed")
    assert (tmp_path / "plaw-poll.json").exists()
    assert json.loads(out[out.index("{"):])["congresses"][0]["congress"] == 118
    with mock:
        code = main(["plaw", "poll", "--from-dir", str(PLAW_FIXTURES), "--congress", "118", "--limit", "1", "--force", "--since", "2020-01-01", "--dir", str(tmp_path)])
    assert code == 0 and "1 fetched via files, 1 loaded (0 new, 0 replaced volume-derived, 1 re-loaded)" in capsys.readouterr().out


# ------------------------------------------------------------- the untouched


def test_the_volume_derived_law_is_untouched(fresh):
    with fresh() as session:
        law = session.scalars(select(Law).where(Law.identifier == "/us/pl/118/3")).one()
        assert law.source_collection == "STATUTE" and law.source_package == "STATUTE-137"
        assert law.provenance_identifiers == "rules-1.0"
        assert session.scalar(select(Law.source_collection).where(Law.identifier == "/us/pl/118/22")) == "PLAW"
