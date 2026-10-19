"""The SQLAlchemy `Repository` implementation — where all the SQL lives.

Resolution follows design section 3:

  1. Exact identifier match on a stored unit, or on the law.
  2. Otherwise the longest stored prefix; when that is a section, the rest of
     the path is cut from the section's XML by `@identifier`.
  3. Otherwise the section-number index under the law.
  4. A law answers to every alias in `law_aliases`.

The class is named for the deployment database; the SQL is portable and the
test suite runs it over SQLite.
"""

from __future__ import annotations

import contextvars
import dataclasses
import datetime
import functools
import hashlib
from collections.abc import Sequence

from sqlalchemy import Text, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from db.models import (
    Citation,
    ClassificationCheck,
    ClassificationEntry,
    ClassificationFile,
    Comp,
    CompUnit,
    CompVersion,
    Law,
    LawAlias,
    PendingLaw as PendingLawRow,
    SourceCheck,
    StatPage,
    Unit,
)
from storage.identifiers import (
    ParsedIdentifier,
    act_title,
    congress_of_date,
    congress_ordinal,
    congress_years,
    law_label,
    parse_identifier,
    parse_stat_page,
    title_order,
)
from storage.repository import (
    CitationIndexStatus,
    CitationRef,
    CitedBy,
    CitingSection,
    ClassificationCheckInfo,
    ClassificationFileRef,
    ClassificationRow,
    ClassificationStatus,
    CollectionStatus,
    CongressDetail,
    CongressesOverview,
    CongressLawItem,
    CongressSummary,
    IndexCoverage,
    LawCite,
    LawSources,
    SourceCreditEvidence,
    CompCounterpart,
    CompRef,
    CompUnitResult,
    CompVersionRef,
    LabelInfo,
    PendingLaw,
    LawRef,
    LawSummary,
    PageRef,
    Provision,
    SourceCheckInfo,
    StatPageDocument,
    StatPageResult,
    UnitRef,
    UnitResult,
)
from uslmtext import PageSlice, fragment_by_identifier, page_slice, plain_text, serialize


_slice_source: contextvars.ContextVar[Law] = contextvars.ContextVar("law_of_the_slice")
"""The law `_page_slice` reads its XML from: the cache is keyed on the law and
the page and holds the slice's strings, never a row."""


@functools.lru_cache(maxsize=256)
def _page_slice(law_id: int, content_hash: str, page: str) -> PageSlice:
    """The slice, cached on the law and the page (ADR-0020). The law itself is
    not an argument, so the cache holds no row and reads the XML on a miss
    only."""
    return page_slice(_slice_source.get().xml, page)


def _law_page_slice(law: Law, page: str) -> PageSlice:
    """The page's slice of the law, computed once per (law, hash, page)."""
    token = _slice_source.set(law)
    try:
        return _page_slice(law.id, law.content_hash, page)
    finally:
        _slice_source.reset(token)


FIRST_PLAW_CONGRESS = 104
"""GovInfo's PLAW collection starts with the 104th Congress."""
FIRST_PLAW_USLM_CONGRESS = 113
"""Bulk-data USLM starts with the 113th."""


