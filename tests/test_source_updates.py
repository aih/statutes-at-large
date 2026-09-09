"""The weekly update's three questions to their sources, with the network
mocked by respx and the committed slices standing in for the volume files:
`fetch-statute --if-changed` (the Hub tree listing against the files on
disk), `statute --changed-only` (the files against their last load), and
`citations --from-hub --if-changed` (the dataset revision against the one
recorded). Each writes a `source_checks` row whether or not it loaded."""

from __future__ import annotations

import hashlib
import shutil

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from db.base import Base, make_engine
from db.models import Citation, SourceCheck
from ingest.hub import (
    HUB_API,
    HUB_RESOLVE,
    USCODE_DATASET,
    HubFile,
    git_blob_sha1,
    list_volume_files,
    parse_tree,
    sha256_of,
    tree_url,
    volume_of,
    volume_url,
)
from ingest.load import recorded_volume_sha
from tests.conftest import CITATIONS_SLICE, FIXTURES

mock = respx.mock(assert_all_mocked=True, assert_all_called=False)


def factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def checks(sessions, collection: str) -> list[SourceCheck]:
    with sessions() as session:
        return session.scalars(select(SourceCheck).where(SourceCheck.collection == collection).order_by(SourceCheck.id)).all()


def lfs_entry(name: str, path) -> dict:
    """A tree entry for a file stored through LFS, as the Hub lists one."""
    size = path.stat().st_size
    return {"type": "file", "oid": "0" * 40, "size": size, "path": f"xmls/{name}", "lfs": {"oid": sha256_of(path), "size": size, "pointerSize": 134}}


def git_entry(name: str, path) -> dict:
    """A tree entry for a small file kept in git itself: only the blob id."""
    return {"type": "file", "oid": git_blob_sha1(path), "size": path.stat().st_size, "path": f"xmls/{name}"}


@pytest.fixture()
def volumes(tmp_path):
    """Slices 64 and 72 on disk under the Hub's names."""
    directory = tmp_path / "xmls"
    directory.mkdir()
    shutil.copy(FIXTURES / "statute-64-slice.xml", directory / "STATUTE-64.xml")
    shutil.copy(FIXTURES / "statute-72-slice.xml", directory / "STATUTE-72.xml")
    return directory


@pytest.fixture()
def sessions(monkeypatch):
    import db.base

    made = factory()
    monkeypatch.setattr(db.base, "SessionLocal", made)
    return made


# ---------------------------------------------------------------- the listing


def test_the_tree_listing_is_parsed_lfs_and_git_alike(volumes):
    entries = parse_tree([
        lfs_entry("STATUTE-64.xml", volumes / "STATUTE-64.xml"),
        git_entry("STATUTE-72.xml", volumes / "STATUTE-72.xml"),
        {"type": "directory", "oid": "abc", "path": "xmls/extra"},
    ])
    assert [(e.volume, e.sha256 is not None) for e in entries] == [(64, True), (72, False)]
    assert entries[0].matches(volumes / "STATUTE-64.xml")
    assert entries[1].matches(volumes / "STATUTE-72.xml")
    assert not entries[0].matches(volumes / "STATUTE-72.xml")
    assert not entries[1].matches(volumes / "STATUTE-64.xml")
    assert not entries[0].matches(volumes / "STATUTE-99.xml")
    assert volume_of("data/statute/xmls/STATUTE-137.xml") == 137 and volume_of("slice.xml") is None


def test_the_git_blob_id_is_gits(tmp_path):
    path = tmp_path / "STATUTE-1.xml"
    path.write_bytes(b"<volume/>")
    assert git_blob_sha1(path) == hashlib.sha1(b"blob 9\0<volume/>").hexdigest()


def test_a_changed_byte_is_a_changed_file(volumes):
    entry = parse_tree([lfs_entry("STATUTE-64.xml", volumes / "STATUTE-64.xml")])[0]
    with (volumes / "STATUTE-64.xml").open("ab") as handle:
        handle.write(b"\n")
    assert not entry.matches(volumes / "STATUTE-64.xml")


