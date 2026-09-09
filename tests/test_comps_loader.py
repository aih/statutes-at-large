"""`load_comp` and `poll` over SQLite, on top of the session-loaded slices:
idempotence, a second version, `through=`, the law link, the source checks."""

import datetime
import json

from sqlalchemy import select

from db.models import Comp, CompUnit, CompVersion, Law, LawAlias, SourceCheck
from ingest.comps import load_comp, load_comp_file, parse_comp, poll
from tests.conftest import COMPS_FIXTURES

ATOMIC = COMPS_FIXTURES / "COMPS-1630-slice.xml"
ATOMIC_SUMMARY = COMPS_FIXTURES / "COMPS-1630.summary.json"


def _comp(session, file_id: str) -> Comp:
    return session.scalars(select(Comp).where(Comp.file_id == file_id)).one()


def _versions(session, comp: Comp) -> list[CompVersion]:
    return list(session.scalars(select(CompVersion).where(CompVersion.comp_id == comp.id).order_by(CompVersion.id)).all())


def test_the_fixtures_were_loaded(loaded, db):
    assert loaded["COMPS-1630-slice.xml"].action == "new"
    assert loaded["COMPS-3055.xml"].unidentified_sections == 1
    assert sorted(c.file_id for c in db.scalars(select(Comp)).all()) == ["1630", "3055", "8755", "973"]
    comp = _comp(db, "1630")
    assert comp.package_id == "COMPS-1630" and comp.identifier_prefix == "/us/sComp/83/703"
    assert comp.law_congress == 83 and comp.law_number == 703 and comp.law_id is not None
    versions = _versions(db, comp)
    assert len(versions) == 1 and versions[0].is_current and versions[0].current_through_pl == "118-67"
    units = db.scalars(select(CompUnit).where(CompUnit.comp_version_id == versions[0].id).order_by(CompUnit.seq)).all()
    assert [u.identifier for u in units][:3] == ["/us/sComp/83/703/tI", "/us/sComp/83/703/tI/ch1.", "/us/sComp/83/703/tI/ch1./s1"]
    assert units[2].usc_refs == ["/us/usc/t42/s2011"] and units[2].xml.startswith("<section")


def test_loading_the_same_file_twice_is_one_version(db):
    report = load_comp_file(db, ATOMIC, summary_path=ATOMIC_SUMMARY)
    assert report.action == "unchanged" and report.versions == 1
    comp = _comp(db, "1630")
    assert len(_versions(db, comp)) == 1
    assert report.law_identifier == "/us/pl/83/703"


def test_a_changed_text_is_a_second_version(db, repo):
    xml = ATOMIC.read_text(encoding="utf-8")
    assert "Atomic energy is capable of application" in xml
    modified = (
        xml.replace("Atomic energy is capable of application", "Atomic energy is CAPABLE of application")
        .replace("<currentThroughPublicLaw>118–67</currentThroughPublicLaw>", "<currentThroughPublicLaw>119–1</currentThroughPublicLaw>")
        .replace("<currentThroughPublicLaw>P.L. 118–67</currentThroughPublicLaw>", "<currentThroughPublicLaw>P.L. 119–1</currentThroughPublicLaw>")
        .replace('<date date="2024-07-09">July 9, 2024</date>', '<date date="2025-01-03">January 3, 2025</date>')
    )
    summary = json.loads(ATOMIC_SUMMARY.read_text())
    summary["lastModified"] = "2026-09-10T00:00:00Z"
    record = parse_comp(modified, summary=summary)
    assert record.current_through_pl == "119-1"
    comp = _comp(db, "1630")
    before = _versions(db, comp)
    assert len(before) == 1
    old_id = before[0].id
    report = load_comp(db, record)
    try:
        assert report.action == "new_version" and report.versions == 2
        versions = _versions(db, comp)
        assert [v.is_current for v in versions] == [False, True]
        assert versions[0].id == old_id and versions[1].current_through_pl == "119-1"
        assert versions[1].govinfo_last_modified.replace(tzinfo=datetime.timezone.utc) == datetime.datetime(2026, 9, 10, tzinfo=datetime.timezone.utc)

        ref = repo.get_comp("1630")
        assert [v.current_through_pl for v in ref.versions] == ["118-67", "119-1"]
        assert ref.current.current_through_pl == "119-1"

        current = repo.get_comp_unit("/us/sComp/83/703/tI/ch1./s1")
        assert current.version.current_through_pl == "119-1" and current.pinned is False
        assert "CAPABLE" in current.text
        old = repo.get_comp_unit("/us/sComp/83/703/tI/ch1./s1", through="118-67")
        assert old.version.current_through_pl == "118-67" and old.pinned is True
        assert "CAPABLE" not in old.text and "capable" in old.text
        assert repo.get_comp_unit("/us/sComp/83/703/tI/ch1./s1", through="200-1") is None
    finally:
        # Put the shared database back: the API tests expect one version.
        versions = _versions(db, comp)
        for version in versions:
            if version.id != old_id:
                db.delete(version)
            else:
                version.is_current = True
        db.commit()
    assert [v.is_current for v in _versions(db, comp)] == [True]
    assert repo.get_comp_unit("/us/sComp/83/703/tI/ch1./s1").version.current_through_pl == "118-67"