class PostgresRepository:
    """`Repository` over the stage-1 schema."""

    def __init__(self, session: Session):
        self._session = session

    # ---------------------------------------------------------------- enacted

    def get_unit(self, identifier: str, *, wanted: str = "json") -> UnitResult | None:
        parsed = parse_identifier(identifier)
        if parsed is None or parsed.kind == "sComp":
            return None
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return None
        base = "exact" if parsed.law_identifier == law.identifier else "alias"
        if not parsed.path:
            return self._law_result(law, parsed.law_identifier + parsed.path, base)
        return self._resolve_under(law, parsed, base)

    def get_law(self, identifier: str) -> LawSummary | None:
        parsed = parse_identifier(identifier)
        if parsed is None or parsed.kind == "sComp":
            return None
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return None
        units = self._session.scalars(
            select(Unit).where(Unit.law_id == law.id, Unit.occurrence == 1).order_by(Unit.seq)
        ).all()
        return LawSummary(
            law=self._law_ref(law),
            toc=tuple(self._unit_ref(u) for u in units),
            section_count=sum(1 for u in units if u.level == "section"),
        )

    def get_section_by_number(self, law_identifier: str, section_num: str) -> UnitResult | None:
        parsed = parse_identifier(law_identifier)
        if parsed is None:
            return None
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return None
        unit = self._section_by_number(law, section_num)
        if unit is None:
            return None
        requested = f"{parsed.law_identifier}/s{section_num}"
        resolution = "exact" if unit.identifier == requested else "section_number"
        return self._unit_result(law, unit, requested, resolution, provision_path=None)

    def stat_page(self, volume: int, page: str, *, with_slices: bool = False) -> StatPageResult | None:
        rows = self._session.execute(
            select(StatPage, Law)
            .join(Law, Law.id == StatPage.law_id)
            .where(StatPage.volume == volume, StatPage.page == page)
            .order_by(StatPage.starts_here.desc(), Law.seq_in_volume)
        ).all()
        if not rows:
            return None
        documents = []
        for sp, law in rows:
            cut = _law_page_slice(law, page) if with_slices else None
            documents.append(
                StatPageDocument(
                    law=self._law_ref(law),
                    starts_here=sp.starts_here,
                    unit_identifier=sp.unit_identifier,
                    units=self._units_on_page(law, page, sp.unit_identifier) if with_slices else (),
                    xml=cut.xml if cut is not None else None,
                    text=cut.text if cut is not None else None,
                    to_identifier=cut.to if cut is not None else None,
                )
            )
        return StatPageResult(volume=volume, page=page, documents=tuple(documents))

    def _units_on_page(self, law: Law, page: str, unit_identifier: str | None) -> tuple[UnitRef, ...]:
        """The unit the page marker falls in, then the units that start on the
        page, in reading order."""
        starting = self._session.scalars(
            select(Unit)
            .where(Unit.law_id == law.id, Unit.occurrence == 1, Unit.first_page == page)
            .order_by(Unit.seq)
        ).all()
        units = list(starting)
        if unit_identifier is not None:
            if any(u.identifier == unit_identifier for u in units):
                units.sort(key=lambda u: (u.identifier != unit_identifier, u.seq))
            else:
                head = self._session.scalars(
                    select(Unit).where(
                        Unit.law_id == law.id, Unit.occurrence == 1, Unit.identifier == unit_identifier
                    )
                ).first()
                if head is not None:
                    units.insert(0, head)
        return tuple(self._unit_ref(u) for u in units)

    def labels(self, identifiers: Sequence[str]) -> dict[str, LabelInfo]:
        found: dict[str, LabelInfo] = {}
        for identifier in identifiers:
            result = self.get_unit(identifier)
            if result is None:
                continue
            # A provision that was not found is a prefix answer, and the label
            # says so through `resolution`; the caller decides what to make of it.
            found[identifier] = LabelInfo(
                identifier=identifier,
                served_identifier=result.served_identifier,
                resolution=result.resolution,
                law=result.law,
                level=result.level,
                num=result.num,
                heading=result.heading,
            )
        return found

    def law_sources(self, law_identifier: str) -> LawSources | None:
        parsed = parse_identifier(law_identifier)
        if parsed is None or parsed.kind == "sComp":
            return None
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return None
        volume_package = f"STATUTE-{law.stat_volume}"
        volume_loaded = law.source_collection == "STATUTE" or self._session.scalar(
            select(Law.id).where(Law.source_collection == "STATUTE", Law.stat_volume == law.stat_volume).limit(1)
        ) is not None or self._session.scalar(
            select(SourceCheck.id).where(SourceCheck.collection == "STATUTE", SourceCheck.newest_package == volume_package).limit(1)
        ) is not None
        plaw_package = None
        plaw_uslm = False
        if law.kind in ("pl", "pvtl") and law.congress is not None and law.number is not None and law.congress >= FIRST_PLAW_CONGRESS:
            plaw_package = f"PLAW-{law.congress}{'publ' if law.kind == 'pl' else 'pvtl'}{law.number}"
            plaw_uslm = law.kind == "pl" and law.congress >= FIRST_PLAW_USLM_CONGRESS
        return LawSources(
            law_identifier=law.identifier,
            served_from=law.source_collection,
            package=law.source_package,
            provenance_identifiers=law.provenance_identifiers,
            volume=law.stat_volume,
            volume_package=volume_package,
            volume_loaded=volume_loaded,
            plaw_package=plaw_package,
            plaw_uslm=plaw_uslm,
        )

    # -- helpers

    def _law_by_alias(self, law_identifier: str) -> Law | None:
        return self._session.scalars(
            select(Law).join(LawAlias, LawAlias.law_id == Law.id).where(LawAlias.identifier == law_identifier)
        ).first()

    def _law_by_congress_number(self, congress: int, number: int) -> Law | None:
        """`/us/sComp/{c}/{n}` names a public law, or a chapter before 1901."""
        law = self._law_by_alias(f"/us/pl/{congress}/{number}")
        if law is not None:
            return law
        return self._session.scalars(
            select(Law).where(Law.congress == congress, Law.chapter == number, Law.kind == "act")
            .order_by(Law.id)
        ).first()

    def _resolve_under(self, law: Law, parsed: ParsedIdentifier, base: str) -> UnitResult | None:
        requested = parsed.law_identifier + parsed.path
        segments = list(parsed.segments)
        # 1. exact
        for cut in range(len(segments), 0, -1):
            candidate = law.identifier + "/" + "/".join(segments[:cut])
            unit = self._unit(law, candidate)
            if unit is None:
                continue
            rest = segments[cut:]
            if not rest:
                return self._unit_result(law, unit, requested, base, provision_path=None)
            # 2. a stored prefix; below a section the rest is cut from the XML.
            if unit.level == "section":
                return self._unit_result(
                    law, unit, requested, base,
                    provision_path=requested if base == "exact" else candidate + "/" + "/".join(rest),
                )
            return self._unit_result(law, unit, requested, "prefix", provision_path=None)
        # 3. the section-number index
        if parsed.section_num is not None:
            unit = self._section_by_number(law, parsed.section_num)
            if unit is not None:
                below = "/".join(parsed.below_section)
                provision_path = f"{unit.identifier}/{below}" if below else None
                return self._unit_result(law, unit, requested, "section_number", provision_path=provision_path)
        # 2 again: the law itself is the longest stored prefix.
        return self._law_result(law, requested, "prefix")

    def _unit(self, law: Law, identifier: str) -> Unit | None:
        return self._session.scalars(
            select(Unit).where(Unit.law_id == law.id, Unit.identifier == identifier, Unit.occurrence == 1)
        ).first()

    def _section_by_number(self, law: Law, section_num: str) -> Unit | None:
        return self._session.scalars(
            select(Unit)
            .where(Unit.law_id == law.id, Unit.level == "section", Unit.section_num == section_num, Unit.occurrence == 1)
            .order_by(Unit.seq)
        ).first()

    def _children(self, law: Law, parent_identifier: str | None) -> tuple[UnitRef, ...]:
        rows = self._session.scalars(
            select(Unit)
            .where(Unit.law_id == law.id, Unit.parent_identifier.is_(None) if parent_identifier is None else Unit.parent_identifier == parent_identifier, Unit.occurrence == 1)
            .order_by(Unit.seq)
        ).all()
        return tuple(self._unit_ref(u) for u in rows)

    def _occurrences(self, law: Law, identifier: str) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(Unit).where(Unit.law_id == law.id, Unit.identifier == identifier)
            )
            or 0
        )

    def _law_result(self, law: Law, requested: str, resolution: str) -> UnitResult:
        """`text` and `xml` are always empty for a law: the answer is its
        table of contents in every format, and `Law.xml` (a deferred column)
        is not read (ADR-0019)."""
        ref = self._law_ref(law)
        pages = self._session.scalars(
            select(StatPage.page).where(StatPage.law_id == law.id).order_by(StatPage.starts_here.desc(), StatPage.id)
        ).all()
        return UnitResult(
            requested_identifier=requested,
            served_identifier=law.identifier,
            resolution=resolution,
            law=ref,
            level="law",
            num=None,
            heading=law.official_title,
            xml="",
            text="",
            content_hash=law.content_hash,
            ancestors=(),
            children=self._children(law, None),
            pages=tuple(PageRef(law.stat_volume, p) for p in pages),
            provision=None,
        )

    def _unit_result(
        self, law: Law, unit: Unit, requested: str, resolution: str, *, provision_path: str | None
    ) -> UnitResult:
        provision = None
        if unit.level == "section":
            xml = unit.xml or ""
            text = unit.text or ""
            digest = unit.content_hash or law.content_hash
            if provision_path and provision_path != unit.identifier:
                fragment = fragment_by_identifier(xml, provision_path)
                if fragment is not None:
                    provision = Provision(provision_path, True, serialize(fragment), plain_text(fragment))
                else:
                    provision = Provision(provision_path, False)
                    if resolution == "exact":
                        resolution = "prefix"
            children: tuple[UnitRef, ...] = ()
        else:
            # A hierarchy node: its table of contents in every format; `xml`
            # and `text` are always empty and `Law.xml` is not read (ADR-0019).
            xml = ""
            text = ""
            digest = unit.content_hash or law.content_hash
            children = self._children(law, unit.identifier)
        pages = [unit.first_page] if unit.first_page else []
        pages += [p for p in unit.pages if p not in pages]
        return UnitResult(
            requested_identifier=requested,
            served_identifier=unit.identifier,
            resolution=resolution,
            law=self._law_ref(law),
            level=unit.level,
            num=unit.num,
            heading=unit.heading,
            xml=xml,
            text=text,
            content_hash=digest,
            ancestors=tuple(
                UnitRef(a["identifier"], a["level"], a.get("num"), a.get("heading"), False)
                for a in (unit.ancestors or [])
            ),
            children=children,
            pages=tuple(PageRef(law.stat_volume, p) for p in pages),
            provision=provision,
            occurrences=self._occurrences(law, unit.identifier),
        )

    def _law_ref(self, law: Law) -> LawRef:
        aliases = self._session.scalars(
            select(LawAlias.identifier).where(LawAlias.law_id == law.id).order_by(LawAlias.is_primary.desc(), LawAlias.identifier)
        ).all()
        return LawRef(
            identifier=law.identifier,
            kind=law.kind,
            congress=law.congress,
            number=law.number,
            chapter=law.chapter,
            enacted=law.enacted,
            doc_type=law.doc_type,
            official_title=law.official_title,
            short_titles=tuple(law.short_titles or ()),
            stat_volume=law.stat_volume,
            stat_page_first=law.stat_page_first,
            stat_page_last=law.stat_page_last,
            citation=law.citation,
            source_collection=law.source_collection,
            source_package=law.source_package,
            source_granule=law.source_granule,
            provenance_text=law.provenance_text,
            provenance_identifiers=law.provenance_identifiers,
            content_hash=law.content_hash,
            aliases=tuple(aliases),
        )

    @staticmethod
    def _unit_ref(unit: Unit) -> UnitRef:
        return UnitRef(unit.identifier, unit.level, unit.num, unit.heading, unit.level == "section", unit.occurrence)

    # --------------------------------------------------------------- compiled

    def compilations_for_law(self, law_identifier: str) -> list[CompRef]:
        parsed = parse_identifier(law_identifier)
        if parsed is None:
            return []
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return []
        return [self._comp_ref(c) for c in self._comps_of(law)]

    def _comps_of(self, law: Law) -> list[Comp]:
        clauses = [Comp.law_id == law.id]
        if law.congress is not None:
            if law.kind == "pl" and law.number is not None:
                clauses.append((Comp.law_congress == law.congress) & (Comp.law_number == law.number))
            if law.kind == "act" and law.chapter is not None:
                clauses.append((Comp.law_congress == law.congress) & (Comp.law_number == law.chapter))
        return list(self._session.scalars(select(Comp).where(or_(*clauses)).order_by(Comp.file_id)).all())

    def get_comp(self, file_id: str) -> CompRef | None:
        comp = self._session.scalars(
            select(Comp).where(or_(Comp.file_id == file_id, Comp.package_id == file_id))
        ).first()
        return self._comp_ref(comp, with_versions=True) if comp is not None else None

    def list_comps(self, *, law_identifier: str | None = None, q: str | None = None, limit: int = 50) -> list[CompRef]:
        if law_identifier:
            return self.compilations_for_law(law_identifier)[:limit]
        stmt = select(Comp)
        if q:
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Comp.title.ilike(needle),
                    Comp.display_title.ilike(needle),
                    cast(Comp.short_titles, Text).ilike(needle),
                )
            )
        stmt = stmt.order_by(Comp.display_title, Comp.file_id).limit(limit)
        return [self._comp_ref(c) for c in self._session.scalars(stmt).all()]

    def get_comp_unit(self, identifier: str, *, through: str | None = None, wanted: str = "json") -> CompUnitResult | None:
        parsed = parse_identifier(identifier)
        if parsed is None or parsed.kind != "sComp":
            return None
        comps = list(
            self._session.scalars(
                select(Comp).where(Comp.identifier_prefix == parsed.law_identifier).order_by(Comp.file_id)
            ).all()
        )
        if not comps:
            return None
        versions: list[CompVersion] = []
        for comp in comps:
            version = self._version_of(comp, through)
            if version is not None:
                versions.append(version)
        if not versions:
            return None
        pinned = through is not None
        requested = parsed.law_identifier + parsed.path
        if not parsed.path:
            return self._comp_root(versions, requested, "exact", pinned)
        version_ids = [v.id for v in versions]
        segments = list(parsed.segments)
        for cut in range(len(segments), 0, -1):
            candidate = parsed.law_identifier + "/" + "/".join(segments[:cut])
            unit = self._session.scalars(
                select(CompUnit).where(CompUnit.comp_version_id.in_(version_ids), CompUnit.identifier == candidate)
                .order_by(CompUnit.comp_version_id)
            ).first()
            if unit is None:
                continue
            rest = segments[cut:]
            if not rest:
                return self._comp_unit_result(unit, requested, "exact", pinned, provision_path=None)
            if unit.level == "section":
                return self._comp_unit_result(unit, requested, "exact", pinned, provision_path=requested)
            return self._comp_unit_result(unit, requested, "prefix", pinned, provision_path=None)
        if parsed.section_num is not None:
            unit = self._session.scalars(
                select(CompUnit)
                .where(CompUnit.comp_version_id.in_(version_ids), CompUnit.level == "section", CompUnit.section_num == parsed.section_num)
                .order_by(CompUnit.comp_version_id, CompUnit.seq)
            ).first()
            if unit is not None:
                below = "/".join(parsed.below_section)
                path = f"{unit.identifier}/{below}" if below else None
                return self._comp_unit_result(unit, requested, "section_number", pinned, provision_path=path)
        return self._comp_root(versions, requested, "prefix", pinned)

    def compiled_counterparts(self, law_identifier: str, section_num: str | None) -> list[CompCounterpart]:
        parsed = parse_identifier(law_identifier)
        if parsed is None:
            return []
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return []
        out: list[CompCounterpart] = []
        for comp in self._comps_of(law):
            version = self._version_of(comp, None)
            if version is None:
                continue
            ref = self._comp_ref(comp)
            vref = self._version_ref(version)
            if section_num is None:
                out.append(CompCounterpart(ref, vref, comp.identifier_prefix, "compilation", None, comp.display_title, (), None))
                continue
            for unit in self._session.scalars(
                select(CompUnit)
                .where(CompUnit.comp_version_id == version.id, CompUnit.level == "section", CompUnit.section_num == section_num)
                .order_by(CompUnit.seq)
            ).all():
                out.append(CompCounterpart(ref, vref, unit.identifier, unit.level, unit.num, unit.heading, tuple(unit.usc_refs or ()), unit.content_hash))
        return out

    def enacted_counterpart(self, comp_prefix: str, section_num: str | None) -> UnitResult | None:
        parsed = parse_identifier(comp_prefix)
        if parsed is None or parsed.kind != "sComp" or parsed.congress is None or parsed.number is None:
            return None
        law = self._law_by_congress_number(parsed.congress, parsed.number)
        if law is None:
            return None
        if section_num is None:
            return self._law_result(law, law.identifier, "exact")
        unit = self._section_by_number(law, section_num)
        if unit is None:
            return None
        return self._unit_result(law, unit, unit.identifier, "exact", provision_path=None)

    # -- helpers

    def _version_of(self, comp: Comp, through: str | None) -> CompVersion | None:
        stmt = select(CompVersion).where(CompVersion.comp_id == comp.id)
        if through is None:
            stmt = stmt.where(CompVersion.is_current.is_(True)).order_by(CompVersion.id.desc())
        else:
            stmt = stmt.where(CompVersion.current_through_pl == through.replace("–", "-")).order_by(CompVersion.id.desc())
        return self._session.scalars(stmt).first()

    def _comp_children(self, version_id: int, parent_identifier: str | None) -> tuple[UnitRef, ...]:
        rows = self._session.scalars(
            select(CompUnit)
            .where(CompUnit.comp_version_id == version_id, CompUnit.parent_identifier.is_(None) if parent_identifier is None else CompUnit.parent_identifier == parent_identifier)
            .order_by(CompUnit.seq)
        ).all()
        return tuple(UnitRef(u.identifier, u.level, u.num, u.heading, u.level == "section") for u in rows)

    def _comp_root(self, versions: list[CompVersion], requested: str, resolution: str, pinned: bool) -> CompUnitResult:
        """The compilation itself: the whole-act file when one exists, else
        every per-title file gathered in title order (ADR-0007, decision 8)."""
        whole = next((v for v in versions if v.comp.partial_of is None), None)
        if whole is not None:
            return self._comp_root_result(whole, requested, resolution, pinned)
        return self._gathered_root_result(versions, requested, resolution, pinned)

    def _comp_root_result(self, version: CompVersion, requested: str, resolution: str, pinned: bool) -> CompUnitResult:
        """`text` and `xml` are always empty for the compilation: the answer
        is its table of contents in every format, and `CompVersion.xml` (a
        deferred column) is not read (ADR-0019)."""
        comp = version.comp
        return CompUnitResult(
            requested_identifier=requested,
            served_identifier=comp.identifier_prefix,
            resolution=resolution,
            comp=self._comp_ref(comp),
            version=self._version_ref(version),
            pinned=pinned,
            level="compilation",
            num=None,
            heading=comp.display_title,
            xml="",
            text="",
            content_hash=version.content_hash,
            ancestors=(),
            children=self._comp_children(version.id, None),
            usc_refs=(),
            provision=None,
        )

    def _gathered_root_result(self, versions: list[CompVersion], requested: str, resolution: str, pinned: bool) -> CompUnitResult:
        """An act served title by title and having no whole-act file: the root
        is the files gathered in title order. `comp` is the first file with
        the act's title in place of its own and no `partial_of`; `version` is
        that file's; `children` are every file's top-level units; the hash
        is over the files' hashes. Nothing here reads a version's `xml`."""
        ordered = sorted(versions, key=lambda v: (title_order(v.comp.partial_of), v.comp.file_id))
        first = ordered[0].comp
        files = tuple(self._comp_ref(v.comp) for v in ordered)
        position = {v.id: index for index, v in enumerate(ordered)}
        rows = list(
            self._session.scalars(
                select(CompUnit).where(CompUnit.comp_version_id.in_(list(position)), CompUnit.parent_identifier.is_(None))
            ).all()
        )
        rows.sort(key=lambda u: (position[u.comp_version_id], u.seq))
        short_titles: list[str] = []
        for text in first.short_titles or ():
            trimmed = act_title(text, first.partial_of) or text
            if trimmed not in short_titles:
                short_titles.append(trimmed)
        comp = dataclasses.replace(
            files[0],
            display_title=act_title(first.display_title, first.partial_of),
            short_titles=tuple(short_titles),
            partial_of=None,
        )
        digest = hashlib.sha256(":".join(v.content_hash for v in ordered).encode("utf-8")).hexdigest()
        return CompUnitResult(
            requested_identifier=requested,
            served_identifier=first.identifier_prefix,
            resolution=resolution,
            comp=comp,
            version=self._version_ref(ordered[0]),
            pinned=pinned,
            level="compilation",
            num=None,
            heading=comp.display_title,
            xml="",
            text="",
            content_hash=digest,
            ancestors=(),
            children=tuple(UnitRef(u.identifier, u.level, u.num, u.heading, u.level == "section") for u in rows),
            usc_refs=(),
            provision=None,
            files=files,
        )

    def _comp_unit_result(
        self, unit: CompUnit, requested: str, resolution: str, pinned: bool, *, provision_path: str | None
    ) -> CompUnitResult:
        version = unit.version
        comp = version.comp
        provision = None
        if unit.level == "section":
            xml = unit.xml or ""
            text = unit.text or ""
            if provision_path and provision_path != unit.identifier:
                fragment = fragment_by_identifier(xml, provision_path)
                if fragment is not None:
                    provision = Provision(provision_path, True, serialize(fragment), plain_text(fragment))
                else:
                    provision = Provision(provision_path, False)
                    if resolution == "exact":
                        resolution = "prefix"
            children: tuple[UnitRef, ...] = ()
        else:
            # A hierarchy node: its table of contents in every format; `xml`
            # and `text` are always empty and `CompVersion.xml` is not read
            # (ADR-0019).
            xml = ""
            text = ""
            children = self._comp_children(version.id, unit.identifier)
        return CompUnitResult(
            requested_identifier=requested,
            served_identifier=unit.identifier,
            resolution=resolution,
            comp=self._comp_ref(comp),
            version=self._version_ref(version),
            pinned=pinned,
            level=unit.level,
            num=unit.num,
            heading=unit.heading,
            xml=xml,
            text=text,
            content_hash=unit.content_hash or version.content_hash,
            ancestors=tuple(
                UnitRef(a["identifier"], a["level"], a.get("num"), a.get("heading"), False)
                for a in (unit.ancestors or [])
            ),
            children=children,
            usc_refs=tuple(unit.usc_refs or ()),
            provision=provision,
            section_num=unit.section_num,
        )

    def _comp_ref(self, comp: Comp, *, with_versions: bool = False) -> CompRef:
        current = self._version_of(comp, None)
        versions: tuple[CompVersionRef, ...] = ()
        if with_versions:
            versions = tuple(
                self._version_ref(v)
                for v in self._session.scalars(
                    select(CompVersion).where(CompVersion.comp_id == comp.id).order_by(CompVersion.id)
                ).all()
            )
        law_identifier = None
        if comp.law_id is not None:
            law_identifier = self._session.scalar(select(Law.identifier).where(Law.id == comp.law_id))
        elif comp.law_congress is not None and comp.law_number is not None:
            law = self._law_by_congress_number(comp.law_congress, comp.law_number)
            law_identifier = law.identifier if law is not None else None
        return CompRef(
            file_id=comp.file_id,
            package_id=comp.package_id,
            identifier_prefix=comp.identifier_prefix,
            law_congress=comp.law_congress,
            law_number=comp.law_number,
            law_identifier=law_identifier,
            title=comp.title,
            display_title=comp.display_title,
            short_titles=tuple(comp.short_titles or ()),
            approved_date=comp.approved_date,
            partial_of=comp.partial_of,
            current=self._version_ref(current) if current is not None else None,
            versions=versions,
        )

    @staticmethod
    def _version_ref(version: CompVersion) -> CompVersionRef:
        return CompVersionRef(
            id=version.id,
            current_through_pl=version.current_through_pl,
            current_through_date=version.current_through_date,
            govinfo_last_modified=version.govinfo_last_modified,
            fetched_at=version.fetched_at,
            content_hash=version.content_hash,
            is_current=version.is_current,
        )

    # ---------------------------------------------------------------- indexes

    def cited_by(self, identifier: str, *, contexts: Sequence[str] | None = None,
                 limit: int = 50, offset: int = 0) -> CitedBy | None:
        stat = parse_stat_page(identifier)
        if stat is not None:
            target = and_(Citation.to_volume == stat.volume, Citation.to_page == stat.page)
            return self._cited_by(identifier, identifier, None, (identifier,), None, None, target, contexts, limit, offset)
        parsed = parse_identifier(identifier)
        if parsed is None or parsed.kind == "sComp":
            return None
        law = self._law_by_alias(parsed.law_identifier)
        law_ref = self._law_ref(law) if law is not None else None
        aliases = law_ref.aliases if law_ref is not None else (parsed.law_identifier,)
        section_num = parsed.section_num
        below = "/".join(parsed.below_section) or None
        clauses = [Citation.to_law.in_(list(aliases))]
        if section_num is not None:
            clauses.append(Citation.to_section_num == section_num)
            if below:
                tail = f"/s{section_num}/{below}"
                clauses.append(or_(Citation.to_path.like(f"%{tail}"), Citation.to_path.like(f"%{tail}/%")))
        elif parsed.path:
            # A hierarchy node: refs written with that hierarchy, at it or under it.
            clauses.append(or_(Citation.to_path == parsed.path, Citation.to_path.like(f"{parsed.path}/%")))
        requested = parsed.law_identifier + parsed.path
        law_identifier = law_ref.identifier if law_ref is not None else parsed.law_identifier
        return self._cited_by(requested, law_identifier, law_ref, tuple(aliases), section_num, below, and_(*clauses), contexts, limit, offset)

    def _cited_by(self, requested, law_identifier, law_ref, aliases, section_num, below, target, contexts, limit, offset) -> CitedBy:
        where = [target]
        if contexts:
            where.append(Citation.context.in_(list(contexts)))
        total = int(self._session.scalar(select(func.count(func.distinct(Citation.from_identifier))).where(*where)) or 0)
        context_rows = self._session.execute(
            select(Citation.context, func.count()).where(*where).group_by(Citation.context)
        ).all()
        labels = self._session.scalars(
            select(Citation.release_label).where(*where).distinct().order_by(Citation.release_label)
        ).all()
        page = self._session.scalars(
            select(Citation.from_identifier).where(*where).distinct().order_by(Citation.from_identifier).limit(limit).offset(offset)
        ).all()
        sections: list[CitingSection] = []
        if page:
            rows = self._session.scalars(
                select(Citation).where(*where, Citation.from_identifier.in_(page)).order_by(Citation.from_identifier, Citation.seq)
            ).all()
            by_section: dict[str, list[Citation]] = {}
            for row in rows:
                by_section.setdefault(row.from_identifier, []).append(row)
            for from_identifier in page:
                group = by_section.get(from_identifier, [])
                if not group:
                    continue
                first = group[0]
                sections.append(
                    CitingSection(
                        identifier=from_identifier,
                        citation=first.from_citation,
                        heading=first.from_heading,
                        release_label=first.release_label,
                        refs=tuple(self._citation_ref(r) for r in group),
                    )
                )
        return CitedBy(
            requested_identifier=requested,
            law_identifier=law_identifier,
            law=law_ref,
            aliases=aliases,
            section_num=section_num,
            below=below,
            sections=tuple(sections),
            total=total,
            contexts={c: int(n) for c, n in sorted(context_rows)},
            release_labels=tuple(labels),
        )

    @staticmethod
    def _citation_ref(row: Citation) -> CitationRef:
        return CitationRef(
            from_identifier=row.from_identifier,
            release_label=row.release_label,
            context=row.context,
            note_topic=row.note_topic,
            seq=row.seq,
            to_identifier=row.to_identifier,
            to_kind=row.to_kind,
            to_law=row.to_law,
            to_section_num=row.to_section_num,
            to_congress=row.to_congress,
            to_number=row.to_number,
            to_chapter=row.to_chapter,
            to_date=row.to_date,
        )

    def _law_aliases_for(self, law_identifier: str) -> tuple[Law | None, tuple[str, ...]]:
        parsed = parse_identifier(law_identifier)
        if parsed is None or parsed.kind == "sComp":
            return None, ()
        law = self._law_by_alias(parsed.law_identifier)
        if law is None:
            return None, (parsed.law_identifier,)
        aliases = self._session.scalars(select(LawAlias.identifier).where(LawAlias.law_id == law.id)).all()
        return law, tuple(aliases)

    def source_credit_evidence(self, law_identifier: str, section_num: str | None) -> tuple[SourceCreditEvidence, ...]:
        _, aliases = self._law_aliases_for(law_identifier)
        if not aliases:
            return ()
        clauses = [Citation.context == "sourceCredit", Citation.to_law.in_(list(aliases))]
        if section_num is not None:
            clauses.append(Citation.to_section_num == section_num)
        citing = self._session.execute(
            select(Citation.from_identifier, Citation.release_label, Citation.to_identifier)
            .where(*clauses).order_by(Citation.from_identifier, Citation.seq)
        ).all()
        if not citing:
            return ()
        cites: dict[tuple[str, str], list[str]] = {}
        for from_identifier, label, to_identifier in citing:
            cites.setdefault((from_identifier, label), []).append(to_identifier)
        credit_rows = self._session.scalars(
            select(Citation)
            .where(
                Citation.context == "sourceCredit",
                Citation.to_kind.in_(["pl", "pvtl", "act"]),
                Citation.from_identifier.in_(sorted({k[0] for k in cites})),
            )
            .order_by(Citation.from_identifier, Citation.seq)
        ).all()
        laws: dict[tuple[str, str], list[LawCite]] = {}
        for row in credit_rows:
            key = (row.from_identifier, row.release_label)
            if key not in cites:
                continue
            laws.setdefault(key, []).append(
                LawCite(row.to_law or row.to_identifier, row.to_kind, row.to_congress, row.to_number, row.to_chapter, row.to_date, row.seq)
            )
        return tuple(
            SourceCreditEvidence(from_identifier=key[0], release_label=key[1], cites=tuple(hrefs), laws=tuple(laws.get(key, ())))
            for key, hrefs in cites.items()
        )

    def _pl_of(self, law_identifier: str) -> tuple[int, int] | None:
        """The (congress, number) a classification table would write for the law."""
        law, aliases = self._law_aliases_for(law_identifier)
        if law is not None:
            if law.kind == "pl" and law.congress is not None and law.number is not None:
                return law.congress, law.number
            return None
        parsed = parse_identifier(law_identifier)
        if parsed is not None and parsed.kind == "pl" and parsed.congress is not None and parsed.number is not None:
            return parsed.congress, parsed.number
        return None

    def classification_rows(self, law_identifier: str, section_num: str | None = None) -> tuple[ClassificationRow, ...]:
        pl = self._pl_of(law_identifier)
        if pl is None:
            return ()
        clauses = [ClassificationEntry.pl_congress == pl[0], ClassificationEntry.pl_num == pl[1]]
        if section_num is not None:
            clauses.append(ClassificationEntry.pl_section_num == section_num)
        rows = self._session.scalars(
            select(ClassificationEntry).where(*clauses)
            .order_by(ClassificationEntry.congress, ClassificationEntry.session, ClassificationEntry.row_seq)
        ).all()
        return tuple(self._classification_row(r) for r in rows)

    def classification_amendments(self, law_identifier: str, section_num: str | None) -> tuple[ClassificationRow, ...]:
        pl = self._pl_of(law_identifier)
        if pl is None:
            return ()
        own = [ClassificationEntry.pl_congress == pl[0], ClassificationEntry.pl_num == pl[1], ClassificationEntry.usc_identifier.is_not(None)]
        if section_num is not None:
            own.append(ClassificationEntry.pl_section_num == section_num)
        targets = select(ClassificationEntry.usc_identifier).where(*own).distinct()
        later = or_(
            ClassificationEntry.pl_congress > pl[0],
            and_(ClassificationEntry.pl_congress == pl[0], ClassificationEntry.pl_num > pl[1]),
        )
        rows = self._session.scalars(
            select(ClassificationEntry)
            .where(ClassificationEntry.usc_identifier.in_(targets), later)
            .order_by(ClassificationEntry.pl_congress, ClassificationEntry.pl_num, ClassificationEntry.row_seq)
        ).all()
        return tuple(self._classification_row(r) for r in rows)

    @staticmethod
    def _classification_row(row: ClassificationEntry) -> ClassificationRow:
        return ClassificationRow(
            congress=row.congress,
            session=row.session,
            row_seq=row.row_seq,
            usc_identifier=row.usc_identifier,
            title_num=row.title_num,
            section_raw=row.section_raw,
            is_note=row.is_note,
            action=row.action,
            description_raw=row.description_raw,
            act_name=row.act_name,
            pl_congress=row.pl_congress,
            pl_num=row.pl_num,
            pl_section_raw=row.pl_section_raw or "",
            pl_section_num=row.pl_section_num,
            stat_volume=row.stat_volume,
            stat_page_labels=tuple(row.stat_page_labels or ()),
        )

    def index_coverage(self, law_identifier: str) -> IndexCoverage:
        law, aliases = self._law_aliases_for(law_identifier)
        primary = law.identifier if law is not None else law_identifier
        cited = False
        if aliases:
            cited = self._session.scalar(select(Citation.id).where(Citation.to_law.in_(list(aliases))).limit(1)) is not None
        classified = tables_cover = False
        pl = self._pl_of(law_identifier)
        if pl is not None:
            classified = self._session.scalar(
                select(ClassificationEntry.id).where(ClassificationEntry.pl_congress == pl[0], ClassificationEntry.pl_num == pl[1]).limit(1)
            ) is not None
            tables_cover = any(
                self._classification_file_ref(f).covers(pl[1])
                for f in self._session.scalars(select(ClassificationFile).where(ClassificationFile.congress == pl[0], ClassificationFile.kind == "pl")).all()
            )
        return IndexCoverage(law_identifier=primary, cited=cited, classified=classified, tables_cover=tables_cover)

    def enacted_dates(self, law_identifiers: Sequence[str]) -> dict[str, datetime.date]:
        wanted = [i for i in dict.fromkeys(law_identifiers) if i]
        if not wanted:
            return {}
        rows = self._session.execute(
            select(LawAlias.identifier, Law.enacted).join(Law, Law.id == LawAlias.law_id)
            .where(LawAlias.identifier.in_(wanted), Law.enacted.is_not(None))
        ).all()
        return {identifier: enacted for identifier, enacted in rows}

    def citation_index_status(self) -> CitationIndexStatus:
        rows = int(self._session.scalar(select(func.count()).select_from(Citation)) or 0)
        sections = int(self._session.scalar(select(func.count(func.distinct(Citation.from_identifier)))) or 0)
        titles = int(self._session.scalar(select(func.count(func.distinct(Citation.from_title)))) or 0)
        labels = self._session.execute(
            select(Citation.release_label, func.count()).group_by(Citation.release_label).order_by(func.count().desc(), Citation.release_label)
        ).all()
        # A check that loaded nothing (`--if-changed`, the revision unchanged)
        # has `packages_seen` 0; the load's row is the one with shards.
        newest = select(SourceCheck).where(SourceCheck.collection == "USCODE").order_by(SourceCheck.checked_at.desc(), SourceCheck.id.desc())
        check = self._session.scalars(newest).first()
        load = self._session.scalars(newest.where(SourceCheck.packages_seen > 0)).first()
        return CitationIndexStatus(
            rows=rows,
            citing_sections=sections,
            titles=titles,
            release_labels=tuple((label, int(n)) for label, n in labels),
            loaded_at=load.checked_at if load is not None else None,
            checked_at=check.checked_at if check is not None else None,
            dataset_revision=load.newest_package if load is not None else None,
        )

    @staticmethod
    def _classification_file_ref(f: ClassificationFile) -> ClassificationFileRef:
        return ClassificationFileRef(
            congress=f.congress,
            session=f.session,
            session_label=f.session_label,
            kind=f.kind,
            source_url=f.source_url,
            covered_laws_text=f.covered_laws_text,
            covered_ranges=tuple(f.covered_ranges or ()),
            first_law=f.first_law,
            last_law=f.last_law,
            prepared_date=f.prepared_date,
            stat_volume=f.stat_volume,
            row_count=f.row_count,
            upstream_fetched_at=f.upstream_fetched_at,
            mirrored_at=f.mirrored_at,
        )

    def classification_status(self) -> ClassificationStatus:
        files = self._session.scalars(
            select(ClassificationFile).order_by(ClassificationFile.congress.desc(), ClassificationFile.session.desc())
        ).all()
        rows = int(self._session.scalar(select(func.count()).select_from(ClassificationEntry)) or 0)
        return ClassificationStatus(
            files=tuple(self._classification_file_ref(f) for f in files),
            rows=rows,
            congresses=tuple(sorted({f.congress for f in files})),
            last_check=self.last_classification_check(),
        )

    def last_classification_check(self) -> ClassificationCheckInfo | None:
        row = self._session.scalars(
            select(ClassificationCheck).order_by(ClassificationCheck.checked_at.desc(), ClassificationCheck.id.desc())
        ).first()
        if row is None:
            return None
        return ClassificationCheckInfo(
            checked_at=row.checked_at,
            ok=row.ok,
            source_url=row.source_url,
            congress=row.congress,
            files_seen=row.files_seen,
            files_loaded=row.files_loaded,
            files_unchanged=row.files_unchanged,
            rows_loaded=row.rows_loaded,
            upstream_checked_at=row.upstream_checked_at,
            upstream_covered_text=row.upstream_covered_text,
            error=row.error,
        )

    # ----------------------------------------------------------------- status

    def collection_status(self, collection: str) -> CollectionStatus:
        if collection == "COMPS":
            packages = int(self._session.scalar(select(func.count()).select_from(Comp)) or 0)
            latest = self._session.execute(
                select(Comp.package_id, CompVersion.fetched_at)
                .join(CompVersion, CompVersion.comp_id == Comp.id)
                .order_by(CompVersion.govinfo_last_modified.desc().nullslast(), CompVersion.id.desc())
            ).first()
            units = int(self._session.scalar(select(func.count()).select_from(CompUnit)) or 0)
            return CollectionStatus(
                collection="COMPS",
                packages_loaded=packages,
                latest_package=latest[0] if latest else None,
                latest_loaded_at=latest[1] if latest else None,
                laws=0,
                units=units,
            )
        if collection == "PLAW":
            return self._plaw_status()
        rows = self._session.execute(
            select(Law.source_package, Law.stat_volume, func.count(Law.id), func.max(Law.loaded_at))
            .where(Law.source_collection == collection)
            .group_by(Law.source_package, Law.stat_volume)
            .order_by(Law.stat_volume.desc())
        ).all()
        units = int(
            self._session.scalar(
                select(func.count()).select_from(Unit).join(Law, Law.id == Unit.law_id).where(Law.source_collection == collection)
            )
            or 0
        )
        return CollectionStatus(
            collection=collection,
            packages_loaded=len(rows),
            latest_package=rows[0][0] if rows else None,
            latest_loaded_at=rows[0][3] if rows else None,
            laws=sum(r[2] for r in rows),
            units=units,
            volumes=tuple(sorted(r[1] for r in rows)),
        )

    def _plaw_status(self) -> CollectionStatus:
        """One package per law: the count per congress, the newest law by
        (congress, number), and the volumes the laws print in."""
        by_congress = self._session.execute(
            select(Law.congress, func.count(Law.id))
            .where(Law.source_collection == "PLAW")
            .group_by(Law.congress)
            .order_by(Law.congress)
        ).all()
        latest = self._session.execute(
            select(Law.source_package, Law.loaded_at)
            .where(Law.source_collection == "PLAW")
            .order_by(Law.congress.desc(), Law.number.desc())
            .limit(1)
        ).first()
        units = int(
            self._session.scalar(
                select(func.count()).select_from(Unit).join(Law, Law.id == Unit.law_id).where(Law.source_collection == "PLAW")
            )
            or 0
        )
        volumes = self._session.scalars(
            select(Law.stat_volume).where(Law.source_collection == "PLAW").distinct().order_by(Law.stat_volume)
        ).all()
        laws = sum(int(n) for _, n in by_congress)
        return CollectionStatus(
            collection="PLAW",
            packages_loaded=laws,
            latest_package=latest[0] if latest else None,
            latest_loaded_at=latest[1] if latest else None,
            laws=laws,
            units=units,
            volumes=tuple(int(v) for v in volumes),
            laws_by_congress=tuple((int(c), int(n)) for c, n in by_congress if c is not None),
        )

    def last_source_check(self, collection: str) -> SourceCheckInfo | None:
        row = self._session.scalars(
            select(SourceCheck).where(SourceCheck.collection == collection).order_by(SourceCheck.checked_at.desc(), SourceCheck.id.desc())
        ).first()
        if row is None:
            return None
        return SourceCheckInfo(
            collection=row.collection,
            checked_at=row.checked_at,
            ok=row.ok,
            newest_last_modified=row.newest_last_modified,
            newest_package=row.newest_package,
            packages_seen=row.packages_seen,
            new_packages=tuple(row.new_packages or ()),
            error=row.error,
        )

    def pending_law(self, identifier: str) -> PendingLaw | None:
        row = self._session.get(PendingLawRow, identifier)
        if row is None:
            return None
        return PendingLaw(
            identifier=row.identifier,
            congress=row.congress,
            number=row.number,
            bill_type=row.bill_type,
            bill_number=row.bill_number,
            title=row.title,
            action_date=row.action_date,
            congress_gov_url=row.congress_gov_url,
            checked_at=row.checked_at,
        )

    # --------------------------------------------------------------- congresses

    def _congress_summary(self, congress: int) -> CongressSummary:
        start_yr, end_yr = congress_years(congress)
        first, last, tot, pub, pvt, acts = self._session.execute(
            select(
                func.min(Law.enacted),
                func.max(Law.enacted),
                func.count(Law.id),
                func.count(case((Law.kind == "pl", 1))),
                func.count(case((Law.kind == "pvtl", 1))),
                func.count(case((Law.kind == "act", 1))),
            )
            .where(Law.congress == congress)
        ).one()

        volumes = list(
            self._session.scalars(
                select(Law.stat_volume)
                .where(Law.congress == congress, Law.stat_volume.is_not(None))
                .distinct()
                .order_by(Law.stat_volume)
            ).all()
        )

        section_count = int(
            self._session.scalar(
                select(func.count(Unit.id))
                .select_from(Law)
                .join(Unit, Unit.law_id == Law.id)
                .where(Law.congress == congress, Unit.level == "section")
            )
            or 0
        )

        compilations_count = int(
            self._session.scalar(
                select(func.count(func.distinct(Comp.id)))
                .select_from(Comp)
                .outerjoin(Law, Law.id == Comp.law_id)
                .where(func.coalesce(Comp.law_congress, Law.congress) == congress)
            )
            or 0
        )

        classified_count = int(
            self._session.scalar(
                select(func.count(func.distinct(ClassificationEntry.pl_num)))
                .where(ClassificationEntry.pl_congress == congress, ClassificationEntry.pl_num.is_not(None))
            )
            or 0
        )

        sessions = list(
            self._session.scalars(
                select(ClassificationFile.session)
                .where(ClassificationFile.congress == congress)
                .order_by(ClassificationFile.session)
            ).all()
        )

        cited_laws, citing_sections = self._session.execute(
            select(
                func.count(func.distinct(Citation.to_law)),
                func.count(func.distinct(Citation.from_identifier)),
            )
            .select_from(LawAlias)
            .join(Citation, Citation.to_law == LawAlias.identifier)
            .join(Law, Law.id == LawAlias.law_id)
            .where(Law.congress == congress)
        ).one()

        pending_count = int(
            self._session.scalar(
                select(func.count(PendingLawRow.identifier))
                .where(PendingLawRow.congress == congress)
            )
            or 0
        )

        return CongressSummary(
            congress=congress,
            ordinal=congress_ordinal(congress),
            start_year=start_yr,
            end_year=end_yr,
            first_enacted=first,
            last_enacted=last,
            total_laws=int(tot or 0),
            public_laws=int(pub or 0),
            private_laws=int(pvt or 0),
            chapter_acts=int(acts or 0),
            volumes=tuple(int(v) for v in volumes if v is not None),
            section_count=section_count,
            compilations_count=compilations_count,
            classified_laws_count=classified_count,
            classification_sessions=tuple(int(s) for s in sessions),
            cited_laws_count=int(cited_laws or 0),
            citing_sections_count=int(citing_sections or 0),
            pending_laws_count=pending_count,
        )

    def congresses_overview(self) -> CongressesOverview:
        # 1. Law aggregates by congress
        law_stats: dict[int, tuple[datetime.date | None, datetime.date | None, int, int, int, int]] = {}
        for c, first, last, tot, pub, pvt, acts in self._session.execute(
            select(
                Law.congress,
                func.min(Law.enacted),
                func.max(Law.enacted),
                func.count(Law.id),
                func.count(case((Law.kind == "pl", 1))),
                func.count(case((Law.kind == "pvtl", 1))),
                func.count(case((Law.kind == "act", 1))),
            )
            .where(Law.congress.is_not(None))
            .group_by(Law.congress)
        ):
            if c is not None:
                law_stats[int(c)] = (first, last, int(tot), int(pub), int(pvt), int(acts))

        # 2. Volumes by congress
        volumes_by_congress: dict[int, set[int]] = {}
        for c, v in self._session.execute(
            select(Law.congress, Law.stat_volume)
            .where(Law.congress.is_not(None), Law.stat_volume.is_not(None))
            .distinct()
        ):
            if c is not None and v is not None:
                volumes_by_congress.setdefault(int(c), set()).add(int(v))

        # 3. Section counts by congress
        sections_by_congress: dict[int, int] = {}
        for c, cnt in self._session.execute(
            select(Law.congress, func.count(Unit.id))
            .join(Unit, Unit.law_id == Law.id)
            .where(Law.congress.is_not(None), Unit.level == "section")
            .group_by(Law.congress)
        ):
            if c is not None:
                sections_by_congress[int(c)] = int(cnt)

        # 4. Compilations count by congress
        comp_counts: dict[int, int] = {}
        for c, cnt in self._session.execute(
            select(
                func.coalesce(Comp.law_congress, Law.congress).label("c"),
                func.count(func.distinct(Comp.id)),
            )
            .outerjoin(Law, Law.id == Comp.law_id)
            .where(func.coalesce(Comp.law_congress, Law.congress).is_not(None))
            .group_by("c")
        ):
            if c is not None:
                comp_counts[int(c)] = int(cnt)

        # 5. Classified laws count by congress
        classified_counts: dict[int, int] = {}
        for c, cnt in self._session.execute(
            select(
                ClassificationEntry.pl_congress,
                func.count(func.distinct(ClassificationEntry.pl_num)),
            )
            .where(ClassificationEntry.pl_congress.is_not(None), ClassificationEntry.pl_num.is_not(None))
            .group_by(ClassificationEntry.pl_congress)
        ):
            if c is not None:
                classified_counts[int(c)] = int(cnt)

        # 6. Classification sessions by congress
        sessions_by_congress: dict[int, list[int]] = {}
        for c, s in self._session.execute(
            select(ClassificationFile.congress, ClassificationFile.session)
            .order_by(ClassificationFile.congress, ClassificationFile.session)
        ):
            sessions_by_congress.setdefault(int(c), []).append(int(s))

        # 7. Citations: cited_laws_count and citing_sections_count
        cited_laws_by_congress: dict[int, int] = {}
        citing_sections_by_congress: dict[int, int] = {}
        for c, law_cnt, sec_cnt in self._session.execute(
            select(
                Law.congress,
                func.count(func.distinct(Citation.to_law)),
                func.count(func.distinct(Citation.from_identifier)),
            )
            .join(LawAlias, LawAlias.identifier == Citation.to_law)
            .join(Law, Law.id == LawAlias.law_id)
            .where(Law.congress.is_not(None))
            .group_by(Law.congress)
        ):
            if c is not None:
                cited_laws_by_congress[int(c)] = int(law_cnt)
                citing_sections_by_congress[int(c)] = int(sec_cnt)

        # 8. Pending laws by congress
        pending_by_congress: dict[int, int] = {}
        for c, cnt in self._session.execute(
            select(PendingLawRow.congress, func.count(PendingLawRow.identifier))
            .group_by(PendingLawRow.congress)
        ):
            if c is not None:
                pending_by_congress[int(c)] = int(cnt)

        all_congresses = sorted(law_stats.keys() | pending_by_congress.keys())
        summaries: list[CongressSummary] = []
        for c in all_congresses:
            first_enacted, last_enacted, tot, pub, pvt, acts = law_stats.get(c, (None, None, 0, 0, 0, 0))
            start_yr, end_yr = congress_years(c)
            summaries.append(
                CongressSummary(
                    congress=c,
                    ordinal=congress_ordinal(c),
                    start_year=start_yr,
                    end_year=end_yr,
                    first_enacted=first_enacted,
                    last_enacted=last_enacted,
                    total_laws=tot,
                    public_laws=pub,
                    private_laws=pvt,
                    chapter_acts=acts,
                    volumes=tuple(sorted(volumes_by_congress.get(c, ()))),
                    section_count=sections_by_congress.get(c, 0),
                    compilations_count=comp_counts.get(c, 0),
                    classified_laws_count=classified_counts.get(c, 0),
                    classification_sessions=tuple(sessions_by_congress.get(c, ())),
                    cited_laws_count=cited_laws_by_congress.get(c, 0),
                    citing_sections_count=citing_sections_by_congress.get(c, 0),
                    pending_laws_count=pending_by_congress.get(c, 0),
                )
            )

        return CongressesOverview(
            total_congresses=len(summaries),
            total_laws=sum(s.total_laws for s in summaries),
            total_public_laws=sum(s.public_laws for s in summaries),
            total_private_laws=sum(s.private_laws for s in summaries),
            total_chapter_acts=sum(s.chapter_acts for s in summaries),
            total_sections=sum(s.section_count for s in summaries),
            total_compilations=sum(s.compilations_count for s in summaries),
            congresses=tuple(summaries),
        )

    def congress_detail(
        self,
        congress: int,
        *,
        kind: str | None = None,
        has_comp: bool = False,
        cited: bool = False,
        q: str | None = None,
        sort: str = "sequence",
        limit: int = 100,
        offset: int = 0,
    ) -> CongressDetail | None:
        has_laws = self._session.scalar(select(Law.id).where(Law.congress == congress).limit(1)) is not None
        has_pending = self._session.scalar(select(PendingLawRow.identifier).where(PendingLawRow.congress == congress).limit(1)) is not None
        if not has_laws and not has_pending:
            return None

        summary = self._congress_summary(congress)
        pending_rows = list(
            self._session.scalars(
                select(PendingLawRow).where(PendingLawRow.congress == congress).order_by(PendingLawRow.number)
            ).all()
        )
        pending_laws = tuple(
            PendingLaw(
                identifier=row.identifier,
                congress=row.congress,
                number=row.number,
                bill_type=row.bill_type,
                bill_number=row.bill_number,
                title=row.title,
                action_date=row.action_date,
                congress_gov_url=row.congress_gov_url,
                checked_at=row.checked_at,
            )
            for row in pending_rows
        )

        base_stmt = select(Law).where(Law.congress == congress)
        if kind in ("pl", "pvtl", "act"):
            base_stmt = base_stmt.where(Law.kind == kind)

        if has_comp:
            comp_match = or_(
                Comp.law_id == Law.id,
                and_(
                    Comp.law_congress == Law.congress,
                    or_(
                        Comp.law_number == Law.number,
                        Comp.law_number == Law.chapter,
                    ),
                ),
            )
            base_stmt = base_stmt.where(select(Comp.id).where(comp_match).exists())

        if cited:
            cit_subq = (
                select(Citation.id)
                .select_from(Citation)
                .join(LawAlias, LawAlias.identifier == Citation.to_law)
                .where(LawAlias.law_id == Law.id)
            )
            class_match = and_(
                ClassificationEntry.pl_congress == Law.congress,
                ClassificationEntry.pl_num == Law.number,
            )
            base_stmt = base_stmt.where(
                or_(
                    cit_subq.exists(),
                    select(ClassificationEntry.id).where(class_match).exists(),
                )
            )

        if q and q.strip():
            needle = f"%{q.strip()}%"
            base_stmt = base_stmt.where(
                or_(
                    Law.official_title.ilike(needle),
                    cast(Law.short_titles, Text).ilike(needle),
                    Law.citation.ilike(needle),
                    Law.identifier.ilike(needle),
                )
            )

        if sort == "date":
            base_stmt = base_stmt.order_by(
                Law.enacted.asc().nullslast(),
                Law.seq_in_volume.asc().nullslast(),
                Law.id.asc(),
            )
        elif sort == "sections":
            sec_subq = select(func.count(Unit.id)).where(Unit.law_id == Law.id, Unit.level == "section").scalar_subquery()
            base_stmt = base_stmt.order_by(
                sec_subq.desc(),
                Law.seq_in_volume.asc().nullslast(),
                Law.id.asc(),
            )
        else:  # sequence
            base_stmt = base_stmt.order_by(
                Law.stat_volume.asc().nullslast(),
                Law.seq_in_volume.asc().nullslast(),
                Law.number.asc().nullslast(),
                Law.chapter.asc().nullslast(),
                Law.id.asc(),
            )

        total = int(self._session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0)
        law_rows = list(self._session.scalars(base_stmt.offset(offset).limit(limit)).all())

        if not law_rows:
            return CongressDetail(
                summary=summary,
                laws=(),
                pending_laws=pending_laws,
                total=total,
                limit=limit,
                offset=offset,
            )

        law_ids = [law.id for law in law_rows]
        numbers = [law.number for law in law_rows if law.number is not None]
        chapters = [law.chapter for law in law_rows if law.chapter is not None]

        # 1. section counts
        sec_counts: dict[int, int] = {}
        for lid, cnt in self._session.execute(
            select(Unit.law_id, func.count(Unit.id))
            .where(Unit.law_id.in_(law_ids), Unit.level == "section")
            .group_by(Unit.law_id)
        ):
            sec_counts[int(lid)] = int(cnt)

        # 2. compilations
        comp_clauses = [Comp.law_id.in_(law_ids)]
        if numbers or chapters:
            num_clauses = []
            if numbers:
                num_clauses.append(Comp.law_number.in_(numbers))
            if chapters:
                num_clauses.append(Comp.law_number.in_(chapters))
            comp_clauses.append(
                and_(Comp.law_congress == congress, or_(*num_clauses))
            )
        matching_comps = list(
            self._session.scalars(
                select(Comp).where(or_(*comp_clauses)).order_by(Comp.file_id)
            ).all()
        )
        comps_by_law_id: dict[int, list[CompRef]] = {}
        for comp in matching_comps:
            cref = self._comp_ref(comp)
            for law in law_rows:
                is_match = False
                if comp.law_id == law.id:
                    is_match = True
                elif comp.law_congress == law.congress:
                    if law.number is not None and comp.law_number == law.number:
                        is_match = True
                    elif law.chapter is not None and comp.law_number == law.chapter:
                        is_match = True
                if is_match:
                    comps_by_law_id.setdefault(law.id, []).append(cref)

        # 3. classifications
        class_counts: dict[int, int] = {}
        class_titles: dict[int, set[str]] = {}
        if numbers:
            for pnum, cnt in self._session.execute(
                select(
                    ClassificationEntry.pl_num,
                    func.count(ClassificationEntry.id),
                )
                .where(
                    ClassificationEntry.pl_congress == congress,
                    ClassificationEntry.pl_num.in_(numbers),
                )
                .group_by(ClassificationEntry.pl_num)
            ):
                if pnum is not None:
                    class_counts[int(pnum)] = int(cnt)

            for pnum, tnum in self._session.execute(
                select(
                    ClassificationEntry.pl_num,
                    ClassificationEntry.title_num,
                )
                .where(
                    ClassificationEntry.pl_congress == congress,
                    ClassificationEntry.pl_num.in_(numbers),
                    ClassificationEntry.title_num.is_not(None),
                )
                .distinct()
            ):
                if pnum is not None and tnum:
                    class_titles.setdefault(int(pnum), set()).add(str(tnum))

        # 4. citations
        cit_sec_counts: dict[int, int] = {}
        cit_titles: dict[int, set[str]] = {}
        for lid, cnt in self._session.execute(
            select(
                LawAlias.law_id,
                func.count(func.distinct(Citation.from_identifier)),
            )
            .join(LawAlias, LawAlias.identifier == Citation.to_law)
            .where(LawAlias.law_id.in_(law_ids))
            .group_by(LawAlias.law_id)
        ):
            cit_sec_counts[int(lid)] = int(cnt)

        for lid, tnum in self._session.execute(
            select(
                LawAlias.law_id,
                Citation.from_title,
            )
            .join(LawAlias, LawAlias.identifier == Citation.to_law)
            .where(LawAlias.law_id.in_(law_ids), Citation.from_title.is_not(None))
            .distinct()
        ):
            if lid is not None and tnum:
                cit_titles.setdefault(int(lid), set()).add(str(tnum))

        def _sort_title(t: str) -> tuple[int, str]:
            return (int(t), t) if t.isdigit() else (10**6, t)

        law_items: list[CongressLawItem] = []
        for law in law_rows:
            all_titles = set(cit_titles.get(law.id, set()))
            if law.number is not None:
                all_titles |= class_titles.get(law.number, set())
            sorted_titles = tuple(sorted(all_titles, key=_sort_title))

            law_items.append(
                CongressLawItem(
                    identifier=law.identifier,
                    kind=law.kind,
                    congress=law.congress,
                    number=law.number,
                    chapter=law.chapter,
                    label=law_label(law.kind, law.congress, law.number, law.chapter, law.enacted),
                    citation=law.citation,
                    volume=law.stat_volume,
                    page_first=law.stat_page_first,
                    enacted=law.enacted,
                    official_title=law.official_title,
                    short_titles=tuple(law.short_titles or ()),
                    section_count=sec_counts.get(law.id, 0),
                    compilations=tuple(comps_by_law_id.get(law.id, ())),
                    usc_classifications_count=class_counts.get(law.number, 0) if law.number is not None else 0,
                    usc_titles=sorted_titles,
                    usc_citing_sections_count=cit_sec_counts.get(law.id, 0),
                )
            )

        return CongressDetail(
            summary=summary,
            laws=tuple(law_items),
            pending_laws=pending_laws,
            total=total,
            limit=limit,
            offset=offset,
        )