def test_the_listing_follows_link_next(volumes):
    first = [lfs_entry("STATUTE-64.xml", volumes / "STATUTE-64.xml")]
    second = [lfs_entry("STATUTE-72.xml", volumes / "STATUTE-72.xml")]
    with mock:
        # The cursor route first: a route without params matches the cursor
        # URL too, and respx takes the first match.
        mock.get(tree_url(), params={"cursor": "abc"}).mock(return_value=httpx.Response(200, json=second))
        mock.get(tree_url()).mock(
            return_value=httpx.Response(200, json=first, headers={"Link": f'<{tree_url()}?cursor=abc>; rel="next"'})
        )
        found = list_volume_files()
    assert sorted(found) == [64, 72]
    assert isinstance(found[64], HubFile) and found[64].path == "xmls/STATUTE-64.xml"


# ------------------------------------------------- fetch-statute --if-changed


def test_fetch_if_changed_downloads_only_what_differs(volumes, sessions, capsys):
    from ingest.__main__ import main

    on_hub_72 = FIXTURES / "statute-137-slice.xml"  # the Hub's 72 is not the one on disk
    with mock:
        mock.get(tree_url()).mock(
            return_value=httpx.Response(200, json=[
                lfs_entry("STATUTE-64.xml", volumes / "STATUTE-64.xml"),
                lfs_entry("STATUTE-72.xml", on_hub_72),
                lfs_entry("STATUTE-124.xml", FIXTURES / "statute-124-slice.xml"),
            ])
        )
        download = mock.get(volume_url(72)).mock(return_value=httpx.Response(200, content=on_hub_72.read_bytes()))
        code = main(["fetch-statute", "64", "72", "99", "--if-changed", "--dir", str(volumes)])
    out, err = capsys.readouterr()
    assert code == 0
    assert download.call_count == 1
    assert sha256_of(volumes / "STATUTE-72.xml") == sha256_of(on_hub_72)
    assert "64\t" in out and "unchanged" in out and "fetched" in out
    assert "99\tnot on the Hub" in err
    assert out.strip().endswith("3 volumes listed, 2 asked for, 1 fetched")
    (row,) = checks(sessions, "STATUTE")
    assert row.ok and row.packages_seen == 3 and row.new_packages == ["STATUTE-72"] and row.newest_package is None


def test_fetch_if_changed_fetches_a_missing_file_and_is_quiet_when_nothing_changed(volumes, sessions):
    from ingest.__main__ import main

    (volumes / "STATUTE-72.xml").unlink()
    with mock:
        mock.get(tree_url()).mock(
            return_value=httpx.Response(200, json=[
                lfs_entry("STATUTE-64.xml", volumes / "STATUTE-64.xml"),
                git_entry("STATUTE-72.xml", FIXTURES / "statute-72-slice.xml"),
            ])
        )
        download = mock.get(volume_url(72)).mock(
            return_value=httpx.Response(200, content=(FIXTURES / "statute-72-slice.xml").read_bytes())
        )
        assert main(["fetch-statute", "64-72", "--if-changed", "--dir", str(volumes)]) == 0
        assert download.call_count == 1
        assert main(["fetch-statute", "64-72", "--if-changed", "--dir", str(volumes)]) == 0
        assert download.call_count == 1
    first, second = checks(sessions, "STATUTE")
    assert first.new_packages == ["STATUTE-72"] and second.new_packages == [] and second.ok


def test_a_failed_listing_is_a_check_that_is_not_ok(volumes, sessions, capsys):
    from ingest.__main__ import main

    with mock:
        mock.get(tree_url()).mock(return_value=httpx.Response(503))
        code = main(["fetch-statute", "64", "--if-changed", "--dir", str(volumes)])
    assert code == 1
    (row,) = checks(sessions, "STATUTE")
    assert not row.ok and row.error and "503" in row.error and row.new_packages == []
    assert "could not be read" in capsys.readouterr().err


# ------------------------------------------------- statute --changed-only


def test_changed_only_skips_the_file_its_last_load_read(volumes, sessions, capsys):
    from ingest.__main__ import main

    path = volumes / "STATUTE-64.xml"
    assert main(["statute", str(path)]) == 0
    with sessions() as session:
        assert recorded_volume_sha(session, 64) == sha256_of(path)
        assert recorded_volume_sha(session, 72) is None
    assert main(["statute", str(path), "--changed-only"]) == 0
    out = capsys.readouterr().out
    assert "unchanged since its last load, skipped" in out and out.strip().endswith("1 files unchanged since their last load; nothing loaded")
    load, quiet = checks(sessions, "STATUTE")
    assert load.newest_package == "STATUTE-64" and load.source_sha256 == sha256_of(path)
    assert quiet.newest_package is None and quiet.packages_seen == 1 and quiet.new_packages == [] and quiet.ok

    with path.open("ab") as handle:
        handle.write(b"\n")  # still well-formed: whitespace after the root
    assert main(["statute", str(path), "--changed-only"]) == 0
    assert "STATUTE-64: 10 laws" in capsys.readouterr().out
    rows = checks(sessions, "STATUTE")
    assert len(rows) == 3 and rows[-1].newest_package == "STATUTE-64" and rows[-1].source_sha256 == sha256_of(path)


