"""Write parsed volumes into the database and report what was written.

Ingest sits on the other side of the `Repository` boundary and writes `db/`
models directly (the US Code site's rule). A re-load of a volume replaces
every law it holds by primary identifier, so the loader is idempotent per
volume.
"""

from __future__ import annotations

import datetime
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from db.models import Comp, Law, LawAlias, SourceCheck, StatPage, Unit
from ingest.hub import sha256_of
from ingest.statute import (
    IDENTIFIER_RULES_VERSION,
    TEXT_PROVENANCE,
    LawRecord,
    VolumeParse,
    iter_volume,
)

COMMIT_EVERY = 50

#: Which source's copy of a law wins when both hold it (ADR-0011). A load from
#: a lower-ranked collection leaves a stored law of a higher-ranked one alone.
SOURCE_PRECEDENCE: dict[str, int] = {"STATUTE": 1, "PLAW": 2}


@dataclass(slots=True)
class WriteOutcome:
    """What `_write_law` did with one record."""

    action: str
    """`new` | `replaced` | `kept`: `kept` means a copy from a collection that
    outranks this record's was stored already and nothing was written."""
    replaced_from: str | None = None
    """The collection of the copy that was replaced (`STATUTE`, `PLAW`)."""
    replaced_xml: str | None = None
    """That copy's whole-law XML, for the identifier comparison a PLAW load
    writes (`ingest/plaw.py`)."""
    aliases_written: int = 0
    aliases_dropped: int = 0

    @property
    def replaced(self) -> int:
        return 1 if self.action == "replaced" else 0


@dataclass(slots=True)
class VolumeLoadReport:
    volume: int
    package: str
    source_file: str
    source_sha256: str
    loaded_at: str
    seconds: float = 0.0
    components: int = 0
    laws_loaded: int = 0
    laws_by_kind: dict[str, int] = field(default_factory=dict)
    laws_replaced: int = 0
    laws_kept_from_plaw: list[str] = field(default_factory=list)
    """Laws of the volume left alone because a PLAW-derived copy is stored
    (ADR-0011): the bulk-data file outranks the volume file."""
    units: int = 0
    units_by_level: dict[str, int] = field(default_factory=dict)
    sections: int = 0
    sections_in_quoted_content_skipped: int = 0
    duplicate_section_identifiers: int = 0
    aliases: int = 0
    aliases_dropped_as_taken: int = 0
    stat_pages: int = 0
    number_conflicts: list[dict] = field(default_factory=list)
    """Laws whose law number is also claimed by another law of the volume
    (`ingest/numbering.py`): stored under the chapter form, or dropped."""
    numbers_out_of_sequence: list[dict] = field(default_factory=list)
    repeated_laws: list[dict] = field(default_factory=list)
    """Laws whose primary identifier an earlier law of the same volume already
    took after numbering: the same act printed twice. The first is stored."""
    skipped_components: dict[str, int] = field(default_factory=dict)
    merged_components: int = 0
    """Components that held more than one law."""
    unidentified: list[dict] = field(default_factory=list)
    warnings: dict[str, int] = field(default_factory=dict)
    identifier_rules: str = IDENTIFIER_RULES_VERSION
    first_law: str | None = None
    last_law: str | None = None


def recorded_volume_sha(session: Session, volume: int) -> str | None:
    """The sha256 of the file the last load of `STATUTE-{volume}` read, from
    its `source_checks` row; None when the volume was never loaded or the row
    predates the column."""
    return session.scalar(
        select(SourceCheck.source_sha256)
        .where(SourceCheck.collection == "STATUTE", SourceCheck.newest_package == f"STATUTE-{volume}")
        .order_by(SourceCheck.checked_at.desc(), SourceCheck.id.desc())
        .limit(1)
    )


def record_source_check(
    session: Session,
    collection: str,
    *,
    ok: bool,
    packages_seen: int | None,
    new_packages: list[str],
    newest_package: str | None = None,
    error: str | None = None,
    now: datetime.datetime | None = None,
) -> SourceCheck:
    """One row for a check that loaded nothing by itself: a Hub listing
    (`fetch-statute --if-changed`), a `statute --changed-only` run that found
    every file unchanged, a `citations --if-changed` run that found the
    revision unchanged. `newest_package` stays null unless the check names a
    package it holds, because `law_sources` reads a `STATUTE-{n}` there as the
    volume having been loaded."""
    row = SourceCheck(
        collection=collection,
        checked_at=now or datetime.datetime.now(datetime.timezone.utc),
        ok=ok,
        newest_last_modified=None,
        newest_package=newest_package,
        packages_seen=packages_seen,
        new_packages=new_packages,
        error=error,
    )
    session.add(row)
    session.commit()
    return row


