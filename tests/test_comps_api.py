"""The compiled view over the loaded slices: shape, note, resolution rules,
formats, caching, 404s, the listings."""

import datetime

import pytest

from api.comps import compiled_alternatives, origins

SECTION = "/api/v1/us/sComp/83/703/tI/ch1./s1"


def test_a_compiled_section(client):
    response = client.get(SECTION)
    assert response.status_code == 200
    body = response.json()
    assert body["identifier"] == "/us/sComp/83/703/tI/ch1./s1"
    assert body["served_identifier"] == "/us/sComp/83/703/tI/ch1./s1"
    assert body["view"] == "compiled" and body["resolution"] == "exact"
    assert body["level"] == "section" and body["num"] == "1" and body["heading"] == "Declaration.—"
    assert body["section_num"] == "1"
    assert body["compilation"] == {
        "file_id": "1630",
        "package_id": "COMPS-1630",
        "display_title": "Atomic Energy Act of 1954",
        "short_titles": ["Atomic Energy Act of 1954"],
        "identifier_prefix": "/us/sComp/83/703",
        "law_identifier": None,
        "partial_of": None,
        "govinfo_details": "https://www.govinfo.gov/app/details/COMPS-1630",
    }
    assert body["law"] == {"congress": 83, "number": 703, "identifier": "/us/pl/83/703", "loaded": False}
    currency = body["currency"]
    assert currency["kind"] == "compiled"
    assert currency["current_through"] == {"pl": "118-67", "enacted": "2024-07-09"}
    assert currency["fetched"] == datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert currency["govinfo_last_modified"] == "2026-09-04T12:08:06Z"
    assert len(body["versions"]) == 1
    version = body["versions"][0]
    assert version["current_through"] == {"pl": "118-67", "enacted": "2024-07-09"}
    assert version["is_current"] is True
    assert version["url"] == f"{origins.site_origin}/us/sComp/83/703/tI/ch1./s1?through=118-67"
    assert body["alternatives"] == [
        {"view": "codified", "identifiers": ["/us/usc/t42/s2011"], "url": f"{origins.uscode_origin}/us/usc/t42/s2011"}
    ]
    assert body["usc_refs"] == ["/us/usc/t42/s2011"]
    assert body["provenance"] == {"text": "gpo-uslm", "identifiers": "gpo-uslm", "sha256": body["provenance"]["sha256"]}
    assert len(body["provenance"]["sha256"]) == 64
    assert body["text"].startswith("Section 1. Declaration.— Atomic energy is capable")
    assert body["xml_url"] == "/api/v1/us/sComp/83/703/tI/ch1./s1?format=xml"
    assert [a["identifier"] for a in body["ancestors"]] == ["/us/sComp/83/703/tI", "/us/sComp/83/703/tI/ch1."]
    assert body["ancestors"][1]["num"] == "1." and body["ancestors"][1]["level"] == "chapter"
    assert body["children"] == [] and body["provision"] is None


def test_the_compiled_note_wording(client):
    note = client.get(SECTION).json()["note"]
    assert note == (
        "This is section 1 of Atomic Energy Act of 1954 as compiled by the House Office of the "
        "Legislative Counsel, incorporating amendments through Public Law 118-67 (July 9, 2024). "
        "Compilations are not an official version; the official text is in the Statutes at Large "
        "and the United States Code (1 U.S.C. 112, 204). Laws enacted after July 9, 2024 are not "
        "reflected; check the classification tables for Atomic Energy Act of 1954 and the US Code "
        f"section(s) {origins.uscode_origin}/us/usc/t42/s2011."
    )


