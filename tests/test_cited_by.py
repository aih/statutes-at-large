"""`GET /api/v1/cited-by` over the loaded slices and the citation fixture,
and the `citations` and `classifications` blocks of `/api/v1/status`."""

from __future__ import annotations

from params import LIMITERS, cited_by_note

ROUTE = "/api/v1/cited-by"
KEYS = {
    "identifier", "law_identifier", "law", "aliases", "section_num", "below", "contexts", "total",
    "limit", "offset", "release_labels", "index", "sections", "note",
}
SECTION_KEYS = {"identifier", "citation", "heading", "release_label", "url", "refs"}
REF_KEYS = {"href", "context", "note_topic", "date"}


def _get(client, identifier: str, **params):
    return client.get(ROUTE, params={"identifier": identifier, **params})


# --------------------------------------------------------------------- shape


def test_the_shape_through_the_chapter_alias(client):
    """The Code cites the Atomic Energy Act as `/us/act/1954-08-30/ch1073`;
    the public-law form answers with the law loaded from volume 68."""
    response = _get(client, "/us/pl/83/703/s1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"].startswith('"')
    body = response.json()
    assert set(body) == KEYS
    assert body["identifier"] == "/us/pl/83/703/s1" and body["law_identifier"] == "/us/pl/83/703"
    assert body["law"]["identifier"] == "/us/pl/83/703" and body["law"]["label"] == "Public Law 83-703"
    assert set(body["aliases"]) == {"/us/pl/83/703", "/us/act/1954-08-30/ch1073"}
    assert body["section_num"] == "1" and body["below"] is None
    assert body["contexts"] == {"note": 7, "sourceCredit": 8}
    assert body["total"] == 8 and body["limit"] == 50 and body["offset"] == 0
    assert body["release_labels"] == ["119-83"]
    assert set(body["index"]) == {"release_labels", "loaded_at", "dataset_revision"}
    assert body["index"]["dataset_revision"] == "fixture"
    assert [label for label, _ in body["index"]["release_labels"]][:1] == ["119-83"]
    assert len(body["sections"]) == 8
    first = body["sections"][0]
    assert set(first) == SECTION_KEYS
    assert first["identifier"] == "/us/usc/t42/s2011" and first["citation"] == "42 U.S.C. § 2011"
    assert first["url"] == "https://uscode.linkedlegislation.org/us/usc/t42/s2011"
    assert first["release_label"] == "119-83"
    assert first["refs"] and set(first["refs"][0]) == REF_KEYS
    assert all(r["href"].startswith("/us/act/1954-08-30/ch1073") for r in first["refs"])
    assert {r["context"] for s in body["sections"] for r in s["refs"]} == {"sourceCredit", "note"}


def test_an_unloaded_law_answers_from_the_index_alone(client):
    body = _get(client, "/us/pl/104/333/s814").json()
    assert body["law"] is None and body["law_identifier"] == "/us/pl/104/333"
    assert body["aliases"] == ["/us/pl/104/333"]
    assert body["total"] == 5
    section = next(s for s in body["sections"] if s["identifier"] == "/us/usc/t16/s1")
    assert section["citation"] == "16 U.S.C. § 1" and section["release_label"] == "119-102not101"
    assert section["refs"] == [
        {"href": "/us/pl/104/333/dI/tVIII/s814/e/1", "context": "note", "note_topic": "removalDescription", "date": "1996-11-12"}
    ]
    below = _get(client, "/us/pl/104/333/s814/e/1").json()
    assert below["below"] == "e/1" and below["total"] == 1 and below["sections"][0]["identifier"] == "/us/usc/t16/s1"


def test_identifier_forms_are_normalized(client):
    assert _get(client, "us/pl/83/703/s1/").json()["identifier"] == "/us/pl/83/703/s1"


# --------------------------------------------------------------- not found


def test_404_names_the_citation_index(client):
    response = _get(client, "/us/pl/104/333/s814/f")
    assert response.status_code == 404
    assert response.json() == {"detail": "nothing at /us/pl/104/333/s814/f in the citation index"}
    assert _get(client, "/us/pl/81/999999").status_code == 404
    assert _get(client, "/us/stat/1/1").status_code == 404


def test_a_loaded_law_nothing_cites_is_an_empty_200(client):
    body = _get(client, "/us/pvtl/81/375").json()
    assert body["law"]["identifier"] == "/us/pvtl/81/375"
    assert body["total"] == 0 and body["sections"] == [] and body["contexts"] == {} and body["release_labels"] == []
    assert body["note"].startswith(
        "Sections of the United States Code whose source credits, notes, or text cite Private Law 81-375: no sections"
    )


def test_422s(client):
    assert _get(client, "/us/sComp/83/703/s1").status_code == 422
    assert _get(client, "/us/usc/t42/s2011").status_code == 422
    assert _get(client, "/us/pl/83/703", context="footnote").status_code == 422
    assert _get(client, "/us/pl/83/703", limit=0).status_code == 422
    assert _get(client, "/us/pl/83/703", limit=201).status_code == 422
    assert _get(client, "/us/pl/83/703", offset=-1).status_code == 422
    assert client.get(ROUTE).status_code == 422


# ------------------------------------------------------ contexts and paging


def test_context_narrows_the_answer(client):
    everything = _get(client, "/us/act/1890-07-02/ch647").json()
    assert everything["contexts"] == {"note": 1, "sourceCredit": 8} and everything["total"] == 8
    credits = _get(client, "/us/act/1890-07-02/ch647", context="sourceCredit").json()
    assert credits["contexts"] == {"sourceCredit": 8}
    assert all(r["context"] == "sourceCredit" for s in credits["sections"] for r in s["refs"])
    notes = _get(client, "/us/act/1890-07-02/ch647", context="note").json()
    assert notes["contexts"] == {"note": 1} and notes["total"] == 1
    both = client.get(ROUTE, params=[("identifier", "/us/act/1890-07-02/ch647"), ("context", "note"), ("context", "text")]).json()
    assert both["contexts"] == {"note": 1}


