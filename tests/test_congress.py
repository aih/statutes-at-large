"""Tests for Congress historical analysis: helpers, repository methods, and API routes.

Issue #19.
"""

from __future__ import annotations

import datetime

import pytest

from storage import (
    congress_of_date,
    congress_ordinal,
    congress_years,
)


# --------------------------------------------------------------- pure helpers


def test_congress_ordinal():
    assert congress_ordinal(1) == "1st"
    assert congress_ordinal(2) == "2nd"
    assert congress_ordinal(3) == "3rd"
    assert congress_ordinal(4) == "4th"
    assert congress_ordinal(10) == "10th"
    assert congress_ordinal(11) == "11th"
    assert congress_ordinal(12) == "12th"
    assert congress_ordinal(13) == "13th"
    assert congress_ordinal(21) == "21st"
    assert congress_ordinal(22) == "22nd"
    assert congress_ordinal(23) == "23rd"
    assert congress_ordinal(51) == "51st"
    assert congress_ordinal(74) == "74th"
    assert congress_ordinal(81) == "81st"
    assert congress_ordinal(83) == "83rd"
    assert congress_ordinal(111) == "111th"
    assert congress_ordinal(112) == "112th"
    assert congress_ordinal(113) == "113th"
    assert congress_ordinal(118) == "118th"
    assert congress_ordinal(119) == "119th"


def test_congress_years():
    assert congress_years(1) == (1789, 1791)
    assert congress_years(51) == (1889, 1891)
    assert congress_years(74) == (1935, 1937)
    assert congress_years(81) == (1949, 1951)
    assert congress_years(83) == (1953, 1955)
    assert congress_years(118) == (2023, 2025)
    assert congress_years(119) == (2025, 2027)


def test_congress_of_date():
    # Before 1935: March 4 cutoff
    assert congress_of_date(datetime.date(1789, 3, 4)) == 1
    assert congress_of_date(datetime.date(1789, 4, 1)) == 1
    assert congress_of_date(datetime.date(1790, 5, 1)) == 1
    assert congress_of_date(datetime.date(1791, 3, 3)) == 1
    assert congress_of_date(datetime.date(1791, 3, 4)) == 2
    assert congress_of_date(datetime.date(1890, 7, 2)) == 51  # Sherman Act
    assert congress_of_date(datetime.date(1934, 6, 18)) == 73
    assert congress_of_date(datetime.date(1935, 1, 2)) == 73

    # From 1935: January 3 cutoff (Twentieth Amendment)
    assert congress_of_date(datetime.date(1935, 1, 3)) == 74
    assert congress_of_date(datetime.date(1950, 8, 30)) == 81  # Pub. L. 81-740
    assert congress_of_date(datetime.date(1954, 8, 30)) == 83  # Atomic Energy Act
    assert congress_of_date(datetime.date(2023, 1, 2)) == 117
    assert congress_of_date(datetime.date(2023, 1, 3)) == 118
    assert congress_of_date(datetime.date(2025, 1, 2)) == 118
    assert congress_of_date(datetime.date(2025, 1, 3)) == 119


# ---------------------------------------------------------- repository methods


def test_repo_congresses_overview(repo):
    overview = repo.congresses_overview()
    assert overview.total_congresses >= 7
    assert overview.total_laws > 0
    assert overview.total_sections > 0
    assert overview.total_compilations > 0

    congresses = {s.congress: s for s in overview.congresses}

    # 51st Congress (1890, Sherman Act chapter law)
    c51 = congresses.get(51)
    assert c51 is not None
    assert c51.ordinal == "51st"
    assert c51.start_year == 1889 and c51.end_year == 1891
    assert c51.chapter_acts >= 1
    assert c51.compilations_count >= 1
    assert c51.cited_laws_count >= 1
    assert c51.citing_sections_count >= 1
    assert 26 in c51.volumes

    # 81st Congress (1950, Public Law and Private Law)
    c81 = congresses.get(81)
    assert c81 is not None
    assert c81.public_laws >= 1
    assert c81.private_laws >= 1
    assert c81.section_count > 0
    assert 64 in c81.volumes

    # 83rd Congress (1954, Atomic Energy Act)
    c83 = congresses.get(83)
    assert c83 is not None
    assert c83.compilations_count >= 1
    assert c83.cited_laws_count >= 1
    assert 68 in c83.volumes

    # 118th Congress (PLAW and classifications)
    c118 = congresses.get(118)
    assert c118 is not None
    assert c118.public_laws >= 1
    assert c118.classified_laws_count >= 1
    assert len(c118.classification_sessions) >= 1


def test_repo_congress_detail_51st_sherman_act(repo):
    detail = repo.congress_detail(51)
    assert detail is not None
    assert detail.summary.congress == 51
    assert detail.total >= 1
    assert len(detail.laws) >= 1

    sherman = next((l for l in detail.laws if l.chapter == 647), None)
    assert sherman is not None
    assert sherman.kind == "act"
    assert sherman.identifier == "/us/act/1890-07-02/ch647"
    assert sherman.volume == 26
    assert sherman.section_count >= 1
    assert len(sherman.compilations) >= 1
    assert sherman.compilations[0].identifier_prefix == "/us/sComp/51/647"
    assert sherman.usc_citing_sections_count >= 1
    assert "15" in sherman.usc_titles


