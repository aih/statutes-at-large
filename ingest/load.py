"""Write parsed volumes into the database and report what was written.

Ingest sits on the other side of the `Repository` boundary and writes `db/`
models directly (the US Code site's rule). A re-load of a volume replaces
every law it holds by primary identifier, so the loader is idempotent per
volume.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models import Law, LawAlias, SourceCheck, StatPage, Unit
from ingest.statute import (
    IDENTIFIER_RULES_VERSION,
    TEXT_PROVENANCE,
    LawRecord,
    VolumeParse,
    iter_volume,
)

COMMIT_EVERY = 50


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
    skipped_components: dict[str, int] = field(default_factory=dict)
    unidentified: list[dict] = field(default_factory=list)
    warnings: dict[str, int] = field(default_factory=dict)
    identifier_rules: str = IDENTIFIER_RULES_VERSION
    first_law: str | None = None
    last_law: str | None = None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            report.unidentified.append({"seq": law.seq_in_volume, "reason": "primary identifier repeated after numbering", "identifier": law.identifier, "citation": law.citation})
            continue
        seen_primaries.add(law.identifier)
        replaced, alias_count, dropped = _write_law(session, law, now)
        report.laws_loaded += 1
        report.laws_replaced += replaced
        report.aliases += alias_count
        report.aliases_dropped_as_taken += dropped
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
            )
        )
    session.commit()
    report.seconds = round(time.monotonic() - started, 1)
    return report


def _write_law(session: Session, law: LawRecord, now: datetime.datetime) -> tuple[int, int, int]:
    """Replace any earlier copy of the law, then insert it. Returns
    (replaced, aliases written, aliases dropped because another law holds them)."""
    replaced = 0
    existing = session.scalars(select(Law).where(Law.identifier == law.identifier)).all()
    for old in existing:
        session.execute(delete(StatPage).where(StatPage.law_id == old.id))
        session.delete(old)
        replaced += 1
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
        source_collection="STATUTE",
        source_package=law.source_package,
        source_granule=None,
        seq_in_volume=law.seq_in_volume,
        provenance_text=TEXT_PROVENANCE,
        provenance_identifiers=IDENTIFIER_RULES_VERSION,
        xml=law.xml,
        content_hash=law.content_hash,
        loaded_at=now,
    )
    session.add(row)
    session.flush()

    written = dropped = 0
    for alias in law.aliases:
        taken = session.get(LawAlias, alias)
        if taken is not None:
            if taken.law_id == row.id:
                continue
            dropped += 1
            law.warnings.append(f"alias {alias} already names another law")
            continue
        session.add(LawAlias(identifier=alias, law_id=row.id, is_primary=(alias == law.identifier)))
        written += 1

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
    return replaced, written, dropped


def write_report(report: VolumeLoadReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"statute-{report.volume}.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n")
    return target
