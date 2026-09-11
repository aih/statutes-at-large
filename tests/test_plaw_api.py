"""The API over PLAW-derived laws (stage 4, part b): `law.source` and
`provenance` say `PLAW`, the enacted note keeps its wording, `alternatives`
and `view=compiled` work on a PLAW-derived section, `labels` answers, the law
summary carries `sources`, and `/status`'s `PLAW` block carries the
congresses and the per-congress counts."""

from __future__ import annotations

import datetime
import hashlib

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from db.base import Base, make_engine
from db.models import Comp, CompUnit, CompVersion, Law
from tests.conftest import CITATIONS_SLICE, CLASSIFICATIONS_FIXTURES, FIXTURES, PLAW_FILES

SITE = "https://statutes.linkedlegislation.org"
USC = "https://uscode.linkedlegislation.org"
S102 = "/us/pl/118/22/dB/tI/s102"
ENACTED_NOTE = (
    "This is section 102 of Public Law 118-22 as enacted on November 17, 2023 (137 Stat. 112). "
    "It is not updated."
)


# --------------------------------------------------------- the session db


def test_a_plaw_unit_says_where_it_came_from(client):
    body = client.get(f"/api/v1{S102}").json()
    assert body["served_identifier"] == S102 and body["resolution"] == "exact"
    assert body["law"]["source"] == {"collection": "PLAW", "package": "PLAW-118publ22", "granule": None}
    assert body["provenance"]["text"] == "gpo-uslm" and body["provenance"]["identifiers"] == "gpo-uslm"
    assert body["note"].startswith(ENACTED_NOTE)
    assert "This section has been amended since; the most recent law recorded is Public Law 119-37" in body["note"]
    assert "; the classification tables at uscode.house.gov for laws after November 17, 2023. " in body["note"]
    assert body["note"].endswith(
        "The text is from GovInfo package PLAW-118publ22, converted to USLM by GPO from its "
        "typesetting (locator) files; the identifiers are GPO's."
    )
    assert "the compiled text at" not in body["note"]
    # The index's source credits cite the section; no compilation of the law is loaded.
    assert [a["view"] for a in body["alternatives"]] == ["codified"]
    assert "/us/usc/t7/s940c\u20132" in body["alternatives"][0]["identifiers"]
    amended = body["currency"]["amended"]
    assert amended["status"] == "known_amended" and amended["evidence"] == ["source_credit"]
    assert amended["latest"]["pl"] == "119-37"
    filled = client.get("/api/v1/us/pl/118/1/s1").json()
    assert filled["provenance"]["identifiers"] == "gpo-uslm+rules-1.0"
    assert filled["law"]["source"]["package"] == "PLAW-118publ1"
    volume = client.get("/api/v1/us/pl/118/3/s1").json()
    assert volume["law"]["source"]["collection"] == "STATUTE" and volume["provenance"]["identifiers"] == "rules-1.0"


def test_labels_answer_with_the_served_identifier(client):
    body = client.post("/api/v1/labels", json={"identifiers": [f"{S102}/c", "/us/pl/119/1/s3", "/us/pl/118/22/s102"]}).json()
    below = body[f"{S102}/c"]
    assert below["exists"] is True and below["served_identifier"] == S102 and below["resolution"] == "exact"
    assert below["level"] == "section" and below["num"] == "102" and below["law_label"] == "Public Law 118-22"
    assert body["/us/pl/119/1/s3"]["served_identifier"] == "/us/pl/119/1/s3"
    by_number = body["/us/pl/118/22/s102"]
    assert by_number["served_identifier"] == S102 and by_number["resolution"] == "section_number"