def load_volume(session: Session, path: Path, *, record_check: bool = True) -> VolumeLoadReport:
    path = Path(path)
    started = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    header: VolumeParse | None = None
    report: VolumeLoadReport | None = None
    kinds: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    pending = 0
    seen_primaries: set[str] = set()

    from ingest.numbering import plan_numbering
    from ingest.statute import iter_claims

    plan = plan_numbering(list(iter_claims(path)))

    for item in iter_volume(path, plan):
        if isinstance(item, VolumeParse):
            header = item
            report = VolumeLoadReport(
                volume=item.volume,
                package=item.package,
                source_file=str(path),
                source_sha256=sha256_of(path),
                loaded_at=now.isoformat(),
            )
            continue
        assert header is not None and report is not None
        law: LawRecord = item
        if law.identifier in seen_primaries:
            # The same act printed twice in the volume file (vol 12 repeats 19
            # private acts); the first printing is the one stored.
            report.repeated_laws.append({"seq": law.seq_in_volume, "identifier": law.identifier, "citation": law.citation})
            continue
        seen_primaries.add(law.identifier)
        outcome = _write_law(session, law, now)
        if outcome.action == "kept":
            report.laws_kept_from_plaw.append(law.identifier)
            continue
        report.laws_loaded += 1
        report.laws_replaced += outcome.replaced
        report.aliases += outcome.aliases_written
        report.aliases_dropped_as_taken += outcome.aliases_dropped
        report.units += len(law.units)
        report.sections += len(law.sections)
        report.stat_pages += len(law.page_units)
        report.duplicate_section_identifiers += sum(
            1 for u in law.units if u.level == "section" and u.occurrence > 1
        )
        kinds[law.kind] += 1
        for unit in law.units:
            levels[unit.level] += 1
        for warning in law.warnings:
            key = warning.split(" ", 1)[-1] if warning.startswith("/") else warning
            warnings[key] += 1
        report.first_law = report.first_law or law.identifier
        report.last_law = law.identifier
        pending += 1
        if pending >= COMMIT_EVERY:
            session.commit()
            pending = 0

    assert header is not None and report is not None
    report.components = header.components
    report.laws_by_kind = dict(kinds)
    report.units_by_level = dict(levels)
    report.sections_in_quoted_content_skipped = header.sections_in_quoted_content
    report.skipped_components = header.skipped_by_reason
    report.merged_components = header.merged_components
    report.unidentified.extend(
        {"seq": s.seq, "doc_type": s.doc_type, "doc_number": s.doc_number}
        for s in header.skipped
        if s.reason == "unidentified law"
    )
    report.number_conflicts = [
        {"seq": d.seq, "action": d.action, "claimed": d.claimed, "kept_as": d.kept_as,
         "citation": d.citation, "title": d.title, "reason": d.reason}
        for d in sorted(plan.decisions.values(), key=lambda d: d.seq)
    ]
    report.numbers_out_of_sequence = plan.out_of_sequence
    report.warnings = dict(warnings.most_common())
    if record_check:
        session.add(
            SourceCheck(
                collection="STATUTE",
                checked_at=now,
                ok=True,
                newest_last_modified=None,
                newest_package=report.package,
                packages_seen=1,
                new_packages=[report.package],
                error=None,
                source_sha256=report.source_sha256,
            )
        )
    session.commit()
    report.seconds = round(time.monotonic() - started, 1)
    return report


def _write_law(session: Session, law: LawRecord, now: datetime.datetime) -> WriteOutcome:
    """Replace any earlier copy of the law, then insert it.

    Precedence (ADR-0011): a stored copy from a collection that outranks the
    record's (`SOURCE_PRECEDENCE`) is kept and nothing is written. Otherwise
    the old copy, its units, aliases and pages go, and compilations that were
    linked to it are re-pointed at the new row.
    """
    outcome = WriteOutcome(action="new")
    rank = SOURCE_PRECEDENCE.get(law.source_collection, 0)
    existing = session.scalars(select(Law).where(Law.identifier == law.identifier)).all()
    comp_ids: list[int] = []
    for old in existing:
        if SOURCE_PRECEDENCE.get(old.source_collection, 0) > rank:
            outcome.action = "kept"
            outcome.replaced_from = old.source_collection
            return outcome
        outcome.action = "replaced"
        outcome.replaced_from = old.source_collection
        outcome.replaced_xml = old.xml
        comp_ids.extend(session.scalars(select(Comp.id).where(Comp.law_id == old.id)).all())
        session.execute(delete(StatPage).where(StatPage.law_id == old.id))
        session.delete(old)
    if existing:
        session.flush()

    row = Law(
        identifier=law.identifier,
        kind=law.kind,
        congress=law.congress,
        number=law.number,
        chapter=law.chapter,
        enacted=law.enacted,
        doc_type=law.doc_type,
        official_title=law.official_title,
        short_titles=law.short_titles,
        stat_volume=law.stat_volume,
        stat_page_first=law.stat_page_first,
        stat_page_last=law.stat_page_last,
        citation=law.citation,
        source_collection=law.source_collection,
        source_package=law.source_package,
        source_granule=None,
        seq_in_volume=law.seq_in_volume,
        provenance_text=TEXT_PROVENANCE,
        provenance_identifiers=law.provenance_identifiers,
        xml=law.xml,
        content_hash=law.content_hash,
        loaded_at=now,
    )
    session.add(row)
    session.flush()
    if comp_ids:
        session.execute(update(Comp).where(Comp.id.in_(comp_ids)).values(law_id=row.id))

    for alias in law.aliases:
        taken = session.get(LawAlias, alias)
        if taken is not None:
            if taken.law_id == row.id:
                continue
            outcome.aliases_dropped += 1
            law.warnings.append(f"alias {alias} already names another law")
            continue
        session.add(LawAlias(identifier=alias, law_id=row.id, is_primary=(alias == law.identifier)))
        outcome.aliases_written += 1

    session.add_all(
        Unit(
            law_id=row.id,
            identifier=u.identifier,
            occurrence=u.occurrence,
            parent_identifier=u.parent_identifier,
            level=u.level,
            num=u.num,
            heading=u.heading,
            section_num=u.section_num,
            seq=u.seq,
            depth=u.depth,
            ancestors=u.ancestors,
            xml=u.xml,
            text=u.text,
            content_hash=u.content_hash,
            first_page=u.first_page,
            pages=u.pages,
        )
        for u in law.units
    )
    session.add_all(
        StatPage(
            volume=law.stat_volume,
            page=page,
            law_id=row.id,
            starts_here=(page == law.stat_page_first),
            unit_identifier=unit_identifier,
        )
        for page, unit_identifier in law.page_units.items()
    )
    session.flush()
    return outcome


def write_report(report: VolumeLoadReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"statute-{report.volume}.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n")
    return target
