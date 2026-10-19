"""`GET /api/v1/search` over a fake OpenSearch client through the
`search_client_dependency` override. No cluster: the query building is
`tests/test_searchquery.py`'s and the mapping is `tests/test_search_mapping.py`'s;
this is the route's own contract. `api_client` answers `act_matches` from a
fake repository; the `acts` tests use the fixture database (`client`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.alternatives import USCODE_ORIGIN
from api.search import search_client_dependency
from main import app
from params import SEARCH_UNAVAILABLE
from storage import get_repository

ROUTE = "/api/v1/search"

HIT_RESPONSE = {
    "hits": {
        "total": {"value": 1},
        "hits": [
            {
                "_source": {
                    "identifier": "/us/pl/81/740/s3",
                    "law_identifier": "/us/pl/81/740",
                    "law_label": "Public Law 81-740",
                    "level": "section",
                    "num": "3",
                    "heading": "Definitions",
                    "enacted": "1950-08-30",
                    "citation": "64 Stat. 563",
                    "view": "enacted",
                },
                "highlight": {"text": ["a <em>wild</em> horse"]},
            }
        ],
    },
    "aggregations": {
        "congress": {"buckets": [{"key": 81, "doc_count": 1}]},
        "kind": {"buckets": [{"key": "pl", "doc_count": 1}]},
        "view": {"buckets": [{"key": "enacted", "doc_count": 1}]},
    },
}


class FakeSearchClient:
    """Records the body it was asked and answers a canned response, or
    raises what the test hands it."""

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def search(self, index, body):
        self.calls.append((index, body))
        if self.error is not None:
            raise self.error
        return self.response


class FakeRepository:
    """`act_matches` alone: records the text it was asked, and answers
    nothing or raises what the test hands it."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.asked: list[str] = []

    def act_matches(self, query, *, limit=5):
        self.asked.append(query)
        if self.error is not None:
            raise self.error
        return []


@pytest.fixture()
def fake_repository():
    return FakeRepository()


@pytest.fixture()
def api_client(fake_repository):
    """The session's `client` may already have put the fixture database's
    repository in `get_repository`'s place; that override is put back."""
    previous = app.dependency_overrides.get(get_repository)
    app.dependency_overrides[get_repository] = lambda: fake_repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(search_client_dependency, None)
    if previous is None:
        app.dependency_overrides.pop(get_repository, None)
    else:
        app.dependency_overrides[get_repository] = previous


@pytest.fixture()
def acts_client(client):
    """The fixture database's repository and a cluster with no hits."""
    _use(FakeSearchClient(response={"hits": {"total": {"value": 0}, "hits": []}}))
    yield client
    app.dependency_overrides.pop(search_client_dependency, None)


def _use(fake: FakeSearchClient) -> None:
    app.dependency_overrides[search_client_dependency] = lambda: fake


