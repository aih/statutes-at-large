"""The index: its fingerprint, its alias, and the documents it is built from.

No cluster. `stale_aliases`, `promote` and `sync` talk to one, so they are
driven against a fake that records what was asked of it — the sequence of calls
is the part that has to be right. The documents are read from the fixture
database.

The fingerprint has to be wrong in the safe direction: one that fails to change
when the mapping does leaves a deployed index missing fields nobody notices are
missing, because the mapping is not additive and an absent field returns no
results rather than an error.
"""

import copy
import datetime

import pytest
from sqlalchemy import select

from db.models import Unit
from ingest import search_sync
from storage.search import UNITS_ALIAS


class TestFingerprint:
    def test_it_is_stable_across_runs(self):
        assert search_sync.mapping_fingerprint() == search_sync.mapping_fingerprint()

    def test_key_order_does_not_change_it(self):
        reordered = {
            "settings": copy.deepcopy(search_sync.UNITS_MAPPING["settings"]),
            "mappings": copy.deepcopy(search_sync.UNITS_MAPPING["mappings"]),
        }
        assert search_sync.mapping_fingerprint(reordered) == search_sync.mapping_fingerprint()

    def test_field_order_does_not_change_it(self):
        changed = copy.deepcopy(search_sync.UNITS_MAPPING)
        properties = changed["mappings"]["properties"]
        changed["mappings"]["properties"] = dict(reversed(list(properties.items())))
        assert search_sync.mapping_fingerprint(changed) == search_sync.mapping_fingerprint()

    def test_a_new_field_changes_it(self):
        changed = copy.deepcopy(search_sync.UNITS_MAPPING)
        changed["mappings"]["properties"]["something_new"] = {"type": "keyword"}
        assert search_sync.mapping_fingerprint(changed) != search_sync.mapping_fingerprint()

    def test_a_changed_field_type_changes_it(self):
        """The case that bites: a field whose type moved is not a new field,
        and an index built before it matches nothing on the new one."""
        changed = copy.deepcopy(search_sync.UNITS_MAPPING)
        changed["mappings"]["properties"]["congress"] = {"type": "keyword"}
        assert search_sync.mapping_fingerprint(changed) != search_sync.mapping_fingerprint()

    def test_the_index_name_carries_it(self):
        name = search_sync.index_name_for()
        assert name.startswith(f"{UNITS_ALIAS}_")
        assert name.endswith(search_sync.mapping_fingerprint())

    def test_the_stamped_fingerprint_is_of_the_mapping_without_it(self):
        """Otherwise it is circular: stamping `_meta` into the body would
        change the thing being fingerprinted, and no index would match."""
        body = search_sync._body_with_meta()
        assert body["mappings"]["_meta"]["fingerprint"] == search_sync.mapping_fingerprint()
        assert "_meta" not in search_sync.UNITS_MAPPING["mappings"]


class FakeIndices:
    """Just enough of `client.indices` to drive the swap and a build."""

    def __init__(self, concrete=(), aliases=None, meta=None):
        self.concrete = set(concrete)
        self.aliases = dict(aliases or {})  # alias -> {index: {}}
        self.meta = dict(meta or {})  # index -> fingerprint
        self.calls: list[tuple] = []
        self.settings: list[tuple] = []

    def exists(self, index):
        return index in self.concrete

    def exists_alias(self, name):
        return name in self.aliases

    def get_alias(self, name):
        return self.aliases[name]

    def get(self, index, ignore_unavailable=False):
        stem = index.rstrip("*")
        return {name: {} for name in self.concrete if name.startswith(stem)}

    def get_mapping(self, index):
        target = index
        if index in self.aliases:
            target = next(iter(self.aliases[index]))
        if target not in self.concrete:
            raise KeyError(index)
        fingerprint = self.meta.get(target)
        meta = {"_meta": {"fingerprint": fingerprint}} if fingerprint else {}
        return {target: {"mappings": meta}}

    def create(self, index, body):
        self.calls.append(("create", index))
        self.concrete.add(index)
        self.meta[index] = body["mappings"]["_meta"]["fingerprint"]

    def delete(self, index):
        self.calls.append(("delete", index))
        self.concrete.discard(index)
        self.meta.pop(index, None)

    def update_aliases(self, body):
        self.calls.append(("update_aliases", tuple(sorted(map(str, body["actions"])))))
        for action in body["actions"]:
            if "remove" in action:
                self.aliases.get(action["remove"]["alias"], {}).pop(
                    action["remove"]["index"], None
                )
            else:
                add = action["add"]
                self.aliases.setdefault(add["alias"], {})[add["index"]] = {}

    def put_settings(self, index, body):
        self.calls.append(("put_settings", index))
        self.settings.append((index, body["index"]["refresh_interval"]))

    def refresh(self, index):
        self.calls.append(("refresh", index))


