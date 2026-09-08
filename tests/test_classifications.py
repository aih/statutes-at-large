"""The classification tables mirror: the client over respx, the loader over
the saved pages in `tests/fixtures/classifications/`, and what the repository
answers from it."""

from __future__ import annotations

import datetime
import itertools
import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from db.base import Base, make_engine
from db.models import ClassificationCheck, ClassificationEntry, ClassificationFile
from ingest.classifications import (
    DEFAULT_ORIGIN,
    TABLES_PATH,
    ApiSource,
    ClassificationsClient,
    ClassificationsError,
    DirectorySource,
    content_hash,
    fetch_rows,
    load_classifications,
    write_report,
)
from tests.conftest import CLASSIFICATIONS_FIXTURES

TABLES_URL = f"{DEFAULT_ORIGIN}{TABLES_PATH}"
UPSTREAM_CHECKED = "2026-09-08T06:41:10.740212Z"
UPSTREAM_COVERED = "Public Law 119-70 and Public Laws 119-74 through 119-103"


@pytest.fixture()
def client():
    slept: list[float] = []
    # The clock advances a second per reading, so pacing never sleeps and
    # `slept` holds only the retry waits.
    with ClassificationsClient(origin=DEFAULT_ORIGIN, sleep=slept.append, clock=itertools.count(0.0, 1.0).__next__) as c:
        c.slept = slept  # type: ignore[attr-defined]
        yield c