def test_a_hit_with_a_highlight_becomes_a_result(api_client):
    fake = FakeSearchClient(response=HIT_RESPONSE)
    _use(fake)

    response = api_client.get(ROUTE, params={"q": "wild horses"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    result = body["results"][0]
    assert result["identifier"] == "/us/pl/81/740/s3"
    assert result["url"] == "https://statutes.linkedlegislation.org/us/pl/81/740/s3"
    assert result["snippets"] == ["a <em>wild</em> horse"]
    assert result["law_label"] == "Public Law 81-740"
    assert body["facets"]["congress"] == [{"value": "81", "count": 1}]
    assert body["note"] == "Results are the sections and headings of the laws as enacted."


def test_a_cluster_failure_answers_503_with_the_exact_sentence(api_client):
    _use(FakeSearchClient(error=RuntimeError("cluster is down at opensearch:9200")))

    response = api_client.get(ROUTE, params={"q": "wild horses"})

    assert response.status_code == 503
    assert response.json()["detail"] == SEARCH_UNAVAILABLE == "search is unavailable; try again shortly"


def test_a_query_of_only_a_view_is_a_400(api_client):
    """`storage.searchquery.ParsedQuery.is_empty` is exercised directly in
    `tests/test_searchquery.py`: a filter alone (`kind:pl`) is a valid search
    for that filter, but `view:` alone leaves nothing to search for."""
    fake = FakeSearchClient()
    _use(fake)

    response = api_client.get(ROUTE, params={"q": "view:compiled"})

    assert response.status_code == 400
    assert response.json()["detail"] == "that query has nothing to search for"
    assert fake.calls == []


def test_a_bad_sort_is_a_400(api_client):
    fake = FakeSearchClient()
    _use(fake)

    response = api_client.get(ROUTE, params={"q": "wild horses", "sort": "nonsense"})

    assert response.status_code == 400
    assert fake.calls == []


def test_offset_past_the_maximum_is_a_422(api_client):
    _use(FakeSearchClient())

    response = api_client.get(ROUTE, params={"q": "wild horses", "offset": 1001})

    assert response.status_code == 422


def test_view_all_passes_through_to_the_body(api_client):
    fake = FakeSearchClient(response=HIT_RESPONSE)
    _use(fake)

    response = api_client.get(ROUTE, params={"q": "wild horses", "view": "all"})

    assert response.status_code == 200
    _, body = fake.calls[0]
    assert not [f for f in body["query"]["bool"]["filter"] if "view" in str(f)]
    assert response.json()["note"] == (
        "Results are the sections and headings of the laws as enacted and as compiled; "
        "a section can appear twice."
    )


def test_the_query_wins_over_the_view_parameter(api_client):
    fake = FakeSearchClient(response=HIT_RESPONSE)
    _use(fake)

    response = api_client.get(ROUTE, params={"q": "wild horses view:compiled", "view": "all"})

    assert response.status_code == 200
    assert response.json()["note"] == "Results are the sections and headings of the Statute Compilations' current text."


def test_an_unconfigured_cluster_answers_503_with_the_same_sentence(api_client, monkeypatch):
    """A deployment without `SEARCH_PASSWORD` (the box until the password is
    typed into `.env`) answers 503, not 500. An empty value in the environment
    wins over a password in the shell or in `.env`."""
    from main import app
    from storage.search import reset_search_client

    app.dependency_overrides.pop(search_client_dependency, None)
    monkeypatch.setenv("SEARCH_PASSWORD", "")
    reset_search_client()

    response = api_client.get(ROUTE, params={"q": "wild horses"})

    assert response.status_code == 503
    assert response.json()["detail"] == SEARCH_UNAVAILABLE


def test_the_first_page_asks_for_acts_and_later_pages_do_not(api_client, fake_repository):
    _use(FakeSearchClient(response=HIT_RESPONSE))

    assert api_client.get(ROUTE, params={"q": "wild horses congress:81"}).json()["acts"] == []
    api_client.get(ROUTE, params={"q": "wild horses", "offset": 20})

    assert fake_repository.asked == ["wild horses"]


def test_a_failing_act_lookup_still_answers_the_results(api_client, fake_repository):
    fake_repository.error = RuntimeError("database is down")
    _use(FakeSearchClient(response=HIT_RESPONSE))

    response = api_client.get(ROUTE, params={"q": "wild horses"})

    assert response.status_code == 200
    assert response.json()["total"] == 1 and response.json()["acts"] == []


def test_search_surfaces_matched_act_and_canonical_usc(acts_client):
    response = acts_client.get(ROUTE, params={"q": "Atomic energy act of 1954"})
    assert response.status_code == 200
    acts = response.json()["acts"]
    assert [a["title"] for a in acts] == ["Atomic Energy Act of 1954"]
    act = acts[0]
    assert act["compilation"] == {
        "identifier": "/us/sComp/83/703",
        "package_id": "COMPS-1630",
        "current_through": {"pl": "118-67", "enacted": "2024-07-09"},
        "url": "/app/us/sComp/83/703",
    }

    assert act["law"]["identifier"] == "/us/pl/83/703"
    assert act["law"]["label"] == "Public Law 83-703"
    assert "/us/act/1954-08-30/ch1073" in act["law"]["aliases"]
    assert act["law"]["citation"] == "68 Stat. 919"
    assert act["law"]["enacted"] == "1954-08-30"

    usc = act["canonical_usc"]
    assert usc["identifier"] == "/us/usc/t42/s2011"
    assert usc["citation"] == "42 U.S.C. § 2011"
    assert usc["heading"] == "Congressional declaration of policy"
    assert usc["url"] == f"{USCODE_ORIGIN}/us/usc/t42/s2011"
    assert (usc["context"], usc["note_topic"]) == ("note", "shortTitle")
    assert usc["citing_sections_count"] >= 8
    assert usc["history"][3] == {
        "identifier": "/us/pl/102/486/tIX/s902/a/8",
        "label": "Public Law 102-486, title IX, § 902(a)(8)",
        "date": "1992-10-24",
    }


def test_a_word_in_every_title_names_no_act(acts_client):
    assert acts_client.get(ROUTE, params={"q": "act"}).json()["acts"] == []
