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

import datetime
from collections.abc import Sequence

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session

from db.models import Comp, CompUnit, CompVersion, Law, LawAlias, SourceCheck, StatPage, Unit
from storage.identifiers import ParsedIdentifier, parse_identifier
from storage.repository import (
    CollectionStatus,
    CompCounterpart,
    CompRef,
    CompUnitResult,
    CompVersionRef,
    LabelInfo,
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
from uslmtext import fragment_by_identifier, plain_text, serialize


class PostgresRepository:
    """`Repository` over the stage-1 schema."""

    def __init__(self, session: Session):
        self._session = session

    # ---------------------------------------------------------------- enacted

    def get_unit(self, identifier: str) -> UnitResult | None:
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

    def stat_page(self, volume: int, page: str) -> StatPageResult | None:
        rows = self._session.execute(
            select(StatPage, Law)
            .join(Law, Law.id == StatPage.law_id)
            .where(StatPage.volume == volume, StatPage.page == page)
            .order_by(StatPage.starts_here.desc(), Law.seq_in_volume)
        ).all()
        if not rows:
            return None
        return StatPageResult(
            volume=volume,
            page=page,
            documents=tuple(
                StatPageDocument(
                    law=self._law_ref(law),
                    starts_here=sp.starts_here,
                    unit_identifier=sp.unit_identifier,
                )
                for sp, law in rows
            ),
        )

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
                return self._unit_result(law, unit, requested, base, provision_path=requested if base == "exact" else candidate + "/" + "/".join(rest))
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
            xml=law.xml,
            text=plain_text(fragment_by_identifier(law.xml, "") or _root(law.xml)),
            content_hash=law.content_hash,
            ancestors=(),
            children=self._children(law, None),
            pages=tuple(PageRef(law.stat_volume, p) for p in pages),
            provision=None,
        )

    def _unit_result(self, law: Law, unit: Unit, requested: str, resolution: str, *, provision_path: str | None) -> UnitResult:
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
            # A hierarchy node: its XML is the node cut from the law's XML.
            fragment = fragment_by_identifier(law.xml, unit.identifier)
            xml = serialize(fragment) if fragment is not None else ""
            text = plain_text(fragment) if fragment is not None else ""
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

    def get_comp_unit(self, identifier: str, *, through: str | None = None) -> CompUnitResult | None:
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
            # The compilation itself. Prefer the whole-act file over a per-title one.
            version = next((v for v in versions if v.comp.partial_of is None), versions[0])
            return self._comp_root_result(version, requested, "exact", pinned)
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
        version = next((v for v in versions if v.comp.partial_of is None), versions[0])
        return self._comp_root_result(version, requested, "prefix", pinned)

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

    def _comp_root_result(self, version: CompVersion, requested: str, resolution: str, pinned: bool) -> CompUnitResult:
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
            xml=version.xml,
            text=plain_text(_root(version.xml)),
            content_hash=version.content_hash,
            ancestors=(),
            children=self._comp_children(version.id, None),
            usc_refs=(),
            provision=None,
        )

    def _comp_unit_result(self, unit: CompUnit, requested: str, resolution: str, pinned: bool, *, provision_path: str | None) -> CompUnitResult:
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
            fragment = fragment_by_identifier(version.xml, unit.identifier)
            xml = serialize(fragment) if fragment is not None else ""
            text = plain_text(fragment) if fragment is not None else ""
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


def _root(xml: str):
    from lxml import etree

    return etree.fromstring(xml.encode("utf-8"))