def test_the_law_summary_carries_its_sources(client):
    body = client.get("/api/v1/laws/118/22").json()
    assert set(body) == {"law", "toc", "section_count", "compilations", "sources"}
    assert body["sources"] == {
        "served_from": "PLAW",
        "package": "PLAW-118publ22",
        "identifiers": "gpo-uslm",
        "volume": {"package": "STATUTE-137", "loaded": True, "govinfo": "https://www.govinfo.gov/link/statute/137/112"},
        "plaw": {
            "package": "PLAW-118publ22",
            "uslm": True,
            "loaded": True,
            "govinfo": "https://www.govinfo.gov/link/plaw/118/public/22",
        },
    }
    assert body["law"]["source"]["collection"] == "PLAW"

    volume_only = client.get("/api/v1/laws/118/3").json()["sources"]
    assert volume_only["served_from"] == "STATUTE" and volume_only["package"] == "STATUTE-137"
    assert volume_only["identifiers"] == "rules-1.0" and volume_only["volume"]["loaded"] is True
    assert volume_only["plaw"] == {
        "package": "PLAW-118publ3",
        "uslm": True,
        "loaded": False,
        "govinfo": "https://www.govinfo.gov/link/plaw/118/public/3",
    }

    no_volume = client.get("/api/v1/laws/119/1").json()["sources"]
    assert no_volume["served_from"] == "PLAW" and no_volume["plaw"]["loaded"] is True
    assert no_volume["volume"] == {
        "package": "STATUTE-139",
        "loaded": False,
        "govinfo": "https://www.govinfo.gov/link/statute/139/3",
    }

    before_plaw = client.get("/api/v1/laws/81/740").json()["sources"]
    assert before_plaw["served_from"] == "STATUTE" and before_plaw["volume"]["loaded"] is True
    assert before_plaw["plaw"] == {"package": None, "uslm": False, "loaded": False, "govinfo": None}


def test_status_has_the_plaw_block(client):
    body = client.get("/api/v1/status").json()
    plaw = body["collections"]["PLAW"]
    assert plaw["congresses"] == [118, 119]
    assert plaw["laws_by_congress"] == {"118": 3, "119": 1}
    assert plaw["laws"] == 4 == plaw["packages_loaded"] and plaw["volumes"] == [137, 139]
    for other in ("STATUTE", "COMPS"):
        assert body["collections"][other]["congresses"] == [] and body["collections"][other]["laws_by_congress"] == {}
    check = body["checks"]["PLAW"]
    assert check["ok"] is True and check["stale"] is False and check["newest_package"] == "PLAW-119publ1"
    # The fixture database has COMPS packages and no successful COMPS poll; the
    # aggregate `stale` is theirs, and the PLAW check on its own is fresh.
    comps_check = body["checks"]["COMPS"]
    assert body["stale"] is True and (comps_check is None or comps_check["stale"] is True)


# ---------------------------------------- a compilation for a PLAW-derived law

SECTION_XML = (
    '<section xmlns="http://schemas.gpo.gov/xml/uslm" identifier="/us/sComp/118/22/s102">'
    '<num value="102">SEC. 102.</num><heading>EXTENSION OF AGRICULTURAL PROGRAMS.</heading>'
    "<content>Compiled text of section 102, as later amended.</content></section>"
)
DOCUMENT_XML = (
    '<statuteCompilation xmlns="http://schemas.gpo.gov/xml/uslm" identifier="/us/sComp/118/22">'
    f"<main>{SECTION_XML}</main></statuteCompilation>"
)
USC_REF = "/us/usc/t7/s9011"


@pytest.fixture(scope="module")
def with_compilation():
    """A database with the volume-137 slice, the indexes, the 118th Congress
    from PLAW, and a compilation of Public Law 118-22 inserted through the
    models: one current version holding section 102."""
    from ingest.citations import load_citations
    from ingest.classifications import DirectorySource, load_classifications
    from ingest.load import load_volume
    from ingest.plaw import load_congress

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        load_volume(session, FIXTURES / "statute-137-slice.xml")
        load_citations(session, [CITATIONS_SLICE], revision="fixture")
        load_classifications(session, DirectorySource(CLASSIFICATIONS_FIXTURES))
        files = ((p.name, p.read_text(encoding="utf-8")) for p in PLAW_FILES if "PLAW-118" in p.name)
        load_congress(session, 118, files=files)
    with factory() as session:
        law = session.scalars(select(Law).where(Law.identifier == "/us/pl/118/22")).one()
        assert law.source_collection == "PLAW"
        comp = Comp(
            file_id="test-118-22",
            package_id="COMPS-test-118-22",
            identifier_prefix="/us/sComp/118/22",
            law_congress=118,
            law_number=22,
            law_id=law.id,
            title="Further Continuing Appropriations and Other Extensions Act, 2024",
            display_title="Further Continuing Appropriations and Other Extensions Act, 2024",
            short_titles=[],
        )
        version = CompVersion(
            comp=comp,
            current_through_pl="118-158",
            current_through_date=datetime.date(2024, 12, 20),
            fetched_at=datetime.datetime(2026, 9, 8, tzinfo=datetime.timezone.utc),
            content_hash=hashlib.sha256(DOCUMENT_XML.encode()).hexdigest(),
            xml=DOCUMENT_XML,
            is_current=True,
        )
        CompUnit(
            version=version,
            identifier="/us/sComp/118/22/s102",
            parent_identifier="/us/sComp/118/22",
            level="section",
            num="102",
            heading="EXTENSION OF AGRICULTURAL PROGRAMS.",
            section_num="102",
            seq=1,
            depth=1,
            ancestors=[],
            xml=SECTION_XML,
            text="SEC. 102. EXTENSION OF AGRICULTURAL PROGRAMS. Compiled text of section 102, as later amended.",
            content_hash=hashlib.sha256(SECTION_XML.encode()).hexdigest(),
            usc_refs=[USC_REF],
        )
        session.add(comp)
        session.commit()
    return factory


