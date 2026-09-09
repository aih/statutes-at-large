"""The search index: its mapping, its documents, and the bulk build.

One document per unit that carries text or a heading, under one alias
(`storage.search.UNITS_ALIAS`) pointing at a physical index named for the
mapping fingerprint. Two views are indexed side by side and neither collapses
the other: a section of an enacted law is `view: enacted`, and the same section
in a compilation's current version is a second document, `view: compiled`.

Hierarchy nodes are indexed with their heading and no text. Quoted sections are
not units (gotcha 5) and so are not documents.

Loads do not index. `python -m ingest reindex-search` is the only thing in
`ingest/` that reaches a cluster, and `DISABLE_SEARCH_SYNC=1` makes even that a
no-op, so `make test` and every load run cluster-free.

The rebuild path is `rebuild(session, client)`: create the index for the
current mapping, fill it while readers are still served by the live one, and
move the alias in one `update_aliases` call. `resync_since(session, client,
since)` writes the laws loaded since a date through the live alias instead.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import logging
import os
import re
from collections.abc import Iterator
from typing import Any, Iterable

from opensearchpy import helpers
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Comp, CompUnit, CompVersion, Law, Unit
from storage.identifiers import law_label
from storage.search import UNITS_ALIAS

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
"""Rows read from Postgres, and documents sent to OpenSearch, per batch."""


def _disabled() -> bool:
    """`DISABLE_SEARCH_SYNC=1`: index nothing and reach no cluster."""
    return os.environ.get("DISABLE_SEARCH_SYNC") == "1"


# ----------------------------------------------------------------- the mapping

UNITS_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "identifier": {"type": "keyword"},
            "law_identifier": {"type": "keyword"},
            "law_label": {"type": "keyword"},
            "kind": {"type": "keyword"},
            "congress": {"type": "integer"},
            "number": {"type": "integer"},
            "chapter": {"type": "integer"},
            "level": {"type": "keyword"},
            "num": {"type": "keyword"},
            # The standard analyzer, named rather than left to the default so
            # the mapping says what it is: it lowercases and tokenizes and does
            # not stem. A different word is a different rule (ADR-0031 on the
            # US Code site).
            "heading": {"type": "text", "analyzer": "standard"},
            "text": {"type": "text", "analyzer": "standard"},
            "short_titles": {"type": "text", "analyzer": "standard"},
            "official_title": {"type": "text", "analyzer": "standard"},
            "enacted": {"type": "date"},
            "year": {"type": "integer"},
            "volume": {"type": "integer"},
            "first_page": {"type": "keyword"},
            "citation": {"type": "keyword"},
            "view": {"type": "keyword"},
            "comp_prefix": {"type": "keyword"},
            "current_through": {"type": "keyword"},
            # Citation order as one sortable string — `?sort=citation`.
            "citation_sort": {"type": "keyword"},
        }
    },
    # One node, so a replica would sit unassigned and leave the index yellow.
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
}


def mapping_fingerprint(mapping: dict[str, Any] | None = None) -> str:
    """A short, stable hash of the mapping as declared.

    This is what makes "the deployed index was built from older code" a
    question a script can answer. The mapping is not additive: OpenSearch will
    not add a field type to a live index, so a field the query names and the
    index lacks is **absent rather than broken** — `congress:117` matches
    nothing, which reads exactly like a congress with nothing in it.

    Computed over canonical JSON, so a field moved in the source is not a
    change, and before `_meta` is attached, so stamping the fingerprint into
    the index does not change the fingerprint.
    """
    canonical = json.dumps(mapping or UNITS_MAPPING, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def index_name_for(fingerprint: str | None = None) -> str:
    """`statutes_units_a1b2c3d4e5f6`: the physical index for a mapping.

    The name carries the mapping it was built from, so two generations can
    exist at once — which is what lets a rebuild finish before anything reads
    from it.
    """
    return f"{UNITS_ALIAS}_{fingerprint or mapping_fingerprint()}"


def _body_with_meta() -> dict[str, Any]:
    body = copy.deepcopy(UNITS_MAPPING)
    body.setdefault("mappings", {})["_meta"] = {
        "fingerprint": mapping_fingerprint(),
        "alias": UNITS_ALIAS,
    }
    return body


def create_index(client, name: str | None = None) -> str:
    """Create the physical index for the current mapping and return its name.

    Create-if-absent: a half-built index left by a failed run is reused, and
    its documents are overwritten by `_id`. Does not point the alias at it —
    see `promote`.
    """
    name = name or index_name_for()
    if not client.indices.exists(index=name):
        client.indices.create(index=name, body=_body_with_meta())
    return name


def indexed_fingerprint(client, alias: str = UNITS_ALIAS) -> str | None:
    """The mapping fingerprint of whatever `alias` resolves to.

    None when the alias resolves to nothing, or to an index built before
    fingerprints existed — both of which mean "rebuild".
    """
    try:
        mappings = client.indices.get_mapping(index=alias)
    except Exception:
        return None
    for body in mappings.values():
        meta = body.get("mappings", {}).get("_meta") or {}
        return meta.get("fingerprint")
    return None


def alias_is_current(client) -> bool:
    """The live index was built from the mapping this code declares."""
    return indexed_fingerprint(client) == mapping_fingerprint()


def stale_aliases(client) -> list[str]:
    """The aliases whose index was built from a mapping this code no longer
    declares: `[UNITS_ALIAS]` or `[]`. A list, so `--if-changed` reads the same
    here as on the US Code site."""
    return [] if alias_is_current(client) else [UNITS_ALIAS]


def promote(client, alias: str, new_index: str) -> None:
    """Point `alias` at `new_index`, and delete whatever it pointed at before.

    The alias moves in one `update_aliases` call, so the name never resolves to
    nothing: a search issued during a rebuild reads the old index until this
    returns and the new one after.

    The exception is a cluster where `alias` is a *concrete index* rather than
    an alias. An index and an alias cannot share a name, so the index is
    deleted first — a gap of one round trip, on that migration only (the US
    Code site's ADR-0051).
    """
    old: list[str] = []
    if client.indices.exists_alias(name=alias):
        old = [name for name in client.indices.get_alias(name=alias) if name != new_index]
    elif client.indices.exists(index=alias):
        logger.info("replacing the concrete index %s with an alias", alias)
        client.indices.delete(index=alias)

    actions: list[dict[str, Any]] = [
        {"remove": {"index": name, "alias": alias}} for name in old
    ]
    actions.append({"add": {"index": new_index, "alias": alias}})
    client.indices.update_aliases(body={"actions": actions})

    for name in old:
        try:
            client.indices.delete(index=name)
        except Exception as exc:
            # The alias already points at the new index, so the site is correct
            # either way; this only leaves disk in use.
            logger.warning("could not delete the superseded index %s: %s", name, exc)


def delete_indices(client) -> list[str]:
    """Delete every index named for this alias, and the alias's own target.
    What `--recreate` spends before building from nothing."""
    names: set[str] = set()
    try:
        if client.indices.exists_alias(name=UNITS_ALIAS):
            names.update(client.indices.get_alias(name=UNITS_ALIAS))
        elif client.indices.exists(index=UNITS_ALIAS):
            names.add(UNITS_ALIAS)
        names.update(client.indices.get(index=f"{UNITS_ALIAS}_*", ignore_unavailable=True))
    except Exception as exc:
        logger.warning("could not list the indices for %s: %s", UNITS_ALIAS, exc)
    deleted = []
    for name in sorted(names):
        try:
            client.indices.delete(index=name)
            deleted.append(name)
        except Exception as exc:
            logger.warning("could not delete %s: %s", name, exc)
    return deleted


# --------------------------------------------------------------- the documents

_PAGE_LABEL = re.compile(r"^([a-z]*)(\d*)(.*)$")


def page_sort_key(page: str | None) -> str:
    """A Statutes at Large page label as a sortable string.

    Labels are stored lower case (gotcha 6) and are a letter prefix, a number,
    and sometimes a suffix: `563`, `a12`, `1234-1`. The number is padded to six
    digits so `563` sorts before `1000`, and the letter prefix is kept in
    front, which puts the numbered pages of a volume ahead of its appendix.
    """
    match = _PAGE_LABEL.match((page or "").lower())
    if match is None:
        return ""
    prefix, digits, rest = match.groups()
    return f"{prefix}{int(digits or 0):06d}{rest}"


def citation_sort_key(volume: int | None, page: str | None, seq: int | None) -> str | None:
    """Volume, then printed page, then position in the law: the order the
    Statutes at Large print in. None when there is no volume to start from,
    which sorts last."""
    if volume is None:
        return None
    return f"{volume:04d}|{page_sort_key(page)}|{(seq or 0):06d}"


def enacted_doc_id(identifier: str, occurrence: int = 1) -> str:
    """`/us/pl/81/740/s3`.

    The identifier alone, so a rebuild overwrites rather than duplicating. The
    occurrence is appended only when the source numbered two units alike
    (`units.occurrence` > 1), which is the only way one identifier is two
    documents.
    """
    return identifier if occurrence <= 1 else f"{identifier}~{occurrence}"


def compiled_doc_id(identifier: str, package_id: str) -> str:
    """`/us/sComp/74/271/tII/s202@COMPS-8755`.

    The package, not the identifier prefix: several COMPS files share one
    prefix (gotcha 8 — the Social Security Act has a file per title), and the
    package id is what tells their documents apart. Stable across rebuilds.
    """
    return f"{identifier}@{package_id}"


def _law_fields(law: Law) -> dict[str, Any]:
    return {
        "law_identifier": law.identifier,
        "law_label": law_label(law.kind, law.congress, law.number, law.chapter, law.enacted),
        "kind": law.kind,
        "congress": law.congress,
        "number": law.number,
        "chapter": law.chapter,
        "short_titles": list(law.short_titles or ()),
        "official_title": law.official_title,
        "enacted": law.enacted.isoformat() if law.enacted else None,
        "year": law.enacted.year if law.enacted else None,
        "volume": law.stat_volume,
        "citation": law.citation,
    }


def unit_documents(
    session: Session, *, since: datetime.datetime | datetime.date | None = None
) -> Iterator[dict[str, Any]]:
    """The enacted documents, streamed from `units` joined to `laws`.

    One document per unit that carries text or a heading: a section with its
    text, a hierarchy node with its heading and no text. `since` limits the
    stream to laws whose `loaded_at` is at or after that moment, which is what
    `--since` re-syncs.

    Each item is `{"_id": …, "_source": {…}}`; the index is `sync`'s to name.
    """
    stmt = (
        select(Unit, Law)
        .join(Law, Law.id == Unit.law_id)
        .where((Unit.text.is_not(None)) | (Unit.heading.is_not(None)))
        .order_by(Law.id, Unit.seq)
    )
    if since is not None:
        stmt = stmt.where(Law.loaded_at >= since)

    for unit, law in session.execute(stmt.execution_options(yield_per=BATCH_SIZE)):
        text = (unit.text or "").strip()
        heading = (unit.heading or "").strip()
        if not text and not heading:
            continue
        page = unit.first_page or law.stat_page_first
        source = _law_fields(law) | {
            "identifier": unit.identifier,
            "level": unit.level,
            "num": unit.num,
            "heading": heading or None,
            "text": text or None,
            "first_page": page,
            "view": "enacted",
            "citation_sort": citation_sort_key(law.stat_volume, page, unit.seq),
        }
        yield {"_id": enacted_doc_id(unit.identifier, unit.occurrence), "_source": source}


def comp_documents(
    session: Session, *, since: datetime.datetime | datetime.date | None = None
) -> Iterator[dict[str, Any]]:
    """The compiled documents: the units of every compilation's current
    version, streamed from `comp_units`.

    `view` is `compiled`, `comp_prefix` is the compilation's identifier prefix
    and `current_through` the public law it is current through. The law fields
    come from the enacted law when the compilation is matched to one; when it
    is not, the compilation's own title and approval date stand in, and
    `citation_sort` is absent, so those documents sort last in citation order.

    `since` limits the stream to versions fetched at or after that moment.
    """
    stmt = (
        select(CompUnit, CompVersion, Comp, Law)
        .join(CompVersion, CompVersion.id == CompUnit.comp_version_id)
        .join(Comp, Comp.id == CompVersion.comp_id)
        .outerjoin(Law, Law.id == Comp.law_id)
        .where(CompVersion.is_current.is_(True))
        .where((CompUnit.text.is_not(None)) | (CompUnit.heading.is_not(None)))
        .order_by(Comp.id, CompUnit.seq)
    )
    if since is not None:
        stmt = stmt.where(CompVersion.fetched_at >= since)

    for unit, version, comp, law in session.execute(
        stmt.execution_options(yield_per=BATCH_SIZE)
    ):
        text = (unit.text or "").strip()
        heading = (unit.heading or "").strip()
        if not text and not heading:
            continue
        if law is not None:
            fields = _law_fields(law)
            page = law.stat_page_first
            fields["citation_sort"] = citation_sort_key(law.stat_volume, page, unit.seq)
        else:
            fields = {
                "law_identifier": None,
                "law_label": comp.display_title or comp.title,
                "kind": None,
                "congress": comp.law_congress,
                "number": comp.law_number,
                "chapter": None,
                "short_titles": list(comp.short_titles or ()),
                "official_title": comp.title,
                "enacted": comp.approved_date.isoformat() if comp.approved_date else None,
                "year": comp.approved_date.year if comp.approved_date else None,
                "volume": None,
                "citation": None,
                "citation_sort": None,
            }
            page = None
        source = fields | {
            "identifier": unit.identifier,
            "level": unit.level,
            "num": unit.num,
            "heading": heading or None,
            "text": text or None,
            "first_page": page,
            "view": "compiled",
            "comp_prefix": comp.identifier_prefix,
            "current_through": version.current_through_pl,
        }
        yield {"_id": compiled_doc_id(unit.identifier, comp.package_id), "_source": source}


# ------------------------------------------------------------------- the write


def sync(
    client,
    index: str,
    docs: Iterable[dict[str, Any]],
    *,
    pause_refresh: bool = True,
) -> int:
    """Bulk-index `docs` into `index` and return how many were written.

    Each item is `{"_id": …, "_source": {…}}` as the document streams produce
    them; `index` is added here, so a rebuild fills the new generation while
    readers are still served by the old one.

    `pause_refresh` sets `refresh_interval=-1` for the length of the write and
    restores the default afterwards, which is what a build wants and a write
    through the live alias does not.

    A bulk failure raises (`opensearchpy.helpers.BulkIndexError`): the caller
    decides, and the deploy step that calls it is `|| echo`, so a failed
    rebuild leaves the alias where it was.
    """
    if _disabled():
        logger.info("DISABLE_SEARCH_SYNC=1: %s was not written", index)
        return 0

    def actions() -> Iterator[dict[str, Any]]:
        for doc in docs:
            yield {"_index": index, "_id": doc["_id"], "_source": doc["_source"]}

    if pause_refresh:
        client.indices.put_settings(index=index, body={"index": {"refresh_interval": -1}})
    try:
        written, _ = helpers.bulk(client, actions(), chunk_size=BATCH_SIZE)
    finally:
        if pause_refresh:
            client.indices.put_settings(
                index=index, body={"index": {"refresh_interval": None}}
            )
        client.indices.refresh(index=index)
    return written


def rebuild(session, client, *, recreate: bool = False) -> dict[str, Any]:
    """Build the index for the current mapping and move the alias onto it.

    `recreate` deletes every index named for the alias first, so a half-built
    one left by a failed run is not reused. The alias is moved only after both
    document streams are written, so a failure part-way leaves the live index
    serving.

    Returns the report the CLI prints: the index name, the fingerprint, and the
    documents written per view.
    """
    if _disabled():
        return {"skipped": "DISABLE_SEARCH_SYNC=1"}

    if recreate:
        delete_indices(client)
    fingerprint = mapping_fingerprint()
    index = create_index(client, index_name_for(fingerprint))
    enacted = sync(client, index, unit_documents(session))
    compiled = sync(client, index, comp_documents(session))
    promote(client, UNITS_ALIAS, index)
    return {
        "alias": UNITS_ALIAS,
        "index": index,
        "fingerprint": fingerprint,
        "documents": {"enacted": enacted, "compiled": compiled},
        "recreated": recreate,
    }


def resync_since(
    session, client, since: datetime.datetime | datetime.date
) -> dict[str, Any]:
    """Re-index the laws loaded, and the compilation versions fetched, at or
    after `since`, writing through the live alias.

    What the weekly update runs after `--if-changed`: a load that added or
    replaced laws is a few thousand documents, not a rebuild. A document whose
    unit no longer exists is not removed — `--recreate` is what drops those.
    """
    if _disabled():
        return {"skipped": "DISABLE_SEARCH_SYNC=1"}

    enacted = sync(client, UNITS_ALIAS, unit_documents(session, since=since), pause_refresh=False)
    compiled = sync(client, UNITS_ALIAS, comp_documents(session, since=since), pause_refresh=False)
    return {
        "alias": UNITS_ALIAS,
        "since": since.isoformat(),
        "documents": {"enacted": enacted, "compiled": compiled},
    }
