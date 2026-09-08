"""`GET /api/v1/cite` over the loaded slices: the three answers (422, `exists:
false`, `exists: true`), the resolution rules behind a hit, the US Code
hand-off, the note wording, and the headers."""

from params import LIMITERS, cite_not_a_citation

CITE = "/api/v1/cite"
ORIGIN = "https://statutes.linkedlegislation.org"
USCODE = "https://uscode.linkedlegislation.org"
KEYS = {
    "query", "kind", "identifier", "section_identifier", "law_identifier", "label", "exists",
    "served_identifier", "resolution", "level", "num", "heading", "law_label", "url", "stat_page",
    "hierarchy", "note", "message",
}


def test_not_a_citation_is_422_naming_the_forms(client):
    response = client.get(CITE, params={"q": "garbage"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail == cite_not_a_citation("garbage")
    assert "'Pub. L. 104-333, § 814'" in detail and "'43 U.S.C. 1701'" in detail
    assert client.get(CITE, params={"q": "523"}).status_code == 422
    assert client.get(CITE).status_code == 422


def test_a_section_of_a_public_law(client):
    response = client.get(CITE, params={"q": "Pub. L. 81-740, § 3"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == KEYS
    assert body["exists"] is True
    assert body["kind"] == "pl"
    assert body["identifier"] == "/us/pl/81/740/s3"
    assert body["section_identifier"] == "/us/pl/81/740/s3"
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["resolution"] == "exact"
    assert body["law_identifier"] == "/us/pl/81/740"
    assert body["law_label"] == "Public Law 81-740"
    assert body["label"] == "Public Law 81-740, section 3"
    assert body["level"] == "section" and body["num"] == "3"
    assert body["url"] == f"{ORIGIN}/us/pl/81/740/s3"
    assert body["note"] == "Public Law 81-740, section 3 is /us/pl/81/740/s3, which is loaded here."
    assert body["message"] is None


def test_a_provision_below_a_section(client):
    body = client.get(CITE, params={"q": "Pub. L. 81-740, § 3(a)"}).json()
    assert body["identifier"] == "/us/pl/81/740/s3/a"
    assert body["section_identifier"] == "/us/pl/81/740/s3"
    assert body["exists"] is True
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["url"] == f"{ORIGIN}/us/pl/81/740/s3/a"


def test_a_provision_the_section_does_not_have(client):
    body = client.get(CITE, params={"q": "Pub. L. 81-740, § 3(z)(9)"}).json()
    assert body["exists"] is True
    assert body["resolution"] == "prefix"
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["message"] == "/us/pl/81/740/s3/z/9 is not in the text of /us/pl/81/740/s3."


def test_a_chapter_era_law_by_date_and_chapter_resolves_through_its_alias(client):
    body = client.get(CITE, params={"q": "Aug. 30, 1950, ch. 823, § 3"}).json()
    assert body["exists"] is True
    assert body["kind"] == "pl"
    assert body["identifier"] == "/us/act/1950-08-30/ch823/s3"
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["resolution"] == "alias"
    assert body["law_identifier"] == "/us/pl/81/740"
    assert body["url"] == f"{ORIGIN}/us/act/1950-08-30/ch823/s3"
    assert body["note"] == (
        "Act of August 30, 1950, ch. 823, section 3 is /us/act/1950-08-30/ch823/s3, which is loaded here. "
        "It is served as /us/pl/81/740/s3, the same law under its other identifier."
    )


def test_a_section_under_another_hierarchy_is_found_by_number(client):
    body = client.get(CITE, params={"q": "Pub. L. 118-22, § 101"}).json()
    assert body["exists"] is True
    assert body["identifier"] == "/us/pl/118/22/s101"
    assert body["served_identifier"].endswith("/s101")
    if body["served_identifier"] != "/us/pl/118/22/s101":
        assert body["resolution"] == "section_number"
        assert "the section numbered 101 in this law is at" in body["note"]


def test_a_hierarchy_in_the_citation_is_reported_not_resolved(client):
    body = client.get(CITE, params={"q": "Pub. L. 118–22, title I, § 101"}).json()
    assert body["hierarchy"] == ["tI"]
    assert body["identifier"] == "/us/pl/118/22/s101"


def test_a_law_that_is_not_loaded_is_exists_false(client):
    response = client.get(CITE, params={"q": "Pub. L. 104-333, § 814"})
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["identifier"] == "/us/pl/104/333/s814"
    assert body["law_identifier"] == "/us/pl/104/333"
    assert body["served_identifier"] is None and body["url"] is None
    assert body["note"] == "Public Law 104-333, section 814 is /us/pl/104/333/s814; nothing is loaded there."


def test_a_private_law(client):
    body = client.get(CITE, params={"q": "Private Law 81-375"}).json()
    assert body["exists"] is True and body["kind"] == "pvtl"
    assert body["served_identifier"] == "/us/pvtl/81/375"
    assert body["level"] == "law"


def test_a_stat_page(client):
    body = client.get(CITE, params={"q": "64 Stat. 563"}).json()
    assert body["exists"] is True
    assert body["kind"] == "stat"
    assert body["identifier"] == "/us/stat/64/563"
    assert body["served_identifier"] == "/us/stat/64/563"
    assert body["level"] == "page" and body["num"] == "563"
    assert body["url"] == f"{ORIGIN}/us/stat/64/563"
    assert body["note"] == "64 Stat. 563 is /us/stat/64/563, which is loaded here."


def test_a_stat_page_in_a_volume_not_loaded(client):
    body = client.get(CITE, params={"q": "110 Stat. 4196"}).json()
    assert body["exists"] is False
    assert body["identifier"] == "/us/stat/110/4196"
    assert body["note"] == "110 Stat. 4196 is /us/stat/110/4196; no loaded law prints on that page."


def test_a_chapter_with_its_page_resolves_to_the_law_on_the_page(client):
    body = client.get(CITE, params={"q": "ch. 823, 64 Stat. 563"}).json()
    assert body["exists"] is True
    assert body["kind"] == "pl"
    assert body["identifier"] == "/us/pl/81/740"
    assert body["served_identifier"] == "/us/pl/81/740"
    assert body["label"] == "Public Law 81-740"
    with_section = client.get(CITE, params={"q": "ch. 823, 64 Stat. 563, § 3"}).json()
    assert with_section["identifier"] == "/us/pl/81/740/s3"
    assert with_section["section_identifier"] == "/us/pl/81/740/s3"
    assert with_section["label"] == "Public Law 81-740, section 3"


def test_a_chapter_absent_from_its_page_serves_the_page(client):
    body = client.get(CITE, params={"q": "ch. 999, 64 Stat. 563"}).json()
    assert body["exists"] is True
    assert body["kind"] == "stat"
    assert body["identifier"] == "/us/stat/64/563"
    assert body["message"] == (
        "The page /us/stat/64/563 is loaded, and no law on it is chapter 999; the page's documents are served."
    )


def test_a_stat_page_beside_a_law_is_carried(client):
    body = client.get(CITE, params={"q": "Pub. L. 81-740, § 3, 64 Stat. 563"}).json()
    assert body["identifier"] == "/us/pl/81/740/s3"
    assert body["stat_page"] == "/us/stat/64/563"


def test_a_compilation_identifier(client):
    body = client.get(CITE, params={"q": "/us/sComp/83/703/tI/ch1./s1"}).json()
    assert body["exists"] is True
    assert body["kind"] == "sComp"
    assert body["served_identifier"] == "/us/sComp/83/703/tI/ch1./s1"
    assert body["law_identifier"] == "/us/pl/83/703"
    assert body["url"] == f"{ORIGIN}/us/sComp/83/703/tI/ch1./s1"
    missing = client.get(CITE, params={"q": "/us/sComp/99/1"}).json()
    assert missing["exists"] is False


def test_a_us_code_citation_is_handed_to_the_us_code_site(client):
    response = client.get(CITE, params={"q": "43 U.S.C. 1701"})
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "usc"
    assert body["exists"] is None
    assert body["identifier"] == "/us/usc/t43/s1701"
    assert body["url"] == f"{USCODE}/us/usc/t43/s1701"
    assert body["law_identifier"] is None
    assert body["note"] == (
        "43 U.S.C. 1701 is a United States Code citation, /us/usc/t43/s1701; the US Code site serves it "
        f"at {USCODE}/us/usc/t43/s1701. It is not checked here."
    )
    deep = client.get(CITE, params={"q": "16 USC 45f(c)(5)"}).json()
    assert deep["identifier"] == "/us/usc/t16/s45f/c/5"
    assert deep["section_identifier"] == "/us/usc/t16/s45f"
    assert deep["url"] == f"{USCODE}/us/usc/t16/s45f/c/5"


def test_headers(client):
    response = client.get(CITE, params={"q": "Pub. L. 81-740, § 3"})
    assert response.headers["cache-control"] == "public, max-age=300"
    etag = response.headers["etag"]
    assert etag.startswith('"')
    again = client.get(CITE, params={"q": "Pub. L. 81-740, § 3"}, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert client.get(CITE, params={"q": "Pub. L. 104-333"}).headers["etag"] != etag


def test_cite_is_rate_limited_for_a_person(client):
    limiter = LIMITERS["cite"]
    assert limiter.capacity == 60 and limiter.per_second == 2.0
    while limiter.check("testclient") is None:
        pass
    response = client.get(CITE, params={"q": "Pub. L. 81-740"})
    assert response.status_code == 429
    assert response.headers["retry-after"]