def test_paging(client):
    page = _get(client, "/us/act/1890-07-02/ch647", limit=2, offset=2).json()
    assert page["limit"] == 2 and page["offset"] == 2 and page["total"] == 8
    assert [s["identifier"] for s in page["sections"]] == ["/us/usc/t15/s3", "/us/usc/t15/s4"]
    first = _get(client, "/us/act/1890-07-02/ch647", limit=2).json()
    assert [s["identifier"] for s in first["sections"]] == ["/us/usc/t15/s1", "/us/usc/t15/s2"]
    beyond = _get(client, "/us/act/1890-07-02/ch647", limit=2, offset=100).json()
    assert beyond["sections"] == [] and beyond["total"] == 8


# ---------------------------------------------------------------- the note


def test_the_note_wording(client):
    section = _get(client, "/us/pl/83/703/s1").json()
    assert section["note"] == cited_by_note(what="section 1 of Public Law 83-703", total=8, release_labels=["119-83"])
    assert section["note"].startswith(
        "Sections of the United States Code whose source credits, notes, or text cite section 1 of "
        "Public Law 83-703: 8 sections, from the release points 119-83."
    )
    law = _get(client, "/us/act/1890-07-02/ch647").json()
    assert "cite Act of July 2, 1890, ch. 647: 8 sections" in law["note"]
    unloaded = _get(client, "/us/pl/104/333/s814").json()
    assert "cite section 814 of Public Law 104-333: 5 sections, from the release points 119-102not101." in unloaded["note"]
    below = _get(client, "/us/pl/104/333/s814/e/1").json()
    assert "cite section 814(e)(1) of Public Law 104-333: 1 section," in below["note"]
    node = _get(client, "/us/pl/104/333/dI/tVIII").json()
    assert "cite title VIII of division I of Public Law 104-333: 5 sections" in node["note"]
    page = _get(client, "/us/stat/92/3479").json()
    assert "cite page 3479 of volume 92 of the Statutes at Large: 1 section" in page["note"]
    assert page["sections"][0]["identifier"] == "/us/usc/t16/s45f"


# ---------------------------------------------------------------- caching


def test_etag_and_304(client):
    response = _get(client, "/us/pl/83/703/s1")
    etag = response.headers["etag"]
    again = _get(client, "/us/pl/83/703/s1")
    assert again.headers["etag"] == etag
    cached = client.get(ROUTE, params={"identifier": "/us/pl/83/703/s1"}, headers={"If-None-Match": etag})
    assert cached.status_code == 304 and cached.content == b"" and cached.headers["etag"] == etag
    assert client.get(ROUTE, params={"identifier": "/us/pl/83/703/s1"}, headers={"If-None-Match": f'W/{etag}, "other"'}).status_code == 304
    assert client.get(ROUTE, params={"identifier": "/us/pl/83/703/s1"}, headers={"If-None-Match": '"stale"'}).status_code == 200
    narrowed = _get(client, "/us/pl/83/703/s1", context="sourceCredit")
    assert narrowed.headers["etag"] != etag
    paged = _get(client, "/us/pl/83/703/s1", limit=2)
    assert paged.headers["etag"] not in (etag, narrowed.headers["etag"])


def test_cited_by_is_rate_limited_for_a_person(client):
    limiter = LIMITERS["cited-by"]
    assert limiter.capacity == 60 and limiter.per_second == 2.0
    # Drain the test client's bucket directly; the autouse fixture refills it.
    while limiter.check("testclient") is None:
        pass
    response = _get(client, "/us/pl/83/703/s1")
    assert response.status_code == 429
    assert response.headers["retry-after"]
    assert response.json() == {"detail": "too many requests; try again shortly"}


# ----------------------------------------------------------------- status


def test_status_carries_the_index_blocks(client):
    body = client.get("/api/v1/status").json()
    citations = body["citations"]
    assert set(citations) == {"rows", "citing_sections", "titles", "release_labels", "loaded_at", "dataset_revision"}
    assert citations["rows"] > 500 and citations["citing_sections"] == 57 and citations["titles"] == 9
    assert citations["dataset_revision"] == "fixture" and citations["loaded_at"]
    labels = citations["release_labels"]
    assert 1 <= len(labels) <= 10 and labels[0][0] == "119-83" and labels[0][1] >= labels[-1][1]
    classifications = body["classifications"]
    assert set(classifications) == {"files", "rows", "congresses", "last_check"}
    assert classifications["rows"] == 80 and classifications["congresses"] == [104, 118]
    files = classifications["files"]
    assert [set(f) for f in files] == [{"congress", "session", "covered_laws_text", "row_count", "mirrored_at"}] * 2
    assert [(f["congress"], f["session"], f["row_count"]) for f in files] == [(118, 2, 40), (104, 0, 40)]
    assert files[0]["covered_laws_text"] == "Public Laws 118-35 to 118-274" and files[0]["mirrored_at"]
    check = classifications["last_check"]
    assert set(check) == {"checked_at", "ok", "files_seen", "files_loaded", "rows_loaded", "upstream_checked_at", "error", "stale"}
    assert check["ok"] is True and check["stale"] is False and check["error"] is None
    assert check["files_seen"] == 31 and check["files_loaded"] in (0, 2) and check["rows_loaded"] in (0, 80)
    assert check["upstream_checked_at"].startswith("2026-09-08T06:41:10")
