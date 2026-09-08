"""`currency.amended` from evidence (design section 4, `api/currency.py`):
the three statuses over the fixtures, `latest`, the note sentences, the
`labels` block, and the codified alternative from the citation index. The
classification rows are inserted here (the mirror is built separately)."""

from __future__ import annotations

import datetime

import pytest

from api.currency import Candidate, later, newest
from db.models import ClassificationEntry, ClassificationFile

INDEXES = "the US Code's source credits, the classification tables, and the Statute Compilations"


@pytest.fixture(scope="module")
def classification_rows(loaded, session_factory):
    """One 118th Congress table: PL 118-22 § 101 created 7 U.S.C. § 1627a and
    PL 118-42 § 3 amended it (blank action); PL 118-22 § 2 created § 1627b and
    PL 118-42 § 5 is another `new` row on it. Removed at module end."""
    now = datetime.datetime.now(datetime.timezone.utc)
    with session_factory() as session:
        table = ClassificationFile(
            congress=118, session=1, session_label="118-1", kind="pl",
            covered_laws_text="Public Laws 118-22 and 118-42", covered_ranges=["22-22", "42-42"],
            first_law=22, last_law=42, row_count=4, mirrored_at=now,
        )
        session.add(table)
        session.flush()
        rows = [
            ("101", "/us/usc/t7/s1627a", 22, "new"),
            ("3", "/us/usc/t7/s1627a", 42, None),
            ("2", "/us/usc/t7/s1627b", 22, "new"),
            ("5", "/us/usc/t7/s1627b", 42, "new"),
        ]
        for seq, (pl_section, usc, number, action) in enumerate(rows, start=1):
            session.add(ClassificationEntry(
                file_id=table.id, congress=118, session=1, row_seq=seq,
                title_num="7", section_raw=usc.rsplit("/s", 1)[1], usc_identifier=usc, action=action,
                pl_congress=118, pl_num=number, pl_label=f"118-{number}",
                pl_section_raw=pl_section, pl_section_num=pl_section,
            ))
        session.commit()
        file_id = table.id
    yield
    with session_factory() as session:
        for entry in session.query(ClassificationEntry).filter_by(file_id=file_id).all():
            session.delete(entry)
        session.delete(session.get(ClassificationFile, file_id))
        session.commit()


def amended(client, identifier: str) -> dict:
    response = client.get(f"/api/v1{identifier}")
    assert response.status_code == 200, identifier
    return response.json()["currency"]["amended"]


# ------------------------------------------------------------- the ordering


def test_later_compares_numbers_then_dates():
    law = Candidate("/us/pl/83/703", "pl", 83, 703, datetime.date(1954, 8, 30))
    assert later(Candidate.of_pl(118, 67, None), law)
    assert not later(Candidate.of_pl(83, 703, None), law)
    assert not later(Candidate.of_pl(81, 740, datetime.date(1950, 8, 30)), law)
    act = Candidate("/us/act/1956-08-06/ch1015", "act", None, None, datetime.date(1956, 8, 6))
    assert later(act, law)
    assert not later(Candidate("/us/act/1946-08-01/ch724", "act", None, None, datetime.date(1946, 8, 1)), law)
    undated = Candidate("/us/act/1956-08-06/ch1015", "act", None, None, None)
    assert not later(undated, law)
    private = Candidate("/us/pvtl/83/900", "pvtl", 83, 900, None)
    assert not later(private, law)
    assert later(Candidate("/us/pvtl/84/1", "pvtl", 84, 1, None), law)


def test_newest_keeps_the_first_of_an_incomparable_pair():
    dated = Candidate.of_pl(108, 237, datetime.date(2004, 6, 22))
    undated_act = Candidate("/us/act/1955-07-07/ch281", "act", None, None, None)
    assert newest([undated_act, dated]) is undated_act
    assert newest([dated, undated_act]) is dated
    assert newest([]) is None
    assert newest([dated, Candidate.of_pl(118, 67, None)]).pl == "118-67"


# ------------------------------------------------------------ the statuses


def test_the_sherman_act_section_is_known_amended_by_credit_and_compilation(client):
    """15 U.S.C. § 1's source credit ends with Public Law 108-237; COMPS-3055 is
    current through the same law and its section 1 reads differently."""
    block = amended(client, "/us/act/1890-07-02/ch647/s1")
    assert block["status"] == "known_amended"
    assert block["evidence"] == ["source_credit", "compilation"]
    assert block["latest"] == {
        "pl": "108-237",
        "identifier": "/us/pl/108/237",
        "label": "Public Law 108-237",
        "enacted": "2004-06-22",
    }


def test_the_atomic_energy_act_section_one_is_known_amended(client):
    """Cited as `/us/act/1954-08-30/ch1073/s1`; the chapter alias is the law
    itself and does not count, Public Law 118-67 does."""
    block = amended(client, "/us/pl/83/703/s1")
    assert block["status"] == "known_amended"
    assert block["evidence"] == ["source_credit", "compilation"]
    assert block["latest"]["pl"] == "118-67" and block["latest"]["enacted"] == "2024-07-09"


def test_the_law_itself_is_judged_on_the_law_wide_evidence(client):
    """At law level the compilation fires on "current through a later law" alone."""
    block = amended(client, "/us/act/1954-08-30/ch1073")
    assert block["status"] == "known_amended"
    assert "compilation" in block["evidence"] and "source_credit" in block["evidence"]


def test_a_section_cited_only_in_notes_is_no_record(client):
    block = amended(client, "/us/pl/81/740/s3")
    assert block == {"status": "no_record", "latest": None, "evidence": []}