def test_repo_congress_detail_81st_filters_and_sorts(repo):
    detail = repo.congress_detail(81)
    assert detail is not None
    assert detail.total >= 2

    # Filter: kind="pl"
    pl_detail = repo.congress_detail(81, kind="pl")
    assert pl_detail is not None
    assert all(l.kind == "pl" for l in pl_detail.laws)
    assert any(l.number == 740 for l in pl_detail.laws)

    # Filter: kind="pvtl"
    pvtl_detail = repo.congress_detail(81, kind="pvtl")
    assert pvtl_detail is not None
    assert all(l.kind == "pvtl" for l in pvtl_detail.laws)

    # Filter: q
    q_detail = repo.congress_detail(81, q="740")
    assert q_detail is not None
    assert len(q_detail.laws) == 1
    assert q_detail.laws[0].number == 740

    # Sorts
    sort_seq = repo.congress_detail(81, sort="sequence")
    assert sort_seq is not None
    sort_date = repo.congress_detail(81, sort="date")
    assert sort_date is not None
    sort_sec = repo.congress_detail(81, sort="sections")
    assert sort_sec is not None
    assert sort_sec.laws[0].section_count >= sort_sec.laws[-1].section_count


def test_repo_congress_detail_83rd_comps_and_citations(repo):
    detail = repo.congress_detail(83, has_comp=True)
    assert detail is not None
    assert detail.total >= 1
    assert any(l.number == 703 for l in detail.laws)

    cited_detail = repo.congress_detail(83, cited=True)
    assert cited_detail is not None
    assert cited_detail.total >= 1
    assert any(l.number == 703 for l in cited_detail.laws)


def test_repo_congress_detail_unknown_congress(repo):
    assert repo.congress_detail(150) is None


# ------------------------------------------------------------------ API routes


def test_api_congresses_overview(client):
    response = client.get("/api/v1/congress")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "public, max-age=300"

    body = response.json()
    assert body["total_congresses"] >= 7
    assert body["total_laws"] > 0
    assert body["total_sections"] > 0
    assert body["total_compilations"] > 0
    assert "Acts enacted across" in body["note"]

    congresses = body["congresses"]
    assert len(congresses) >= 7

    # Check 51st Congress
    c51 = next((c for c in congresses if c["congress"] == 51), None)
    assert c51 is not None
    assert c51["ordinal"] == "51st"
    assert c51["url"] == "https://statutes.linkedlegislation.org/app/congress/51"
    assert c51["cited_laws_count"] >= 1

    # Check 118th Congress
    c118 = next((c for c in congresses if c["congress"] == 118), None)
    assert c118 is not None
    assert c118["ordinal"] == "118th"
    assert c118["url"] == "https://statutes.linkedlegislation.org/app/congress/118"
    assert len(c118["uscode_classification_urls"]) >= 1
    for item in c118["uscode_classification_urls"]:
        assert item["url"].startswith("https://uscode.linkedlegislation.org/app/classification/118/")


def test_api_congress_detail_51st(client):
    response = client.get("/api/v1/congress/51")
    assert response.status_code == 200

    body = response.json()
    assert body["summary"]["congress"] == 51
    assert body["summary"]["ordinal"] == "51st"
    assert "51st Congress" in body["note"]
    assert body["total"] >= 1

    sherman = next((l for l in body["laws"] if l["chapter"] == 647), None)
    assert sherman is not None
    assert sherman["identifier"] == "/us/act/1890-07-02/ch647"
    assert sherman["url"] == "https://statutes.linkedlegislation.org/app/us/act/1890-07-02/ch647"
    assert sherman["stat_url"] is not None
    assert sherman["stat_url"].startswith("https://statutes.linkedlegislation.org/app/us/stat/26/")
    assert len(sherman["compilations"]) >= 1
    assert sherman["compilations"][0]["url"] == "https://statutes.linkedlegislation.org/app/us/sComp/51/647"
    assert sherman["usc_citing_sections_count"] >= 1
    assert sherman["cited_by_url"] == "https://statutes.linkedlegislation.org/app/us/act/1890-07-02/ch647#cited-by"
    assert "15" in sherman["usc_titles"]


def test_api_congress_detail_query_filters(client):
    # Filter by kind
    r_pl = client.get("/api/v1/congress/81?kind=pl")
    assert r_pl.status_code == 200
    b_pl = r_pl.json()
    assert all(l["kind"] == "pl" for l in b_pl["laws"])

    r_pvtl = client.get("/api/v1/congress/81?kind=pvtl")
    assert r_pvtl.status_code == 200
    b_pvtl = r_pvtl.json()
    assert all(l["kind"] == "pvtl" for l in b_pvtl["laws"])

    # Filter has_comp
    r_comp = client.get("/api/v1/congress/83?has_comp=true")
    assert r_comp.status_code == 200
    b_comp = r_comp.json()
    assert b_comp["total"] >= 1
    assert any(l["number"] == 703 for l in b_comp["laws"])

    # Filter cited
    r_cited = client.get("/api/v1/congress/83?cited=true")
    assert r_cited.status_code == 200
    b_cited = r_cited.json()
    assert b_cited["total"] >= 1


def test_api_congress_detail_118th_classification_url(client):
    response = client.get("/api/v1/congress/118")
    assert response.status_code == 200
    body = response.json()
    # Find a law that has classification entries
    classified = next((l for l in body["laws"] if l["usc_classifications_count"] > 0), None)
    if classified is not None:
        assert classified["uscode_classification_url"] is not None
        assert classified["uscode_classification_url"].startswith(
            "https://uscode.linkedlegislation.org/app/classification/118/"
        )


def test_api_congress_detail_not_found_and_validation(client):
    # Unknown congress
    r_404 = client.get("/api/v1/congress/150")
    assert r_404.status_code == 404
    assert "150th Congress" in r_404.json()["detail"]

    # Path validation: ge=1, le=200
    r_low = client.get("/api/v1/congress/0")
    assert r_low.status_code == 422

    r_high = client.get("/api/v1/congress/201")
    assert r_high.status_code == 422