@pytest.fixture(scope="module")
def comp_client(with_compilation):
    """An API client over `with_compilation`; the session client's override is
    put back afterwards."""
    from fastapi.testclient import TestClient

    from main import app
    from storage import get_repository
    from storage.postgres import PostgresRepository

    def override():
        with with_compilation() as session:
            yield PostgresRepository(session)

    previous = app.dependency_overrides.get(get_repository)
    app.dependency_overrides[get_repository] = override
    with TestClient(app) as test_client:
        yield test_client
    if previous is None:
        app.dependency_overrides.pop(get_repository, None)
    else:
        app.dependency_overrides[get_repository] = previous


def test_a_plaw_section_names_its_compiled_and_codified_texts(comp_client):
    body = comp_client.get(f"/api/v1{S102}").json()
    assert body["law"]["source"]["collection"] == "PLAW" and body["provenance"]["identifiers"] == "gpo-uslm"
    compiled, codified = body["alternatives"]
    assert compiled == {
        "view": "compiled",
        "identifier": "/us/sComp/118/22/s102",
        "identifiers": None,
        "current_through": {"pl": "118-158", "enacted": "2024-12-20"},
        "url": f"{SITE}/us/sComp/118/22/s102",
    }
    # The compilation's own uscRef first, then the sections whose source credits cite the unit.
    assert codified["view"] == "codified" and codified["url"] == f"{USC}{USC_REF}"
    assert codified["identifiers"][0] == USC_REF and "/us/usc/t7/s940c\u20132" in codified["identifiers"]
    assert body["note"].startswith(ENACTED_NOTE)
    assert "the compiled text at /us/sComp/118/22/s102" in body["note"]
    assert "the US Code section(s) classified from it at 7 U.S.C. 9011, " in body["note"]
    amended = body["currency"]["amended"]
    assert amended["status"] == "known_amended" and amended["evidence"] == ["source_credit", "compilation"]
    assert amended["latest"]["pl"] == "119-37"
    # The law itself offers the compilation; a title does not.
    law = comp_client.get("/api/v1/us/pl/118/22").json()
    assert law["alternatives"][0] == {
        "view": "compiled",
        "identifier": "/us/sComp/118/22",
        "identifiers": None,
        "current_through": {"pl": "118-158", "enacted": "2024-12-20"},
        "url": f"{SITE}/us/sComp/118/22",
    }
    assert comp_client.get("/api/v1/us/pl/118/22/dB/tI").json()["alternatives"] == []
    summary = comp_client.get("/api/v1/laws/118/22").json()
    assert [c["identifier_prefix"] for c in summary["compilations"]] == ["/us/sComp/118/22"]
    assert summary["sources"]["served_from"] == "PLAW"


def test_view_compiled_serves_the_counterpart_of_a_plaw_section(comp_client):
    response = comp_client.get(f"/api/v1{S102}?view=compiled")
    assert response.status_code == 200
    assert response.headers["X-Requested-Identifier"] == S102
    body = response.json()
    assert body["view"] == "compiled" and body["identifier"] == "/us/sComp/118/22/s102"
    assert body["alternatives"][0] == {"view": "enacted", "identifier": S102, "url": f"{SITE}{S102}"}
    xml = comp_client.get(f"/api/v1{S102}?view=compiled&format=xml")
    assert xml.headers["content-type"].startswith("application/xml")
    assert 'identifier="/us/sComp/118/22/s102"' in xml.text
    by_number = comp_client.get("/api/v1/us/pl/118/22/s102?view=compiled")
    assert by_number.status_code == 200 and by_number.json()["identifier"] == "/us/sComp/118/22/s102"
    none = comp_client.get("/api/v1/us/pl/118/22/dB/tI/s101?view=compiled")
    assert none.status_code == 404 and none.json()["alternatives"] == []