def test_a_private_law_is_unknown(client):
    assert amended(client, "/us/pvtl/81/375")["status"] == "unknown"


def test_a_law_in_no_index_is_unknown(client):
    """Nothing in the citation slice cites Public Law 81-910 and no table covers it."""
    assert amended(client, "/us/pl/81/910/s101")["status"] == "unknown"
    assert amended(client, "/us/pl/81/910/tI")["status"] == "unknown"


def test_a_credit_naming_only_the_law_itself_is_no_record(client):
    """16 U.S.C. § 450oo's source credit names Public Law 85-910 and nothing later."""
    block = amended(client, "/us/pl/85/910/s1")
    assert block == {"status": "no_record", "latest": None, "evidence": []}


# ------------------------------------------------------- classification rows


def test_classification_rows_of_a_later_law_fire(client, classification_rows):
    block = amended(client, "/us/pl/118/22/s101")
    assert block["status"] == "known_amended"
    assert block["evidence"] == ["classification"]
    assert block["latest"] == {"pl": "118-42", "identifier": "/us/pl/118/42", "label": "Public Law 118-42", "enacted": None}


def test_a_later_new_row_does_not_fire(client, classification_rows):
    """PL 118-42 § 5 is a `new` row on 7 U.S.C. § 1627b: not an amendment.
    The table covers Public Law 118-22, so the answer is `no_record`."""
    block = amended(client, "/us/pl/118/22/s2")
    assert block == {"status": "no_record", "latest": None, "evidence": []}


def test_a_law_a_table_covers_is_no_record(client, classification_rows, repo):
    """Section 3 of Public Law 118-22 has no row of its own; the table covers
    the law. Public Law 118-34 is outside the table and cited by the US Code."""
    assert amended(client, "/us/pl/118/22/s3")["status"] == "no_record"
    coverage = repo.index_coverage("/us/pl/118/34")
    assert coverage.cited and not coverage.tables_cover and not coverage.classified
    assert amended(client, "/us/pl/118/34/s1")["status"] == "no_record"


# ------------------------------------------------------------- the sentences


def test_the_note_sentence_for_each_status(client):
    known = client.get("/api/v1/us/act/1890-07-02/ch647/s1").json()["note"]
    assert (
        "This section has been amended since; the most recent law recorded is "
        "Public Law 108-237 (June 22, 2004)."
    ) in known
    no_record = client.get("/api/v1/us/pl/81/740/s3").json()["note"]
    assert f"No later amendment of this section is recorded in the indexes here ({INDEXES}); amendment may still have occurred." in no_record
    unknown = client.get("/api/v1/us/pl/81/910/tI").json()["note"]
    assert "Whether this title has been amended since is not recorded here." in unknown
    law = client.get("/api/v1/us/pvtl/81/375").json()["note"]
    assert "Whether this law has been amended since is not recorded here." in law


# ------------------------------------------------------------------- labels


def test_labels_carry_the_same_block(client):
    response = client.post(
        "/api/v1/labels",
        json={"identifiers": ["/us/act/1890-07-02/ch647/s1", "/us/pl/81/740/s3", "/us/pvtl/81/375", "/us/pl/83/703/tI"]},
    )
    body = response.json()
    sherman = body["/us/act/1890-07-02/ch647/s1"]["currency"]
    assert sherman["kind"] == "as_enacted" and sherman["date"] == "1890-07-02"
    assert sherman["amended"]["status"] == "known_amended"
    assert sherman["amended"]["evidence"] == ["source_credit", "compilation"]
    assert sherman["amended"]["latest"]["pl"] == "108-237"
    assert body["/us/pl/81/740/s3"]["currency"]["amended"] == {"status": "no_record", "latest": None, "evidence": []}
    assert body["/us/pvtl/81/375"]["currency"]["amended"]["status"] == "unknown"
    assert body["/us/pl/83/703/tI"]["currency"]["amended"]["status"] == "known_amended"


def test_labels_and_the_unit_agree(client):
    identifiers = ["/us/act/1890-07-02/ch647/s2", "/us/pl/85/910/s1", "/us/pl/81/910/s101"]
    labels = client.post("/api/v1/labels", json={"identifiers": identifiers}).json()
    for identifier in identifiers:
        assert labels[identifier]["currency"]["amended"] == amended(client, identifier)


# ------------------------------------------------- the codified alternative


def test_the_codified_alternative_comes_from_the_index(client):
    """Public Law 85-910 has no compilation; 16 U.S.C. § 450oo's source credit
    cites its section 1."""
    body = client.get("/api/v1/us/pl/85/910/s1").json()
    assert body["alternatives"] == [
        {
            "view": "codified",
            "identifier": None,
            "identifiers": ["/us/usc/t16/s450oo"],
            "current_through": None,
            "url": "https://uscode.linkedlegislation.org/us/usc/t16/s450oo",
        }
    ]
    assert "the US Code section(s) classified from it at 16 U.S.C. 450oo" in body["note"]


def test_the_compilation_reference_comes_first_and_the_index_follows(client):
    body = client.get("/api/v1/us/pl/83/703/s1").json()
    codified = next(a for a in body["alternatives"] if a["view"] == "codified")["identifiers"]
    assert codified[0] == "/us/usc/t42/s2011"
    assert codified == codified[:1] + sorted(codified[1:])
    assert len(codified) <= 20
    assert "42 U.S.C. 2011, 42 U.S.C. 2012" in body["note"]


def test_a_hierarchy_node_has_no_alternatives(client):
    body = client.get("/api/v1/us/pl/81/910/tI").json()
    assert body["alternatives"] == []