def test_changed_only_loads_a_volume_never_loaded(volumes, sessions, capsys):
    from ingest.__main__ import main

    assert main(["statute", str(volumes / "STATUTE-72.xml"), "--changed-only"]) == 0
    assert "STATUTE-72:" in capsys.readouterr().out
    (row,) = checks(sessions, "STATUTE")
    assert row.newest_package == "STATUTE-72"


# --------------------------------------------- citations --from-hub --if-changed


def dataset_info(revision: str) -> dict:
    return {"sha": revision, "siblings": [{"rfilename": "current/train-00000-of-00001.parquet"}, {"rfilename": "README.md"}]}


def test_citations_if_changed_reloads_on_a_new_revision_and_skips_on_the_same(tmp_path, sessions, capsys):
    from ingest.__main__ import main

    shards = tmp_path / "uscode"
    with mock:
        mock.get(HUB_API.format(dataset=USCODE_DATASET)).mock(return_value=httpx.Response(200, json=dataset_info("rev-1")))
        shard = mock.get(
            HUB_RESOLVE.format(dataset=USCODE_DATASET, revision="rev-1", path="current/train-00000-of-00001.parquet")
        ).mock(return_value=httpx.Response(200, content=CITATIONS_SLICE.read_bytes()))
        assert main(["citations", "--from-hub", "--if-changed", "--dir", str(shards)]) == 0
        assert shard.call_count == 1
        with sessions() as session:
            rows = session.scalar(select(Citation.id).limit(1))
        assert rows is not None
        (load,) = checks(sessions, "USCODE")
        assert load.newest_package == "rev-1" and load.packages_seen == 1

        assert main(["citations", "--from-hub", "--if-changed", "--dir", str(shards)]) == 0
        assert shard.call_count == 1
        assert "revision rev-1 unchanged since the last load; nothing to do" in capsys.readouterr().out
        load, skipped = checks(sessions, "USCODE")
        assert skipped.newest_package == "rev-1" and skipped.packages_seen == 0 and skipped.new_packages == [] and skipped.ok

        mock.get(HUB_API.format(dataset=USCODE_DATASET)).mock(return_value=httpx.Response(200, json=dataset_info("rev-2")))
        mock.get(
            HUB_RESOLVE.format(dataset=USCODE_DATASET, revision="rev-2", path="current/train-00000-of-00001.parquet")
        ).mock(return_value=httpx.Response(200, content=CITATIONS_SLICE.read_bytes()))
        assert main(["citations", "--from-hub", "--if-changed", "--force", "--dir", str(shards)]) == 0
        assert checks(sessions, "USCODE")[-1].newest_package == "rev-2"
        assert (shards / "REVISION").read_text().strip() == "rev-2"

    from storage.postgres import PostgresRepository

    with sessions() as session:
        status = PostgresRepository(session).citation_index_status()
    assert status.dataset_revision == "rev-2" and status.loaded_at is not None and status.checked_at is not None


def test_the_status_keeps_loaded_at_on_the_load_when_a_check_skipped(sessions):
    """A skipped check moves `checked_at` and leaves `loaded_at` on the load."""
    from ingest.citations import load_citations
    from ingest.load import record_source_check
    from storage.postgres import PostgresRepository

    with sessions() as session:
        load_citations(session, [CITATIONS_SLICE], revision="rev-1")
        loaded_at = checks(sessions, "USCODE")[0].checked_at
        record_source_check(session, "USCODE", ok=True, packages_seen=0, new_packages=[], newest_package="rev-1")
        status = PostgresRepository(session).citation_index_status()
    assert status.loaded_at.replace(tzinfo=None) == loaded_at.replace(tzinfo=None)
    assert status.checked_at >= status.loaded_at and status.dataset_revision == "rev-1"