@pytest.fixture()
def fresh():
    """An empty SQLite database of its own, for loads that change the rows."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session


def _page(items: list[dict], total: int) -> dict:
    return {"items": items, "total": total, "limit": 2, "offset": 0, "sort": "pl", "file": {}}


# ------------------------------------------------------------------ client


@respx.mock
def test_paging_follows_the_offset(client):
    rows = [{"row_seq": n, "raw_line": f"line {n}"} for n in range(3)]

    def pages(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=_page(rows[offset : offset + 2], 3))

    route = respx.get(f"{TABLES_URL}/118/2/entries").mock(side_effect=pages)
    items, pages_read, warnings = fetch_rows(ApiSource(client, limit=2), 118, 2)
    assert [i["row_seq"] for i in items] == [0, 1, 2] and pages_read == 2 and warnings == []
    assert route.call_count == 2
    first, second = (call.request for call in route.calls)
    assert dict(first.url.params) == {"sort": "pl", "limit": "2", "offset": "0"}
    assert dict(second.url.params) == {"sort": "pl", "limit": "2", "offset": "2"}
    assert first.headers["User-Agent"] == "statutes-linkedlegislation/0.1 (+https://statutes.linkedlegislation.org)"
    assert client.slept == []


def test_requests_are_paced():
    slept: list[float] = []
    # Readings: the first request, the second request 30 ms later, and the
    # reading after the sleep.
    clock = iter([0.0, 0.03, 0.13])
    with respx.mock:
        respx.get(TABLES_URL).mock(return_value=httpx.Response(200, json={"files": []}))
        with ClassificationsClient(origin=DEFAULT_ORIGIN, sleep=slept.append, clock=lambda: next(clock)) as c:
            c.tables()
            c.tables()
    assert len(slept) == 1 and abs(slept[0] - 0.07) < 1e-9


@respx.mock
def test_a_429_is_waited_out_and_retried(client):
    route = respx.get(TABLES_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"source": {}, "files": []}),
        ]
    )
    assert client.tables() == {"source": {}, "files": []}
    assert route.call_count == 2 and client.slept == [3.0]


@respx.mock
def test_a_500_fails_the_run_and_writes_a_check_row(client, fresh):
    route = respx.get(TABLES_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(ClassificationsError, match="HTTP 500"):
        load_classifications(fresh, ApiSource(client))
    assert route.call_count == 4 and client.slept == [1.0, 2.0, 4.0]
    check = fresh.scalars(select(ClassificationCheck)).one()
    assert check.ok is False and check.error.startswith("ClassificationsError: HTTP 500")
    assert check.source_url == TABLES_URL and check.files_seen == 0 and check.rows_loaded == 0


@respx.mock
def test_the_api_source_end_to_end(client, fresh):
    listing = json.loads((CLASSIFICATIONS_FIXTURES / "tables.json").read_text())
    page = json.loads((CLASSIFICATIONS_FIXTURES / "entries-118-2-0.json").read_text())
    page["total"] = 40
    respx.get(TABLES_URL).mock(return_value=httpx.Response(200, json=listing))
    respx.get(f"{TABLES_URL}/118/2/entries").mock(return_value=httpx.Response(200, json=page))
    respx.get(f"{TABLES_URL}/118/1/entries").mock(return_value=httpx.Response(200, json=_page([], 0)))
    report = load_classifications(fresh, ApiSource(client), congress=118)
    assert report.ok and report.congress == 118 and report.source_url == TABLES_URL
    assert [(f.session, f.action, f.rows, f.pages) for f in report.files] == [(2, "loaded", 40, 1), (1, "loaded", 0, 1)]
    assert report.rows_loaded == 40 and report.files_seen == 2
    assert fresh.scalars(select(ClassificationCheck)).one().source_url == TABLES_URL


# ------------------------------------------------------------------ loader


def test_the_fixture_load_report(loaded):
    report = loaded["classifications"]
    assert report.ok and report.error is None and report.congress is None
    assert report.source_url == str(CLASSIFICATIONS_FIXTURES)
    assert (report.files_seen, report.files_other_kind) == (31, 2)
    assert (report.files_loaded, report.files_unchanged, report.files_skipped) == (2, 0, 29)
    assert report.rows_loaded == 80
    assert report.upstream_checked_at == UPSTREAM_CHECKED
    assert report.upstream_covered_text == UPSTREAM_COVERED
    line = next(f for f in report.files if (f.congress, f.session) == (118, 2))
    assert (line.action, line.listing_row_count, line.rows, line.pages) == ("loaded", 2987, 40, 1)
    assert line.covered_laws_text == "Public Laws 118-35 to 118-274"
    assert line.warnings == ["page at offset 40 not found; 40 row(s) kept"]
    skipped = next(f for f in report.files if (f.congress, f.session) == (118, 1))
    assert skipped.action == "skipped" and skipped.warnings == ["no page found; the file is not mirrored"]
    assert "118-1: no page found; the file is not mirrored" in report.warnings


def test_files_and_entries(db):
    files = {(f.congress, f.session): f for f in db.scalars(select(ClassificationFile)).all()}
    assert set(files) == {(118, 2), (104, 0)}
    table = files[(118, 2)]
    assert table.kind == "pl" and table.row_count == 40 and table.covered_ranges == ["35-274"]
    assert (table.first_law, table.last_law, table.stat_volume) == (35, 274, 138)
    assert table.prepared_date == datetime.date(2025, 1, 6)
    assert table.source_filename == "tbl118pl_2nd.htm"
    assert table.upstream_fetched_at.replace(tzinfo=None) == datetime.datetime(2026, 9, 7, 7, 42, 22, 317922)
    assert table.content_hash == content_hash(json.loads((CLASSIFICATIONS_FIXTURES / "entries-118-2-0.json").read_text())["items"])
    whole = files[(104, 0)]
    assert whole.session_label == "all" and whole.covered_laws_text == "Public Laws 104-1 to 104-333"
    entries = db.scalars(
        select(ClassificationEntry).where(ClassificationEntry.file_id == table.id).order_by(ClassificationEntry.row_seq)
    ).all()
    assert len(entries) == 40 and [e.row_seq for e in entries] == list(range(40))
    first = entries[0]
    assert (first.congress, first.session, first.pl_congress, first.pl_num, first.pl_label) == (118, 2, 118, 35, "118-35")
    assert (first.pl_section_raw, first.pl_section_num) == ("101(3)", "101")
    assert first.usc_identifier == "/us/usc/t18/s3551" and first.title_num == "18" and first.section_raw == "3551"
    assert first.is_note is True and first.action is None and first.is_appendix is False
    assert first.stat_volume == 138 and first.stat_pages == [3] and first.stat_page_labels == ["3"]
    assert first.raw_line.startswith("18    3551")
    dashed = next(e for e in entries if e.pl_section_raw == "101(b), (c)")
    assert dashed.usc_identifier == "/us/usc/t42/s254b–2"
    assert {e.action for e in entries} == {None, "new"}


def test_a_reload_over_the_same_pages_rewrites_nothing(db):
    before = db.scalars(select(ClassificationEntry.id).order_by(ClassificationEntry.id)).all()
    report = load_classifications(db, DirectorySource(CLASSIFICATIONS_FIXTURES))
    assert (report.files_loaded, report.files_unchanged, report.files_skipped) == (0, 2, 29)
    assert report.rows_loaded == 0
    assert db.scalars(select(ClassificationEntry.id).order_by(ClassificationEntry.id)).all() == before
    assert db.scalar(select(func.count()).select_from(ClassificationFile)) == 2


def _saved_table(directory: Path, *, rows: int = 40) -> None:
    """The 118-2 fixture alone, with the listing's row count set to what the
    saved page holds, so the listing gate can match."""
    listing = json.loads((CLASSIFICATIONS_FIXTURES / "tables.json").read_text())
    listing["files"] = [f for f in listing["files"] if (f["congress"], f["session"]) == (118, 2)]
    listing["files"][0]["row_count"] = rows
    page = json.loads((CLASSIFICATIONS_FIXTURES / "entries-118-2-0.json").read_text())
    page["items"] = page["items"][:rows]
    page["total"] = rows
    (directory / "tables.json").write_text(json.dumps(listing))
    (directory / "entries-118-2-0.json").write_text(json.dumps(page))


def test_the_listing_gate_and_force(fresh, tmp_path):
    _saved_table(tmp_path)
    first = load_classifications(fresh, DirectorySource(tmp_path))
    assert [(f.action, f.pages, f.warnings) for f in first.files] == [("loaded", 1, [])]
    gated = load_classifications(fresh, DirectorySource(tmp_path))
    assert [(f.action, f.pages, f.rows) for f in gated.files] == [("skipped", 0, 40)]
    assert gated.files_skipped == 1 and gated.files_unchanged == 0
    forced = load_classifications(fresh, DirectorySource(tmp_path), force=True)
    assert [(f.action, f.pages) for f in forced.files] == [("unchanged", 1)]
    assert fresh.scalar(select(func.count()).select_from(ClassificationCheck)) == 3


def test_a_changed_page_replaces_the_file_wholesale(fresh, tmp_path):
    _saved_table(tmp_path)
    load_classifications(fresh, DirectorySource(tmp_path))
    old_ids = set(fresh.scalars(select(ClassificationEntry.id)).all())
    table = fresh.scalars(select(ClassificationFile)).one()
    mirrored_before = table.mirrored_at

    page = json.loads((tmp_path / "entries-118-2-0.json").read_text())
    page["items"] = page["items"][:39]
    page["items"][5]["pl_section_raw"] = ""
    page["items"][5]["raw_line"] = "changed"
    page["total"] = 39
    (tmp_path / "entries-118-2-0.json").write_text(json.dumps(page))
    listing = json.loads((tmp_path / "tables.json").read_text())
    listing["files"][0]["row_count"] = 39
    (tmp_path / "tables.json").write_text(json.dumps(listing))

    report = load_classifications(fresh, DirectorySource(tmp_path))
    assert [f.action for f in report.files] == ["loaded"] and report.rows_loaded == 39
    fresh.expire_all()
    table = fresh.scalars(select(ClassificationFile)).one()
    assert table.row_count == 39 and table.content_hash == content_hash(page["items"])
    assert table.mirrored_at >= mirrored_before
    entries = fresh.scalars(select(ClassificationEntry).order_by(ClassificationEntry.row_seq)).all()
    assert len(entries) == 39 and len(old_ids) == 40
    assert (entries[5].pl_section_raw, entries[5].pl_section_num, entries[5].raw_line) == ("", None, "changed")
    assert fresh.scalar(select(func.count()).select_from(ClassificationFile)) == 1


def test_congress_limits_the_run(fresh):
    report = load_classifications(fresh, DirectorySource(CLASSIFICATIONS_FIXTURES), congress=104)
    assert report.files_seen == 1 and report.files_loaded == 1 and report.rows_loaded == 40
    assert [(f.congress, f.session, f.session_label) for f in report.files] == [(104, 0, "all")]
    check = fresh.scalars(select(ClassificationCheck)).one()
    assert check.congress == 104 and check.ok and check.files_seen == 1 and check.files_loaded == 1
    assert check.upstream_covered_text == UPSTREAM_COVERED
    assert check.upstream_checked_at.replace(tzinfo=None) == datetime.datetime(2026, 9, 8, 6, 41, 10, 740212)


def test_a_missing_listing_is_a_failed_run(fresh, tmp_path):
    with pytest.raises(FileNotFoundError):
        load_classifications(fresh, DirectorySource(tmp_path))
    check = fresh.scalars(select(ClassificationCheck)).one()
    assert check.ok is False and check.error.startswith("FileNotFoundError") and check.source_url == str(tmp_path)


def test_the_report_file(loaded, tmp_path):
    target = write_report(loaded["classifications"], tmp_path)
    body = json.loads(target.read_text())
    assert target.name == "classifications.json"
    assert body["files_loaded"] == 2 and body["rows_loaded"] == 80
    assert body["files"][0].keys() >= {"congress", "session", "action", "listing_row_count", "rows", "warnings"}


# -------------------------------------------------------------- repository


def test_classification_rows_for_a_public_law(repo):
    rows = repo.classification_rows("/us/pl/118/35")
    assert rows and all(r.pl_identifier == "/us/pl/118/35" and r.pl_label == "118-35" for r in rows)
    first = rows[0]
    assert (first.congress, first.session, first.row_seq) == (118, 2, 0)
    assert (first.pl_section_raw, first.pl_section_num, first.usc_identifier) == ("101(3)", "101", "/us/usc/t18/s3551")
    assert first.is_note and first.action is None and first.stat_page_labels == ("3",)
    section = repo.classification_rows("/us/pl/118/35", "101")
    assert section and {r.pl_section_num for r in section} == {"101"} and len(section) < len(rows)
    assert repo.classification_rows("/us/pl/118/300") == ()
    assert repo.classification_rows("/us/pvtl/81/375") == ()


def test_classification_status_and_the_last_check(repo):
    status = repo.classification_status()
    assert [(f.congress, f.session, f.row_count) for f in status.files] == [(118, 2, 40), (104, 0, 40)]
    assert status.rows == 80 and status.congresses == (104, 118)
    assert status.files[0].covers(35) and status.files[0].covers(274) and not status.files[0].covers(300)
    check = repo.last_classification_check()
    assert check is not None and check.ok and not check.is_stale()
    assert check.source_url == str(CLASSIFICATIONS_FIXTURES) and check.files_seen == 31
    assert check.upstream_covered_text == UPSTREAM_COVERED and check.error is None
    assert status.last_check == check


def test_index_coverage_reads_the_tables(repo):
    covered = repo.index_coverage("/us/pl/118/35")
    assert (covered.classified, covered.tables_cover) == (True, True)
    beyond = repo.index_coverage("/us/pl/118/300")
    assert (beyond.classified, beyond.tables_cover) == (False, False)
    whole = repo.index_coverage("/us/pl/104/333")
    assert (whole.classified, whole.tables_cover) == (False, True)
