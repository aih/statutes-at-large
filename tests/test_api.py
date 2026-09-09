"""The machine surface over the loaded slices: the response shape of design
section 4, the note sentences, both representations, the caching headers,
stat pages, labels, and status."""

import datetime
from xml.etree import ElementTree

from params import LIMITERS
from uslmtext import USLM_NS

SECTION = "/api/v1/us/pl/81/740/s3"
SECTION_KEYS = {
    "identifier", "served_identifier", "view", "law", "currency", "alternatives", "note",
    "provenance", "pages", "text", "xml_url",
    "level", "num", "heading", "resolution", "ancestors", "children", "provision", "occurrences",
}
ENACTED_NOTE_740 = (
    "This is section 3 of Public Law 81-740 as enacted on August 30, 1950 (64 Stat. 563). "
    "It is not updated. No later amendment of this section is recorded in the indexes here "
    "(the US Code's source credits, the classification tables, and the Statute Compilations); "
    "amendment may still have occurred. "
    "To check for later amendments: the classification tables at uscode.house.gov for laws "
    "after August 30, 1950."
)
"""Public Law 81-740 is cited by the US Code in notes only: `no_record`."""


# ------------------------------------------------------------- the section


def test_section_json_shape(client):
    response = client.get(SECTION)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == SECTION_KEYS
    assert body["identifier"] == "/us/pl/81/740/s3"
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["view"] == "enacted"
    assert body["resolution"] == "exact"
    assert body["level"] == "section" and body["num"] == "3"
    assert body["law"]["kind"] == "pl" and body["law"]["congress"] == 81 and body["law"]["number"] == 740
    assert body["law"]["chapter"] == 823
    assert body["law"]["label"] == "Public Law 81-740"
    assert body["law"]["aliases"] == ["/us/pl/81/740", "/us/act/1950-08-30/ch823"]
    assert body["law"]["enacted"] == "1950-08-30" and body["law"]["citation"] == "64 Stat. 563"
    assert body["law"]["source"] == {"collection": "STATUTE", "package": "STATUTE-64", "granule": None}
    assert body["currency"]["kind"] == "as_enacted"
    assert body["currency"]["date"] == "1950-08-30"
    assert body["currency"]["amended"] == {"status": "no_record", "latest": None, "evidence": []}
    assert body["alternatives"] == []
    assert body["provenance"]["text"] == "gpo-uslm"
    assert body["provenance"]["identifiers"] == "rules-1.0"
    assert body["provenance"]["sha256"] == response.headers["etag"].strip('"')
    assert body["pages"] == [
        {"page": "/us/stat/64/563", "pdf": "https://www.govinfo.gov/link/statute/64/563"},
        {"page": "/us/stat/64/564", "pdf": "https://www.govinfo.gov/link/statute/64/564"},
    ]
    assert body["text"].startswith("Sec. 3. The objects and purposes")
    assert body["xml_url"] == "/api/v1/us/pl/81/740/s3?format=xml"
    assert body["children"] == [] and body["ancestors"] == []
    assert body["provision"] is None and body["occurrences"] == 1


def test_the_note_for_an_exact_answer(client):
    assert client.get(SECTION).json()["note"] == ENACTED_NOTE_740


def test_the_note_for_a_provision_that_is_not_in_the_text(client):
    body = client.get("/api/v1/us/pl/81/740/s3/9").json()
    assert body["resolution"] == "prefix"
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["provision"] == {"identifier": "/us/pl/81/740/s3/9", "found": False, "xml": None, "text": None}
    assert body["note"] == (
        "Nothing is stored at /us/pl/81/740/s3/9; /us/pl/81/740/s3 is the longest stored prefix "
        "and is served here. /us/pl/81/740/s3/9 is not in its text. " + ENACTED_NOTE_740
    )