def test_law_id_is_set_when_the_enacted_law_is_loaded(db, repo):
    """Public Law 83-703 comes from the volume 68 slice; the loader links the
    compilation to it, and a law that is not loaded (74-271) stays unlinked."""
    comp = _comp(db, "1630")
    law_id = db.scalar(select(Law.id).where(Law.identifier == "/us/pl/83/703"))
    assert law_id is not None and comp.law_id == law_id
    assert repo.get_comp("1630").law_identifier == "/us/pl/83/703"
    assert [c.file_id for c in repo.compilations_for_law("/us/pl/83/703")] == ["1630"]
    assert [c.file_id for c in repo.compilations_for_law("/us/act/1954-08-30/ch1073")] == ["1630"]
    assert _comp(db, "8755").law_id is None
    # The Sherman Act (1890) links by congress and chapter, there being no law number.
    assert repo.get_comp("3055").law_identifier == "/us/act/1890-07-02/ch647"



class _FakeClient:
    """Answers the poller from the fixtures; records what was asked."""

    def __init__(self, packages, *, broken: set[str] = frozenset(), fail_walk: bool = False):
        self.packages = packages
        self.broken = set(broken)
        self.fail_walk = fail_walk
        self.calls: list[tuple[str, str]] = []

    def collection(self, collection, since):
        self.calls.append(("collection", f"{collection}@{since.isoformat()}"))
        if self.fail_walk:
            raise RuntimeError("HTTP 503 for https://api.govinfo.gov/collections/COMPS/x?api_key=SECRET&offsetMark=*")
        yield from self.packages

    def summary(self, package_id):
        self.calls.append(("summary", package_id))
        return json.loads((COMPS_FIXTURES / f"{package_id}.summary.json").read_text())

    def uslm(self, package_id):
        self.calls.append(("uslm", package_id))
        if package_id in self.broken:
            raise RuntimeError(f"HTTP 500 for https://api.govinfo.gov/packages/{package_id}/uslm?api_key=SECRET")
        name = f"{package_id}.xml" if (COMPS_FIXTURES / f"{package_id}.xml").exists() else f"{package_id}-slice.xml"
        return (COMPS_FIXTURES / name).read_text(encoding="utf-8")


