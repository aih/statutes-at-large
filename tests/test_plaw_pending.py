"""`plaw pending` and what `/api/v1/cite` says about a law that has been
enacted and is not loaded (ADR-0031). The listing is
`tests/fixtures/congress-gov/law-119-pub.json`."""

import datetime
import json

import pytest
from sqlalchemy import delete

from db.models import PendingLaw
from ingest.plaw_pending import bill_url, current_congress, ordinal, parse_listing, record_pending
from tests.conftest import FIXTURES

LISTING = FIXTURES / "congress-gov" / "law-119-pub.json"
CITE = "/api/v1/cite"
NOW = datetime.datetime(2026, 10, 13, tzinfo=datetime.timezone.utc)


@pytest.fixture()
def pending(db):
    listed = parse_listing(json.loads(LISTING.read_text()), 119)
    report = record_pending(db, 119, listed, now=NOW)
    db.commit()
    yield report
    db.execute(delete(PendingLaw))
    db.commit()


def test_current_congress():
    assert current_congress(datetime.date(2026, 10, 13)) == 119
    assert current_congress(datetime.date(2025, 1, 3)) == 119
    assert current_congress(datetime.date(2025, 1, 2)) == 118
    assert current_congress(datetime.date(2027, 1, 3)) == 120


def test_ordinal_and_bill_url():
    assert [ordinal(n) for n in (1, 2, 3, 11, 12, 13, 21, 112, 119, 121, 122)] == [
        "1st", "2nd", "3rd", "11th", "12th", "13th", "21st", "112th", "119th", "121st", "122nd",
    ]
    assert bill_url(119, "HR", "9001") == "https://www.congress.gov/bill/119th-congress/house-bill/9001"
    assert bill_url(119, "SJRES", "77") == "https://www.congress.gov/bill/119th-congress/senate-joint-resolution/77"


def test_parse_listing_keeps_the_public_laws_of_the_congress():
    listed = parse_listing(json.loads(LISTING.read_text()), 119)
    assert [law.identifier for law in listed] == ["/us/pl/119/120", "/us/pl/119/119", "/us/pl/119/1"]
    first = listed[0]
    assert (first.bill_type, first.bill_number, first.action_date) == ("HR", "9001", datetime.date(2026, 10, 2))
    assert parse_listing(json.loads(LISTING.read_text()), 118) == []


def test_a_loaded_law_is_not_pending(pending):
    assert pending.listed == 3
    assert pending.loaded == 1
    assert pending.pending == ["/us/pl/119/119", "/us/pl/119/120"]


def test_a_run_replaces_the_congress_rows(db, pending, repo):
    listed = [law for law in parse_listing(json.loads(LISTING.read_text()), 119) if law.number != 119]
    report = record_pending(db, 119, listed, now=NOW)
    db.commit()
    assert report.pending == ["/us/pl/119/120"]
    assert repo.pending_law("/us/pl/119/119") is None


def test_the_repository_answers_a_pending_law(pending, repo):
    law = repo.pending_law("/us/pl/119/120")
    assert law is not None
    assert law.bill_label == "H.R. 9001"
    assert law.congress_gov_url == "https://www.congress.gov/bill/119th-congress/house-bill/9001"
    assert repo.pending_law("/us/pl/119/1") is None


@pytest.mark.parametrize("q", ["PL 119-120", "119-120", "Pub. L. 119-120, § 2", "/us/pl/119/120"])
def test_cite_says_a_pending_law_is_enacted_and_links_congress_gov(client, pending, q):
    body = client.get(CITE, params={"q": q}).json()
    assert body["exists"] is False
    assert body["pending"]["identifier"] == "/us/pl/119/120"
    assert body["pending"]["bill"] == "H.R. 9001"
    assert body["pending"]["url"] == "https://www.congress.gov/bill/119th-congress/house-bill/9001"
    assert body["message"] == (
        "Public Law 119-120 has been enacted, and its text is not on this site yet: a law is loaded once GPO "
        "publishes its enrolled text. Congress.gov has the law as H.R. 9001 at "
        "https://www.congress.gov/bill/119th-congress/house-bill/9001."
    )


def test_cite_says_nothing_more_for_a_law_congress_gov_does_not_list(client, pending):
    body = client.get(CITE, params={"q": "119-121"}).json()
    assert body["exists"] is False
    assert body["pending"] is None
    assert body["message"] is None


def test_fetch_listing_pages_until_a_short_page():
    from ingest.plaw_pending import PAGE_SIZE, fetch_listing

    bill = json.loads(LISTING.read_text())["bills"][0]

    class Client:
        def __init__(self):
            self.offsets = []

        def get_json(self, url, params):
            assert url == "https://api.congress.gov/v3/law/119/pub"
            self.offsets.append(params["offset"])
            count = PAGE_SIZE if params["offset"] == 0 else 1
            return {"bills": [bill] * count}

    client = Client()
    assert len(list(fetch_listing(client, 119))) == PAGE_SIZE + 1
    assert client.offsets == [0, PAGE_SIZE]


def test_parse_listing_with_laws_shape():
    laws_payload = {
        "laws": [
            {
                "number": "119-120",
                "type": "Public Law",
                "title": "A public law",
                "latestAction": {"actionDate": "2026-10-02"},
                "bill": {"type": "HR", "number": "9001"},
            },
            {
                "number": "119-2",
                "type": "Private Law",
                "bill": {"type": "HR", "number": "8000"},
            },
        ]
    }
    listed = parse_listing(laws_payload, 119)
    assert len(listed) == 1
    assert listed[0].identifier == "/us/pl/119/120"
    assert listed[0].bill_type == "HR"
    assert listed[0].bill_number == "9001"
    assert listed[0].action_date == datetime.date(2026, 10, 2)


def test_cmd_pending_with_fake_client(monkeypatch, tmp_path, session_factory):
    from argparse import Namespace
    from ingest.plaw_pending import cmd_pending

    data = json.loads(LISTING.read_text())

    class FakeClient:
        def get_json(self, url, params):
            return data

        def close(self):
            pass

    monkeypatch.setattr("ingest.govinfo.GovInfoClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("db.base.SessionLocal", session_factory)
    args = Namespace(congress=[119], from_file=None, report=str(tmp_path))
    ret = cmd_pending(args)
    assert ret == 0

    report_file = tmp_path / "plaw-pending.json"
    assert report_file.exists()
    saved = json.loads(report_file.read_text())
    assert saved["congresses"][0]["congress"] == 119
    assert saved["congresses"][0]["listed"] == 3

    with session_factory() as session:
        session.execute(delete(PendingLaw))
        session.commit()