class FakeClient:
    def __init__(self, indices=None):
        self.indices = indices or FakeIndices()


def _live(fingerprint=None):
    """A cluster whose alias points at an index built from this mapping."""
    name = search_sync.index_name_for(fingerprint)
    return FakeClient(
        FakeIndices(
            concrete=[name],
            aliases={UNITS_ALIAS: {name: {}}},
            meta={name: fingerprint or search_sync.mapping_fingerprint()},
        )
    )


class TestDriftDetection:
    def test_an_empty_cluster_is_stale(self):
        assert search_sync.stale_aliases(FakeClient()) == [UNITS_ALIAS]
        assert not search_sync.alias_is_current(FakeClient())

    def test_a_concrete_index_with_no_fingerprint_is_stale(self):
        """Any index built before fingerprints existed. It must rebuild, not
        pass for current because the name is there."""
        client = FakeClient(FakeIndices(concrete=[UNITS_ALIAS]))
        assert search_sync.stale_aliases(client) == [UNITS_ALIAS]

    def test_an_index_built_from_this_mapping_is_not_stale(self):
        assert search_sync.stale_aliases(_live()) == []
        assert search_sync.alias_is_current(_live())

    def test_an_index_built_from_an_older_mapping_is_stale(self):
        assert search_sync.stale_aliases(_live("oldfingerprint")) == [UNITS_ALIAS]


class TestPromote:
    def test_it_moves_the_alias_and_drops_the_old_index(self):
        old, new = f"{UNITS_ALIAS}_old", f"{UNITS_ALIAS}_new"
        indices = FakeIndices(concrete=[old, new], aliases={UNITS_ALIAS: {old: {}}})
        search_sync.promote(FakeClient(indices), UNITS_ALIAS, new)

        assert indices.aliases[UNITS_ALIAS] == {new: {}}
        assert old not in indices.concrete
        # One call, so the name never resolves to nothing.
        assert sum(1 for call in indices.calls if call[0] == "update_aliases") == 1

    def test_the_old_index_is_deleted_after_the_alias_moves(self):
        old, new = f"{UNITS_ALIAS}_old", f"{UNITS_ALIAS}_new"
        indices = FakeIndices(concrete=[old, new], aliases={UNITS_ALIAS: {old: {}}})
        search_sync.promote(FakeClient(indices), UNITS_ALIAS, new)

        kinds = [call[0] for call in indices.calls]
        assert kinds.index("update_aliases") < kinds.index("delete")

    def test_a_concrete_index_of_the_alias_name_is_replaced(self):
        """An index and an alias cannot share a name, so the index goes first —
        a gap of one round trip, on that migration only."""
        new = f"{UNITS_ALIAS}_new"
        indices = FakeIndices(concrete=[UNITS_ALIAS, new])
        search_sync.promote(FakeClient(indices), UNITS_ALIAS, new)

        assert indices.aliases[UNITS_ALIAS] == {new: {}}
        assert UNITS_ALIAS not in indices.concrete
        kinds = [call[0] for call in indices.calls]
        assert kinds.index("delete") < kinds.index("update_aliases")

    def test_promoting_what_is_already_live_deletes_nothing(self):
        live = f"{UNITS_ALIAS}_live"
        indices = FakeIndices(concrete=[live], aliases={UNITS_ALIAS: {live: {}}})
        search_sync.promote(FakeClient(indices), UNITS_ALIAS, live)

        assert indices.aliases[UNITS_ALIAS] == {live: {}}
        assert not [call for call in indices.calls if call[0] == "delete"]

    def test_a_failed_delete_does_not_undo_the_promotion(self):
        """The alias is already right; a leftover index costs disk and nothing
        else."""
        old, new = f"{UNITS_ALIAS}_old", f"{UNITS_ALIAS}_new"

        class Stubborn(FakeIndices):
            def delete(self, index):
                raise RuntimeError("no")

        indices = Stubborn(concrete=[old, new], aliases={UNITS_ALIAS: {old: {}}})
        search_sync.promote(FakeClient(indices), UNITS_ALIAS, new)
        assert indices.aliases[UNITS_ALIAS] == {new: {}}