def test_poll_skips_current_packages_and_records_a_check(db):
    packages = [
        {"packageId": "COMPS-1630", "lastModified": "2026-09-04T12:08:06Z"},  # stored: not fetched
        {"packageId": "COMPS-3055", "lastModified": "2026-09-06T00:00:00Z"},  # newer listing, same bytes
        {"packageId": "COMPS-973", "lastModified": "2026-09-06T01:00:00Z"},
    ]
    client = _FakeClient(packages, broken={"COMPS-973"})
    since = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
    report = poll(db, client, since=since)
    assert report.seen == 3 and report.skipped == 1 and report.fetched == 2
    assert report.unchanged == 1 and report.failed == 1 and report.new == 0 and report.new_versions == 0
    assert report.newest_last_modified == "2026-09-06T01:00:00+00:00" and report.newest_package == "COMPS-973"
    assert report.failures[0]["package"] == "COMPS-973"
    assert "SECRET" not in report.failures[0]["error"] and "api_key" not in report.failures[0]["error"]
    assert ("uslm", "COMPS-1630") not in client.calls
    assert client.calls[0] == ("collection", "COMPS@2026-09-01T00:00:00+00:00")
    check = db.scalars(select(SourceCheck).where(SourceCheck.collection == "COMPS").order_by(SourceCheck.id.desc())).first()
    assert check.ok is True and check.packages_seen == 3 and check.newest_package == "COMPS-973"
    assert "SECRET" not in (check.error or "")
    # The stored data is untouched.
    assert len(_versions(db, _comp(db, "3055"))) == 1


def test_poll_with_limit_and_force(db):
    packages = [{"packageId": "COMPS-3055", "lastModified": "2020-01-01T00:00:00Z"}, {"packageId": "COMPS-8755", "lastModified": "2020-01-01T00:00:00Z"}]
    client = _FakeClient(packages)
    report = poll(db, client, since=datetime.datetime(2019, 1, 1, tzinfo=datetime.timezone.utc), limit=1, force=True)
    assert report.seen == 1 and report.fetched == 1 and report.unchanged == 1
    assert ("uslm", "COMPS-3055") in client.calls and ("uslm", "COMPS-8755") not in client.calls


def test_poll_limit_counts_fetched_not_seen(db):
    """A package already current is skipped without a call and does not use
    up the limit, so a bounded walk of a newest-first listing advances."""
    since = datetime.datetime(2019, 1, 1, tzinfo=datetime.timezone.utc)
    # COMPS-3055 is current in the fixture database; COMPS-8755 is listed
    # with a later lastModified, so it is due.
    packages = [{"packageId": "COMPS-3055", "lastModified": "2020-01-01T00:00:00Z"}, {"packageId": "COMPS-8755", "lastModified": "2030-01-01T00:00:00Z"}]
    client = _FakeClient(packages)
    report = poll(db, client, since=since, limit=1)
    assert report.seen == 2 and report.skipped == 1 and report.fetched == 1
    assert ("uslm", "COMPS-3055") not in client.calls and ("uslm", "COMPS-8755") in client.calls


def test_a_failed_walk_is_recorded_and_raised(db):
    import pytest

    client = _FakeClient([], fail_walk=True)
    before = db.scalar(select(SourceCheck.id).order_by(SourceCheck.id.desc()))
    with pytest.raises(RuntimeError):
        poll(db, client, since=datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc))
    check = db.scalars(select(SourceCheck).where(SourceCheck.collection == "COMPS").order_by(SourceCheck.id.desc())).first()
    assert check.id != before and check.ok is False
    assert check.error.startswith("RuntimeError: HTTP 503 for https://api.govinfo.gov/collections/COMPS/x")
    assert "SECRET" not in check.error and "api_key" not in check.error


def test_default_since_follows_the_last_check(db):
    from ingest.comps import DEFAULT_SINCE, default_since

    newest = db.scalar(
        select(SourceCheck.newest_last_modified)
        .where(SourceCheck.collection == "COMPS", SourceCheck.newest_last_modified.is_not(None))
        .order_by(SourceCheck.newest_last_modified.desc())
    )
    since = default_since(db)
    if newest is None:
        assert since == DEFAULT_SINCE
    else:
        assert since == newest.replace(tzinfo=datetime.timezone.utc) - datetime.timedelta(days=1)
