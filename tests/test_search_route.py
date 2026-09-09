"""`GET /api/v1/search` over a fake OpenSearch client through the
`search_client_dependency` override. No cluster, no database: the query
building is `tests/test_searchquery.py`'s and the mapping is
`tests/test_search_mapping.py`'s; this is the route's own contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.search import search_client_dependency
from main import app
from params import SEARCH_UNAVAILABLE

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


@pytest.fixture()
def api_client():
    with TestClient(app) as test_client:
        yield test_client
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
    assert result["url"] == "/app/us/pl/81/740/s3"
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