class TestSortKeys:
    def test_a_page_label_sorts_by_its_number(self):
        assert search_sync.page_sort_key("563") < search_sync.page_sort_key("1000")

    def test_a_lettered_page_keeps_its_prefix(self):
        # Labels are stored lower case (gotcha 6); the appendix follows the
        # numbered pages.
        assert search_sync.page_sort_key("a12") == "a000012"
        assert search_sync.page_sort_key("563") < search_sync.page_sort_key("a12")

    def test_a_volume_orders_before_its_pages(self):
        assert search_sync.citation_sort_key(64, "999", 1) < search_sync.citation_sort_key(
            124, "1", 1
        )

    def test_no_volume_has_no_key(self):
        assert search_sync.citation_sort_key(None, None, 1) is None


class TestDocumentIds:
    def test_an_enacted_document_is_its_identifier(self):
        assert search_sync.enacted_doc_id("/us/pl/81/740/s3") == "/us/pl/81/740/s3"

    def test_a_second_occurrence_is_distinguished(self):
        # `units.occurrence` > 1 is the source numbering two units alike, and
        # the only way one identifier is two documents.
        assert search_sync.enacted_doc_id("/us/pl/81/740/s3", 2) == "/us/pl/81/740/s3~2"

    def test_a_compiled_document_carries_its_package(self):
        """Several COMPS files share one identifier prefix (gotcha 8), so the
        package is what tells their documents apart."""
        assert (
            search_sync.compiled_doc_id("/us/sComp/74/271/tII/s202", "COMPS-8755")
            == "/us/sComp/74/271/tII/s202@COMPS-8755"
        )


@pytest.fixture()
def enacted(db):
    return {doc["_id"]: doc["_source"] for doc in search_sync.unit_documents(db)}


@pytest.fixture()
def compiled(db):
    return {doc["_id"]: doc["_source"] for doc in search_sync.comp_documents(db)}


class TestEnactedDocuments:
    def test_a_section_carries_its_text_and_its_law(self, enacted):
        doc = enacted["/us/pl/81/740/s3"]
        assert doc["view"] == "enacted"
        assert doc["level"] == "section" and doc["num"] == "3"
        assert "corporation" in doc["text"]
        assert doc["law_identifier"] == "/us/pl/81/740"
        assert doc["law_label"] == "Public Law 81-740"
        assert (doc["kind"], doc["congress"], doc["number"], doc["chapter"]) == (
            "pl", 81, 740, 823,
        )
        assert doc["enacted"] == "1950-08-30" and doc["year"] == 1950
        assert (doc["volume"], doc["first_page"], doc["citation"]) == (64, "563", "64 Stat. 563")

    def test_a_hierarchy_node_carries_a_heading_and_no_text(self, enacted):
        doc = enacted["/us/pl/85/322/tI"]
        assert doc["level"] == "title"
        assert doc["heading"] == "OFFICE OF THE SECRETARY OF DEFENSE"
        assert doc["text"] is None

    def test_a_quoted_section_is_not_a_document_of_its_own(self, enacted, db):
        """A `<section>` inside `quotedContent` is not a section of this law
        (gotcha 5): it stays inside the enclosing section's text."""
        quoting = "/us/pl/81/725/s1"
        xml = db.scalar(select(Unit.xml).where(Unit.identifier == quoting))
        assert "quotedContent" in xml and "<section" in xml.split("quotedContent", 1)[1]
        assert [i for i in enacted if i.startswith(f"{quoting}/")] == []
        assert enacted[quoting]["text"]

    def test_citation_order_follows_the_printed_page(self, enacted):
        # 64 Stat. 563 before 64 Stat. 564.
        assert (
            enacted["/us/pl/81/740/s3"]["citation_sort"]
            < enacted["/us/pl/81/740/s4"]["citation_sort"]
        )
        assert enacted["/us/pl/81/740/s4"]["first_page"] == "564"

    def test_every_document_carries_text_or_a_heading(self, enacted):
        assert enacted and all(
            doc["text"] or doc["heading"] for doc in enacted.values()
        )

    def test_since_limits_the_stream_to_what_was_loaded_after(self, db):
        tomorrow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        assert list(search_sync.unit_documents(db, since=tomorrow)) == []


class TestCompiledDocuments:
    def test_a_compiled_section_is_a_second_answer(self, compiled, enacted):
        doc = compiled["/us/sComp/51/647/s1@COMPS-3055"]
        assert doc["view"] == "compiled"
        assert doc["comp_prefix"] == "/us/sComp/51/647"
        assert doc["current_through"]
        assert doc["law_identifier"] == "/us/act/1890-07-02/ch647"
        assert "contract" in doc["text"]
        # The enacted section of the same law is its own document.
        assert "/us/act/1890-07-02/ch647/s1" in enacted

    def test_a_compilation_with_no_loaded_law_still_indexes(self, compiled):
        """The FD&C Act's compilation is loaded and its law is not, so the
        compilation's own title stands in and citation order has nothing to
        place it by."""
        doc = compiled["/us/sComp/75/675/chI/s1@COMPS-973"]
        assert doc["law_identifier"] is None
        assert doc["law_label"]
        assert doc["citation_sort"] is None

    def test_since_limits_the_stream(self, db):
        tomorrow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        assert list(search_sync.comp_documents(db, since=tomorrow)) == []