def test_headers_unpinned(client):
    response = client.get(SECTION)
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert response.headers["Vary"] == "Accept"
    etag = response.headers["ETag"]
    assert etag.startswith('"') and etag.endswith('"')
    assert etag.strip('"') == response.json()["provenance"]["sha256"]
    again = client.get(SECTION, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.headers["ETag"] == etag
    weak = client.get(SECTION, headers={"If-None-Match": f"W/{etag}"})
    assert weak.status_code == 304


def test_pinned_with_through_is_immutable(client):
    response = client.get(SECTION + "?through=118-67")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert response.json()["xml_url"] == "/api/v1/us/sComp/83/703/tI/ch1./s1?format=xml&through=118-67"
    dash = client.get(SECTION + "?through=118–67")
    assert dash.status_code == 200 and dash.headers["Cache-Control"].endswith("immutable")


def test_an_unknown_through_is_a_404_that_says_so(client):
    response = client.get(SECTION + "?through=200-1")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail.startswith("nothing at /us/sComp/83/703/tI/ch1./s1 in the loaded Statute Compilations")
    assert "no stored version of /us/sComp/83/703 is current through 200-1" in detail


def test_nothing_compiled_is_a_404(client):
    response = client.get("/api/v1/us/sComp/99/1/s1")
    assert response.status_code == 404
    assert response.json()["detail"] == "nothing at /us/sComp/99/1/s1 in the loaded Statute Compilations"


def test_rule_3_the_section_number_under_the_compilation(client):
    response = client.get("/api/v1/us/sComp/83/703/s1")
    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "section_number"
    assert body["identifier"] == "/us/sComp/83/703/s1"
    assert body["served_identifier"] == "/us/sComp/83/703/tI/ch1./s1"
    assert body["note"].startswith(
        "No unit is stored at /us/sComp/83/703/s1; the section numbered 1 in this law is at "
        "/us/sComp/83/703/tI/ch1./s1 and is served here. This is section 1 of Atomic Energy Act of 1954"
    )
    assert response.headers["Cache-Control"] == "public, max-age=300"
    # Pinned but not exact: revalidates.
    pinned = client.get("/api/v1/us/sComp/83/703/s1?through=118-67")
    assert pinned.headers["Cache-Control"] == "public, max-age=300"


def test_a_provision_is_cut_from_its_section(client):
    response = client.get(SECTION + "/a")
    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "exact" and body["served_identifier"] == "/us/sComp/83/703/tI/ch1./s1"
    assert body["provision"]["identifier"] == "/us/sComp/83/703/tI/ch1./s1/a"
    assert body["provision"]["found"] is True
    assert body["provision"]["text"].startswith("a. the development, use, and control of atomic energy")
    assert body["provision"]["xml"].startswith("<subsection")
    assert response.headers["ETag"].endswith(':/us/sComp/83/703/tI/ch1./s1/a"')
    missing = client.get(SECTION + "/zz")
    assert missing.status_code == 200
    assert missing.json()["resolution"] == "prefix" and missing.json()["provision"]["found"] is False
    assert "/us/sComp/83/703/tI/ch1./s1/zz is not in its text" in missing.json()["note"]


def test_format_xml(client):
    response = client.get(SECTION + "?format=xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.text.startswith("<section")
    assert 'identifier="/us/sComp/83/703/tI/ch1./s1"' in response.text
    assert response.headers["ETag"].endswith(';xml"')
    provision = client.get(SECTION + "/b?format=xml")
    assert provision.text.startswith("<subsection") and 'identifier="/us/sComp/83/703/tI/ch1./s1/b"' in provision.text
    accept = client.get(SECTION, headers={"Accept": "application/xml"})
    assert accept.headers["content-type"].startswith("application/xml")


def test_a_hierarchy_node_and_the_compilation_itself(client):
    chapter = client.get("/api/v1/us/sComp/83/703/tI/ch1.").json()
    assert chapter["level"] == "chapter" and chapter["num"] == "1."
    assert [c["identifier"] for c in chapter["children"]][:1] == ["/us/sComp/83/703/tI/ch1./s1"]
    assert chapter["children"][0]["is_section"] is True
    assert chapter["heading"] == "DECLARATION, FINDINGS, AND PURPOSE"
    assert chapter["usc_refs"] == [] and chapter["alternatives"] == []
    assert chapter["note"].startswith("This is chapter 1. of Atomic Energy Act of 1954 as compiled")
    root = client.get("/api/v1/us/sComp/83/703").json()
    assert root["level"] == "compilation" and root["served_identifier"] == "/us/sComp/83/703"
    assert [c["identifier"] for c in root["children"]] == ["/us/sComp/83/703/tI"]
    assert root["note"].startswith("This is the compilation of Atomic Energy Act of 1954 as compiled")
    whole = client.get("/api/v1/us/sComp/83/703?format=xml")
    assert whole.text.lstrip().startswith("<?xml") and "<statuteCompilation" in whole.text


def test_the_per_title_file(client):
    response = client.get("/api/v1/us/sComp/74/271/tII/s201")
    assert response.status_code == 200
    body = response.json()
    assert body["compilation"]["file_id"] == "8755" and body["compilation"]["partial_of"] == "II"
    assert body["law"] == {"congress": 74, "number": 271, "identifier": "/us/pl/74/271", "loaded": False}
    assert body["currency"]["current_through"] == {"pl": "119-77", "enacted": "2026-02-10"}
    assert body["alternatives"][0]["identifiers"] == ["/us/usc/t42/s401"]
    assert [a["identifier"] for a in body["ancestors"]] == ["/us/sComp/74/271/tII"]
    assert body["note"].startswith("This is section 201 of Social Security Act-TITLE II")


def test_an_act_before_public_law_numbering(client):
    response = client.get("/api/v1/us/sComp/51/647/s1")
    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "exact" and body["compilation"]["file_id"] == "3055"
    assert body["law"] == {"congress": 51, "number": 647, "identifier": None, "loaded": False}
    assert body["currency"]["current_through"] == {"pl": "108-237", "enacted": "2004-06-22"}
    assert body["alternatives"] == [{"view": "codified", "identifiers": ["/us/usc/t15/s1"], "url": f"{origins.uscode_origin}/us/usc/t15/s1"}]
    assert body["note"].startswith("This is section 1 of Sherman Act as compiled")
    assert body["text"].startswith("Section 1. Every contract, combination")


def test_list_comps_by_title(client):
    response = client.get("/api/v1/comps?q=atomic")
    assert response.status_code == 200
    comps = response.json()["comps"]
    assert [c["file_id"] for c in comps] == ["1630"]
    comp = comps[0]
    assert comp["package_id"] == "COMPS-1630" and comp["identifier_prefix"] == "/us/sComp/83/703"
    assert comp["display_title"] == "Atomic Energy Act of 1954"
    assert comp["title"].startswith("To amend the Atomic Energy Act of 1946")
    assert comp["short_titles"] == ["Atomic Energy Act of 1954"]
    assert comp["law_identifier"] is None and comp["partial_of"] is None
    assert comp["current_through"] == {"pl": "118-67", "enacted": "2024-07-09"}
    assert comp["govinfo_last_modified"] == "2026-09-04T12:08:06Z"
    assert comp["url"] == f"{origins.site_origin}/us/sComp/83/703"
    assert comp["govinfo_details"] == "https://www.govinfo.gov/app/details/COMPS-1630"
    everything = client.get("/api/v1/comps").json()["comps"]
    assert sorted(c["file_id"] for c in everything) == ["1630", "3055", "8755", "973"]
    assert client.get("/api/v1/comps?q=medicare").json()["comps"][0]["file_id"] == "8755"
    assert client.get("/api/v1/comps?q=nothing-like-this").json() == {"comps": []}
    assert client.get("/api/v1/comps?limit=0").status_code == 422
    assert client.get("/api/v1/comps?q=").status_code == 422
    assert len(client.get("/api/v1/comps?limit=2").json()["comps"]) == 2


def test_list_comps_by_law(client):
    # `list_comps(law_identifier=…)` goes through the loaded laws; Public Law
    # 83-703 is not in the slices, so the answer is empty rather than a match
    # on the prefix.
    response = client.get("/api/v1/comps?law=/us/pl/83/703")
    assert response.status_code == 200
    assert response.json() == {"comps": []}
    # A loaded law without a compilation is empty too.
    assert client.get("/api/v1/comps?law=/us/pl/81/740").json() == {"comps": []}


def test_get_comp_with_versions_and_toc(client):
    response = client.get("/api/v1/comps/1630")
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == "1630" and body["package_id"] == "COMPS-1630"
    assert body["current_through"] == {"pl": "118-67", "enacted": "2024-07-09"}
    assert len(body["versions"]) == 1
    assert body["versions"][0]["is_current"] is True
    assert body["versions"][0]["url"] == f"{origins.site_origin}/us/sComp/83/703?through=118-67"
    assert body["versions"][0]["fetched"] == datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert body["toc"] == [{"identifier": "/us/sComp/83/703/tI", "level": "title", "num": "I", "heading": "ATOMIC ENERGY", "is_section": False}]
    by_package = client.get("/api/v1/comps/COMPS-1630").json()
    assert by_package["file_id"] == "1630"
    sherman = client.get("/api/v1/comps/3055").json()
    assert [u["identifier"] for u in sherman["toc"]] == [f"/us/sComp/51/647/s{n}" for n in range(1, 9)]
    assert all(u["is_section"] for u in sherman["toc"])
    ssa = client.get("/api/v1/comps/8755").json()
    assert ssa["partial_of"] == "II"
    assert [u["identifier"] for u in ssa["toc"]] == ["/us/sComp/74/271/tII"]


def test_an_unknown_comp_is_a_404(client):
    response = client.get("/api/v1/comps/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "nothing at /api/v1/comps/999999 in the loaded Statute Compilations"


class _Repo:
    """Just enough repository for `compiled_alternatives`."""

    def __init__(self, enacted):
        self._enacted = enacted
        self.asked = None

    def enacted_counterpart(self, prefix, section_num):
        self.asked = (prefix, section_num)
        return self._enacted


def test_compiled_alternatives_with_and_without_an_enacted_counterpart(repo):
    result = repo.get_comp_unit("/us/sComp/83/703/tI/ch1./s1")
    assert compiled_alternatives(repo, result) == [
        {"view": "codified", "identifiers": ["/us/usc/t42/s2011"], "url": f"{origins.uscode_origin}/us/usc/t42/s2011"}
    ]
    enacted = repo.get_unit("/us/pl/81/740/s3")
    fake = _Repo(enacted)
    alternatives = compiled_alternatives(fake, result)
    assert fake.asked == ("/us/sComp/83/703", "1")
    assert alternatives[0] == {"view": "enacted", "identifier": "/us/pl/81/740/s3", "url": f"{origins.site_origin}/us/pl/81/740/s3"}
    assert alternatives[1]["view"] == "codified"
    root = repo.get_comp_unit("/us/sComp/83/703")
    assert compiled_alternatives(_Repo(None), root) == []


@pytest.mark.parametrize("path", ["/us/sComp/83/703/tI/ch1./s1", "/us/sComp/51/647/s1"])
def test_the_citation_url_redirects_to_the_compiled_view(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == f"/api/v1{path}"
    followed = client.get(path)
    assert followed.status_code == 200 and followed.json()["view"] == "compiled"
