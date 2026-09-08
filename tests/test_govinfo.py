"""The GovInfo client, with httpx mocked by respx: the collection walk, the
key's placement and its absence from output, the retry, the missing key."""

import datetime
import logging

import httpx
import pytest
import respx

from ingest.govinfo import BASE_URL, GovInfoClient, GovInfoError, MissingApiKeyError, strip_query

KEY = "test-key-0123456789-abcdefghij"
SINCE = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
COLLECTION_URL = f"{BASE_URL}/collections/COMPS/2026-09-01T00:00:00Z"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", KEY)
    slept: list[float] = []
    with GovInfoClient(sleep=slept.append) as client:
        client.slept = slept  # type: ignore[attr-defined]
        yield client


@respx.mock
def test_the_collection_walk_follows_next_page(client):
    first = respx.get(COLLECTION_URL, params={"offsetMark": "*", "pageSize": "2", "api_key": KEY}).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 3,
                "packages": [
                    {"packageId": "COMPS-1", "lastModified": "2026-09-02T00:00:00Z"},
                    {"packageId": "COMPS-2", "lastModified": "2026-09-03T00:00:00Z"},
                ],
                "nextPage": f"{COLLECTION_URL}?offsetMark=AoJw&pageSize=2",
            },
        )
    )
    second = respx.get(COLLECTION_URL, params={"offsetMark": "AoJw", "pageSize": "2", "api_key": KEY}).mock(
        return_value=httpx.Response(
            200,
            json={"count": 3, "packages": [{"packageId": "COMPS-3", "lastModified": "2026-09-04T00:00:00Z"}], "nextPage": None},
        )
    )
    packages = list(client.collection("COMPS", SINCE, page_size=2))
    assert [p["packageId"] for p in packages] == ["COMPS-1", "COMPS-2", "COMPS-3"]
    assert first.called and second.called
    assert "offset=" not in str(second.calls.last.request.url)
    assert second.calls.last.request.url.params["api_key"] == KEY
    assert second.calls.last.request.headers["User-Agent"].startswith("statutes-linkedlegislation/")


@respx.mock
def test_a_naive_since_is_read_as_utc(client):
    route = respx.get(COLLECTION_URL).mock(return_value=httpx.Response(200, json={"packages": [], "nextPage": None}))
    assert list(client.collection("COMPS", datetime.datetime(2026, 9, 1))) == []
    assert route.called


@respx.mock
def test_summary_and_uslm(client):
    respx.get(f"{BASE_URL}/packages/COMPS-1630/summary").mock(return_value=httpx.Response(200, json={"packageId": "COMPS-1630"}))
    respx.get(f"{BASE_URL}/packages/COMPS-1630/uslm").mock(
        return_value=httpx.Response(200, content='<?xml version="1.0" encoding="UTF-8"?><statuteCompilation/>'.encode(), headers={"Content-Type": "application/xml"})
    )
    assert client.summary("COMPS-1630") == {"packageId": "COMPS-1630"}
    assert client.uslm("COMPS-1630").endswith("<statuteCompilation/>")


@respx.mock
def test_the_key_is_in_the_query_and_nowhere_visible(client, caplog):
    route = respx.get(f"{BASE_URL}/packages/COMPS-1/summary").mock(return_value=httpx.Response(200, json={}))
    with caplog.at_level(logging.DEBUG):
        client.summary("COMPS-1")
    assert route.calls.last.request.url.params["api_key"] == KEY
    assert KEY not in repr(client) and KEY not in str(client)
    assert "api_key=<set>" in repr(client)
    assert KEY not in caplog.text
    httpx_lines = [r for r in caplog.records if r.name == "httpx"]
    if httpx_lines:
        assert "api_key=REDACTED" in caplog.text


@respx.mock
def test_errors_carry_no_query_string(client):
    respx.get(f"{BASE_URL}/packages/COMPS-404/summary").mock(return_value=httpx.Response(404, json={"message": "no"}))
    with pytest.raises(GovInfoError) as excinfo:
        client.summary("COMPS-404")
    message = str(excinfo.value)
    assert message == f"HTTP 404 for {BASE_URL}/packages/COMPS-404/summary"
    assert KEY not in message and "?" not in message


@respx.mock
def test_429_is_retried_once_after_retry_after(client):
    route = respx.get(f"{BASE_URL}/packages/COMPS-9/summary").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={"packageId": "COMPS-9"})]
    )
    assert client.summary("COMPS-9") == {"packageId": "COMPS-9"}
    assert route.call_count == 2
    assert client.slept == [3.0]


@respx.mock
def test_a_second_failure_is_raised(client):
    route = respx.get(f"{BASE_URL}/packages/COMPS-9/summary").mock(
        side_effect=[httpx.Response(503), httpx.Response(503)]
    )
    with pytest.raises(GovInfoError, match="HTTP 503"):
        client.summary("COMPS-9")
    assert route.call_count == 2


@respx.mock
def test_a_connection_error_is_retried_then_wrapped(client):
    route = respx.get(f"{BASE_URL}/packages/COMPS-9/uslm").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(GovInfoError, match="ConnectError"):
        client.uslm("COMPS-9")
    assert route.call_count == 2


def test_a_missing_key_raises(monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "")
    with pytest.raises(MissingApiKeyError, match="GOVINFO_API_KEY"):
        GovInfoClient()
    monkeypatch.delenv("GOVINFO_API_KEY")
    with pytest.raises(MissingApiKeyError):
        GovInfoClient()
    monkeypatch.setenv("GOVINFO_API_KEY", KEY)
    assert repr(GovInfoClient()).endswith("api_key=<set>)")


def test_strip_query():
    assert strip_query("HTTP 500 for https://x/y?api_key=abc&z=1: bad") == "HTTP 500 for https://x/y: bad"
    assert strip_query("no query here") == "no query here"