class TestSync:
    @pytest.fixture()
    def bulk(self, monkeypatch):
        sent: list[dict] = []

        def fake_bulk(client, actions, **kw):
            actions = list(actions)
            sent.extend(actions)
            return len(actions), []

        monkeypatch.setattr(search_sync, "_disabled", lambda: False)
        monkeypatch.setattr(search_sync.helpers, "bulk", fake_bulk)
        return sent

    def test_it_writes_into_the_index_it_is_given(self, bulk):
        client = FakeClient()
        written = search_sync.sync(
            client, "somewhere_else", [{"_id": "a", "_source": {"identifier": "a"}}]
        )
        assert written == 1
        assert bulk[0] == {"_index": "somewhere_else", "_id": "a",
                           "_source": {"identifier": "a"}}

    def test_a_build_pauses_the_refresh_and_restores_it(self, bulk):
        client = FakeClient()
        search_sync.sync(client, "an_index", [{"_id": "a", "_source": {}}])
        assert client.indices.settings == [("an_index", -1), ("an_index", None)]
        assert ("refresh", "an_index") in client.indices.calls

    def test_the_restore_survives_a_failure(self, monkeypatch):
        monkeypatch.setattr(search_sync, "_disabled", lambda: False)
        monkeypatch.setattr(
            search_sync.helpers, "bulk", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no"))
        )
        client = FakeClient()
        with pytest.raises(RuntimeError):
            search_sync.sync(client, "an_index", [{"_id": "a", "_source": {}}])
        assert client.indices.settings[-1] == ("an_index", None)

    def test_a_write_through_the_alias_leaves_the_refresh_alone(self, bulk):
        client = FakeClient()
        search_sync.sync(client, UNITS_ALIAS, [{"_id": "a", "_source": {}}], pause_refresh=False)
        assert client.indices.settings == []

    def test_disabled_writes_nothing(self, monkeypatch):
        monkeypatch.setenv("DISABLE_SEARCH_SYNC", "1")
        client = FakeClient()
        assert search_sync.sync(client, "an_index", [{"_id": "a", "_source": {}}]) == 0
        assert client.indices.calls == []


class TestRebuild:
    @pytest.fixture()
    def counted(self, monkeypatch):
        monkeypatch.setattr(search_sync, "_disabled", lambda: False)
        monkeypatch.setattr(
            search_sync.helpers,
            "bulk",
            lambda client, actions, **kw: (len(list(actions)), []),
        )

    def test_it_builds_beside_the_live_alias(self, db, counted):
        client = _live("oldfingerprint")
        old = search_sync.index_name_for("oldfingerprint")
        report = search_sync.rebuild(db, client)

        assert report["index"] == search_sync.index_name_for()
        assert report["fingerprint"] == search_sync.mapping_fingerprint()
        assert report["documents"]["enacted"] > 0
        assert report["documents"]["compiled"] > 0
        assert client.indices.aliases[UNITS_ALIAS] == {report["index"]: {}}
        # The build wrote into the new index while the alias still pointed at
        # the old one.
        kinds = [call for call in client.indices.calls if call[0] in ("create", "update_aliases")]
        assert kinds[0] == ("create", report["index"])
        assert old not in client.indices.concrete

    def test_recreate_drops_what_is_there_first(self, db, counted):
        client = _live()
        live = search_sync.index_name_for()
        search_sync.rebuild(db, client, recreate=True)

        kinds = [call[0] for call in client.indices.calls]
        assert kinds.index("delete") < kinds.index("create")
        assert client.indices.aliases[UNITS_ALIAS] == {live: {}}

    def test_a_resync_writes_through_the_alias(self, db, counted):
        client = _live()
        report = search_sync.resync_since(db, client, datetime.datetime(1900, 1, 1))
        assert report["alias"] == UNITS_ALIAS
        assert report["documents"]["enacted"] > 0
        assert not [call for call in client.indices.calls if call[0] == "put_settings"]

    def test_disabled_does_nothing(self, db, monkeypatch):
        monkeypatch.setenv("DISABLE_SEARCH_SYNC", "1")
        client = FakeClient()
        assert "skipped" in search_sync.rebuild(db, client)
        assert "skipped" in search_sync.resync_since(db, client, datetime.datetime(2026, 1, 1))
        assert client.indices.calls == []
