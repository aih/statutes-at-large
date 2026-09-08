"""The two views meet: `alternatives` between them and `view=compiled` on an
enacted identifier (design section 4, ADR-0007)."""

SITE = "https://statutes.linkedlegislation.org"
USC = "https://uscode.linkedlegislation.org"


def test_an_enacted_section_names_its_compiled_and_codified_texts(client):
    body = client.get("/api/v1/us/act/1890-07-02/ch647/s2").json()
    assert body["alternatives"] == [
        {
            "view": "compiled",
            "identifier": "/us/sComp/51/647/s2",
            "identifiers": None,
            "current_through": {"pl": "108-237", "enacted": "2004-06-22"},
            "url": f"{SITE}/us/sComp/51/647/s2",
        },
        {"view": "codified", "identifier": None, "identifiers": ["/us/usc/t15/s2"], "current_through": None, "url": f"{USC}/us/usc/t15/s2"},
    ]
    assert "the compiled text at /us/sComp/51/647/s2" in body["note"]
    assert "the US Code section(s) classified from it at 15 U.S.C. 2" in body["note"]


def test_the_amending_act_of_a_restated_law(client):
    """PL 83-703 section 1 restates the Atomic Energy Act; every compiled
    section numbered 1 under the law is offered (ADR-0006)."""
    body = client.get("/api/v1/us/pl/83/703/s1").json()
    compiled = [a for a in body["alternatives"] if a["view"] == "compiled"]
    assert [a["identifier"] for a in compiled] == ["/us/sComp/83/703/tI/ch1./s1"]
    assert body["alternatives"][-1]["identifiers"] == ["/us/usc/t42/s2011"]


def test_the_law_itself_offers_the_compilation(client):
    body = client.get("/api/v1/us/act/1954-08-30/ch1073").json()
    assert body["alternatives"][0]["identifier"] == "/us/sComp/83/703"
    assert body["alternatives"][0]["view"] == "compiled"


def test_a_section_with_no_compilation_has_no_alternatives(client):
    body = client.get("/api/v1/us/pl/81/740/s3").json()
    assert body["alternatives"] == []
    assert "compiled text" not in body["note"]


def test_view_compiled_serves_the_counterpart(client):
    response = client.get("/api/v1/us/act/1890-07-02/ch647/s2?view=compiled")
    assert response.status_code == 200
    assert response.headers["X-Requested-Identifier"] == "/us/act/1890-07-02/ch647/s2"
    assert response.headers["Cache-Control"] == "public, max-age=300"
    body = response.json()
    assert body["view"] == "compiled" and body["identifier"] == "/us/sComp/51/647/s2"
    assert body["alternatives"][0] == {"view": "enacted", "identifier": "/us/act/1890-07-02/ch647/s2", "url": f"{SITE}/us/act/1890-07-02/ch647/s2"}
    pinned = client.get("/api/v1/us/act/1890-07-02/ch647/s2?view=compiled&through=108-237")
    assert pinned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    xml = client.get("/api/v1/us/pl/83/703/s1?view=compiled&format=xml")
    assert xml.headers["content-type"].startswith("application/xml")
    assert 'identifier="/us/sComp/83/703/tI/ch1./s1"' in xml.text


def test_view_compiled_carries_a_sub_path(client):
    """A provision below the enacted section maps to the same path under the
    compiled section when the compilation has it."""
    response = client.get("/api/v1/us/act/1890-07-02/ch647/s2?view=compiled")
    assert response.status_code == 200
    body = client.get("/api/v1/us/act/1890-07-02/ch647/s2/x?view=compiled").json()
    assert body["identifier"] == "/us/sComp/51/647/s2" or body["provision"] is not None


def test_view_compiled_without_a_compilation_is_a_404_with_alternatives(client):
    response = client.get("/api/v1/us/pl/81/740/s3?view=compiled")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "nothing at /us/pl/81/740/s3 in the loaded Statute Compilations"
    assert body["alternatives"] == []
    missing = client.get("/api/v1/us/pl/81/999999?view=compiled")
    assert missing.status_code == 404