def test_the_note_for_a_section_found_by_number(client):
    body = client.get("/api/v1/us/pl/81/910/s101").json()
    assert body["resolution"] == "section_number"
    assert body["served_identifier"] == "/us/pl/81/910/tI/s101"
    assert body["ancestors"][0]["identifier"] == "/us/pl/81/910/tI"
    assert body["note"] == (
        "No unit is stored at /us/pl/81/910/s101; the section numbered 101 in this law is at "
        "/us/pl/81/910/tI/s101 and is served here. This is section 101 of Public Law 81-910 as "
        "enacted on January 6, 1951 (64 Stat. 1221). It is not updated. Whether this section has "
        "been amended since is not recorded here. To check for later amendments: the "
        "classification tables at uscode.house.gov for laws after January 6, 1951."
    )


def test_the_chapter_form_is_an_alias(client):
    response = client.get("/api/v1/us/act/1950-08-30/ch823/s3")
    body = response.json()
    assert body["identifier"] == "/us/act/1950-08-30/ch823/s3"
    assert body["served_identifier"] == "/us/pl/81/740/s3"
    assert body["resolution"] == "alias"
    assert response.headers["x-served-identifier"] == "/us/pl/81/740/s3"
    assert body["provenance"]["sha256"] == client.get(SECTION).json()["provenance"]["sha256"]
    assert body["note"] == (
        "/us/act/1950-08-30/ch823/s3 is served as /us/pl/81/740/s3, the same law under its other "
        "identifier. " + ENACTED_NOTE_740
    )
    assert body["xml_url"] == "/api/v1/us/act/1950-08-30/ch823/s3?format=xml"


def test_a_provision_is_cut_from_its_section(client):
    body = client.get("/api/v1/us/pl/81/740/s3/1").json()
    assert body["resolution"] == "exact" and body["served_identifier"] == "/us/pl/81/740/s3"
    provision = body["provision"]
    assert provision["identifier"] == "/us/pl/81/740/s3/1" and provision["found"] is True
    assert provision["xml"].startswith("<paragraph")
    assert provision["text"].startswith("(1) to create, foster, and assist")
    assert body["text"].startswith("Sec. 3.")
    assert body["note"] == ENACTED_NOTE_740


# ---------------------------------------------------------------- the XML


def test_format_xml_returns_the_stamped_section(client):
    response = client.get(f"{SECTION}?format=xml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert response.text.startswith("<section")
    assert 'identifier="/us/pl/81/740/s3"' in response.text
    assert response.headers["vary"] == "Accept"


def test_a_provision_path_returns_the_paragraph_in_xml(client):
    response = client.get("/api/v1/us/pl/81/740/s3/1?format=xml")
    assert response.text.startswith("<paragraph")
    assert 'identifier="/us/pl/81/740/s3/1"' in response.text
    assert "<section" not in response.text


def test_accept_xml_also_gives_xml(client):
    response = client.get(SECTION, headers={"Accept": "application/xml"})
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert response.text.startswith("<section")
    browser = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    assert client.get(SECTION, headers={"Accept": browser}).headers["content-type"].startswith("application/xml")
    assert client.get(SECTION, headers={"Accept": "text/html"}).headers["content-type"] == "application/json"


def test_the_law_xml_is_the_whole_plaw_element(client):
    response = client.get("/api/v1/us/pl/81/740?format=xml")
    assert response.text.startswith("<pLaw")


# ---------------------------------------------------------------- caching


def test_etag_and_if_none_match(client):
    first = client.get(SECTION)
    etag = first.headers["etag"]
    assert etag.startswith('"') and etag.endswith('"')
    again = client.get(SECTION, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag
    assert again.headers["cache-control"] == first.headers["cache-control"]
    assert again.headers["x-served-identifier"] == "/us/pl/81/740/s3"
    assert client.get(SECTION, headers={"If-None-Match": '"stale"'}).status_code == 200
    assert client.get(SECTION, headers={"If-None-Match": f'W/{etag}, "other"'}).status_code == 304


def test_two_provisions_of_one_section_have_different_etags(client):
    section = client.get(SECTION).headers["etag"]
    first = client.get("/api/v1/us/pl/81/740/s3/1").headers["etag"]
    second = client.get("/api/v1/us/pl/81/740/s3/2").headers["etag"]
    assert len({section, first, second}) == 3
    assert first.startswith(section.rstrip('"'))


def test_an_enacted_unit_is_immutable(client):
    response = client.get(SECTION)
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["vary"] == "Accept"
    assert response.headers["x-served-identifier"] == "/us/pl/81/740/s3"
    assert client.get(f"{SECTION}?format=xml").headers["cache-control"] == "public, max-age=31536000, immutable"


# ---------------------------------------------------- laws and hierarchy


def test_the_law_itself_with_its_table_of_contents(client):
    body = client.get("/api/v1/us/pl/81/910").json()
    assert body["level"] == "law" and body["resolution"] == "exact"
    assert body["heading"] == body["law"]["official_title"]
    assert [c["identifier"] for c in body["children"]][:2] == ["/us/pl/81/910/tI", "/us/pl/81/910/tI–A"]
    assert body["children"][0]["level"] == "title" and body["children"][0]["is_section"] is False
    assert body["law"]["enacted"] == "1951-01-06"
    assert body["pages"][0]["page"] == "/us/stat/64/1221"
    assert body["text"] == ""


def test_a_private_law(client):
    body = client.get("/api/v1/us/pvtl/81/375").json()
    assert body["law"]["kind"] == "pvtl" and body["law"]["label"] == "Private Law 81-375"
    assert body["pages"][0] == {"page": "/us/stat/64/a12", "pdf": "https://www.govinfo.gov/link/statute/64/a12"}


def test_a_hierarchy_node(client):
    response = client.get("/api/v1/us/pl/111/344/tI")
    body = response.json()
    assert body["level"] == "title" and body["num"] == "I"
    assert body["heading"].startswith("EXTENSION OF TRADE")
    assert body["children"] and all(c["identifier"].startswith("/us/pl/111/344/tI/") for c in body["children"])
    assert body["children"][0]["level"] == "subtitle" and body["children"][0]["is_section"] is False
    assert body["note"].startswith("This is title I of Public Law 111-344 as enacted on December 29, 2010")
    assert body["text"] == ""
    assert client.get("/api/v1/us/pl/111/344/tI?format=xml").text.startswith("<title")


def test_a_division(client):
    body = client.get("/api/v1/us/pl/118/22/dA").json()
    assert body["level"] == "division" and body["served_identifier"] == "/us/pl/118/22/dA"


def test_a_law_without_chapters(client):
    body = client.get("/api/v1/us/pl/85/910").json()
    assert body["law"]["chapter"] is None and body["law"]["aliases"] == ["/us/pl/85/910"]


# ------------------------------------------------------------------- 404s


def test_a_missing_law_is_a_404_that_names_the_search(client):
    response = client.get("/api/v1/us/pl/81/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "nothing at /us/pl/81/999999 in the loaded Statutes at Large volumes"}
    assert client.get("/api/v1/us/act/1900-01-01/ch1/s1").status_code == 404
    assert client.get("/api/v1/us/act/not-a-date/ch1").status_code == 422


def test_the_compiled_view_is_a_404_with_alternatives(client):
    response = client.get(f"{SECTION}?view=compiled")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "nothing at /us/pl/81/740/s3 in the loaded Statute Compilations",
        "alternatives": [],
    }
    assert response.headers["cache-control"] == "public, max-age=300"
    assert client.get(f"{SECTION}?view=compiled&through=118-67").status_code == 404


def test_through_is_accepted_on_the_enacted_view(client):
    assert client.get(f"{SECTION}?view=enacted&through=118-67").status_code == 200


# ------------------------------------------------------------- stat pages


def test_a_stat_page(client):
    response = client.get("/api/v1/us/stat/64/564")
    assert response.status_code == 200
    body = response.json()
    document = body["documents"][0]
    assert document.pop("text").startswith("(3) to create and nurture a love of country life")
    assert document.pop("units") == [
        {"identifier": "/us/pl/81/740/s3", "level": "section", "num": "3", "heading": None, "is_section": True},
        {"identifier": "/us/pl/81/740/s4", "level": "section", "num": "4", "heading": None, "is_section": True},
    ]
    assert body == {
        "page": "564",
        "identifier": "/us/stat/64/564",
        "volume": 64,
        "documents": [
            {
                "identifier": "/us/pl/81/740",
                "kind": "pl",
                "title": "To incorporate the Future Farmers of America, and for other purposes.",
                "label": "Public Law 81-740",
                "citation": "64 Stat. 563",
                "enacted": "1950-08-30",
                "starts_here": False,
                "unit_on_page": "/us/pl/81/740/s3",
            }
        ],
        "pdf": "https://www.govinfo.gov/link/statute/64/564",
    }
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    etag = response.headers["etag"]
    assert client.get("/api/v1/us/stat/64/564", headers={"If-None-Match": etag}).status_code == 304


def test_the_first_page_of_a_law_starts_at_its_preface(client):
    document = client.get("/api/v1/us/stat/64/563").json()["documents"][0]
    assert document["starts_here"] is True and document["unit_on_page"] is None
    assert document["text"].startswith("[CHAPTER 823] AN ACT To incorporate the Future Farmers of America")
    assert [u["identifier"] for u in document["units"]] == [
        "/us/pl/81/740/s1",
        "/us/pl/81/740/s2",
        "/us/pl/81/740/s3",
    ]


def test_a_stat_page_as_xml(client):
    """One `slice` per law on the page, each holding the law\'s USLM between the
    page\'s marker and the next one."""
    response = client.get("/api/v1/us/stat/64/3?format=xml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    root = ElementTree.fromstring(response.text)
    assert root.tag == "statPage"
    assert root.attrib == {"identifier": "/us/stat/64/3", "volume": "64", "page": "3"}
    slices = root.findall("slice")
    assert [s.get("law") for s in slices] == ["/us/pl/81/441", "/us/pl/81/442"]
    assert all(s.get("from") == "/us/stat/64/3" for s in slices)
    assert slices[0].find(f"{{{USLM_NS}}}pLaw") is not None


def test_the_xml_of_a_mid_law_page_names_the_page_it_runs_to(client):
    root = ElementTree.fromstring(client.get("/api/v1/us/stat/64/564?format=xml").text)
    cut = root.find("slice")
    assert cut.get("from") == "/us/stat/64/564" and cut.get("to") == "/us/stat/64/565"
    assert "Future Farmers of America, and for other purposes" not in ElementTree.tostring(cut, encoding="unicode")


def test_a_stat_page_is_negotiated_on_accept(client):
    response = client.get("/api/v1/us/stat/64/564", headers={"Accept": "application/xml"})
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert response.headers["vary"] == "Accept"


def test_a_page_where_two_laws_start(client):
    body = client.get("/api/v1/us/stat/64/3").json()
    assert [(d["identifier"], d["starts_here"], d["unit_on_page"]) for d in body["documents"]] == [
        ("/us/pl/81/441", True, None),
        ("/us/pl/81/442", True, None),
    ]


def test_page_labels_are_matched_lower_case(client):
    body = client.get("/api/v1/us/stat/64/A12").json()
    assert body["page"] == "a12" and body["identifier"] == "/us/stat/64/a12"
    assert body["documents"][0]["identifier"] == "/us/pvtl/81/375"


def test_a_missing_page(client):
    response = client.get("/api/v1/us/stat/64/99999")
    assert response.status_code == 404
    assert response.json() == {"detail": "nothing at /us/stat/64/99999 in the loaded Statutes at Large volumes"}


# ----------------------------------------------------------------- labels


def test_labels_post(client):
    response = client.post(
        "/api/v1/labels",
        json={"identifiers": ["/us/pl/81/740/s3", "/us/act/1950-08-30/ch823", "/us/pl/81/1", "us/pl/118/34/s1"]},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    body = response.json()
    assert set(body) == {"/us/pl/81/740/s3", "/us/act/1950-08-30/ch823", "/us/pl/81/1", "/us/pl/118/34/s1"}
    assert body["/us/pl/81/740/s3"] == {
        "exists": True,
        "served_identifier": "/us/pl/81/740/s3",
        "resolution": "exact",
        "num": "3",
        "heading": None,
        "level": "section",
        "kind": "pl",
        "law_identifier": "/us/pl/81/740",
        "law_label": "Public Law 81-740",
        "currency": {
            "kind": "as_enacted",
            "date": "1950-08-30",
            "amended": {"status": "no_record", "latest": None, "evidence": []},
        },
    }
    assert body["/us/act/1950-08-30/ch823"]["resolution"] == "alias"
    assert body["/us/act/1950-08-30/ch823"]["served_identifier"] == "/us/pl/81/740"
    assert body["/us/act/1950-08-30/ch823"]["level"] == "law"
    assert body["/us/pl/118/34/s1"]["heading"] == "SHORT TITLE; TABLE OF CONTENTS."
    assert body["/us/pl/81/1"] == {"exists": False}


def test_labels_get(client):
    response = client.get("/api/v1/labels?identifier=/us/pl/81/740/s3&identifier=/us/pl/81/1")
    assert response.status_code == 200
    body = response.json()
    assert body["/us/pl/81/740/s3"]["exists"] is True and body["/us/pl/81/740/s3"]["num"] == "3"
    assert body["/us/pl/81/1"] == {"exists": False}
    assert client.get("/api/v1/labels").status_code == 422


def test_labels_are_bounded_at_100(client):
    hundred = [f"/us/pl/81/{n}" for n in range(1, 101)]
    assert client.post("/api/v1/labels", json={"identifiers": hundred}).status_code == 200
    assert client.post("/api/v1/labels", json={"identifiers": hundred + ["/us/pl/81/101"]}).status_code == 422
    assert client.post("/api/v1/labels", json={"identifiers": []}).status_code == 422
    query = "&".join(f"identifier=/us/pl/81/{n}" for n in range(1, 102))
    assert client.get(f"/api/v1/labels?{query}").status_code == 422


def test_labels_are_rate_limited_after_the_burst(client):
    limiter = LIMITERS["labels"]
    assert limiter.capacity == 300 and limiter.per_second == 30.0
    # Drain the test client's bucket directly; the autouse fixture refills it.
    while limiter.check("testclient") is None:
        pass
    response = client.post("/api/v1/labels", json={"identifiers": ["/us/pl/81/740/s3"]})
    assert response.status_code == 429
    assert response.headers["retry-after"]
    assert response.json() == {"detail": "too many requests; try again shortly"}


def test_the_rate_limit_is_reset_between_tests(client):
    assert client.post("/api/v1/labels", json={"identifiers": ["/us/pl/81/740/s3"]}).status_code == 200


# ----------------------------------------------------------------- status


def test_status(client):
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    body = response.json()
    assert set(body) == {"collections", "checks", "stale", "citations", "classifications"}
    assert set(body["collections"]) == {"STATUTE", "COMPS", "PLAW"} == set(body["checks"])
    statute = body["collections"]["STATUTE"]
    assert statute["volumes"] == [26, 64, 68, 72, 116, 124, 137]
    assert statute["packages_loaded"] == 7 and statute["latest_package"] == "STATUTE-137"
    # 28 laws in the volume slices; 118-22 and 118-34 are served from PLAW.
    assert statute["laws"] == 26 and statute["units"] > 0 and statute["latest_loaded_at"]
    comps = body["collections"]["COMPS"]
    assert comps["packages_loaded"] == 4 and comps["latest_package"] == "COMPS-1630"
    assert comps["units"] > 0 and comps["volumes"] == []
    assert statute["congresses"] == [] and statute["laws_by_congress"] == {}
    assert comps["congresses"] == [] and comps["laws_by_congress"] == {}
    check = body["checks"]["STATUTE"]
    assert check["ok"] is True and check["stale"] is False and check["newest_package"] == "STATUTE-137"
    assert set(check) == {
        "checked_at", "ok", "newest_package", "newest_last_modified", "packages_seen", "new_packages", "error", "stale",
    }
    assert datetime.datetime.fromisoformat(check["checked_at"])
    # The COMPS fixtures are loaded from files, which records no poll.
    assert body["checks"]["COMPS"] is None or body["checks"]["COMPS"]["ok"] is True
    plaw = body["collections"]["PLAW"]
    assert plaw["packages_loaded"] == 4 and plaw["laws"] == 4 and plaw["latest_package"] == "PLAW-119publ1"
    assert plaw["volumes"] == [137, 139] and plaw["congresses"] == [118, 119]
    assert plaw["laws_by_congress"] == {"118": 3, "119": 1}
    assert body["checks"]["PLAW"]["ok"] is True and body["checks"]["PLAW"]["newest_package"] == "PLAW-119publ1"
    assert body["checks"]["PLAW"]["stale"] is False
    # COMPS packages are loaded and never polled in the fixture database, so the
    # mirror as a whole reports stale: a collection with packages and no check.
    assert body["stale"] is True


# ------------------------------------------------------------------- laws


def test_law_summary(client):
    response = client.get("/api/v1/laws/81/910")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"law", "toc", "section_count", "compilations", "sources"}
    assert body["sources"]["served_from"] == "STATUTE" and body["sources"]["plaw"]["package"] is None
    assert body["law"]["label"] == "Public Law 81-910"
    assert body["section_count"] == 11
    assert body["toc"][0] == {
        "identifier": "/us/pl/81/910/tI", "level": "title", "num": "I",
        "heading": body["toc"][0]["heading"], "is_section": False,
    }
    assert sum(1 for u in body["toc"] if u["is_section"]) == 11
    assert body["compilations"] == []
    assert client.get("/api/v1/laws/81/999999").status_code == 404


def test_law_section_by_number(client):
    response = client.get("/api/v1/laws/81/910/sections/101")
    assert response.status_code == 200
    body = response.json()
    assert body["served_identifier"] == "/us/pl/81/910/tI/s101"
    assert body["resolution"] == "section_number"
    assert body["identifier"] == "/us/pl/81/910/s101"
    assert response.headers["x-served-identifier"] == "/us/pl/81/910/tI/s101"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/api/v1/laws/81/910/sections/101?format=xml").text.startswith("<section")
    missing = client.get("/api/v1/laws/81/910/sections/999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "nothing at /us/pl/81/910/s999 in the loaded Statutes at Large volumes"}


# ------------------------------------------------------------------- HEAD


def test_head_is_not_served(client):
    """The routes are registered for GET only; Starlette answers HEAD with 405."""
    response = client.head(SECTION)
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


def test_labels_answer_a_stat_page(client):
    response = client.post(
        "/api/v1/labels", json={"identifiers": ["/us/stat/64/563", "/us/stat/64/A12", "/us/stat/110/4196"]}
    )
    assert response.status_code == 200
    body = response.json()
    page = body["/us/stat/64/563"]
    assert page["exists"] is True
    assert page["level"] == "page" and page["kind"] == "stat"
    assert page["served_identifier"] == "/us/stat/64/563"
    assert page["num"] == "563" and page["volume"] == 64 and page["page"] == "563"
    assert page["pdf"] == "https://www.govinfo.gov/link/statute/64/563"
    assert {"identifier": "/us/pl/81/740", "label": "Public Law 81-740", "kind": "pl", "starts_here": True} in page["documents"]
    assert body["/us/stat/64/A12"]["exists"] is True
    assert body["/us/stat/64/A12"]["served_identifier"] == "/us/stat/64/a12"
    assert body["/us/stat/110/4196"] == {"exists": False}
