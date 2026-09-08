"""`currency.amended` for an enacted unit, decided from the indexes (design
section 4).

Three kinds of evidence, each a `Repository` call:

  * `source_credit` — a US Code section whose source credit cites the unit
    names a law later than this one (`source_credit_evidence`).
  * `classification` — a classification-table row of a later public law
    classifies to a US Code section this unit was classified to, with an
    action other than `new` (`classification_amendments`).
  * `compilation` — a compiled counterpart is current through a later law
    and, for a section, its text differs from the enacted text after
    whitespace is collapsed (`compiled_counterparts`, `get_comp_unit`).

"Later" compares `(congress, number)` when the candidate and the law both
carry them, else enactment dates; a candidate with neither, or one that is
the law itself under any alias, does not count. `enacted_dates` fills the
dates of candidates the store holds.

`known_amended` when any evidence fires; `latest` is the newest law among
the ones that fired. Otherwise `no_record` when `index_coverage` says the
indexes know the law and it is not a private law, else `unknown`. A hierarchy
node (title, division, …) is judged on the law-wide evidence.

`labels` (up to 100 identifiers) uses the same rules without the text
comparison: at label time compilation evidence is "current through a later
law" alone, and `get_comp_unit` is not called.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from storage import (
    ClassificationRow,
    CompCounterpart,
    LabelInfo,
    LawRef,
    Repository,
    SourceCreditEvidence,
    UnitResult,
    law_label_of_identifier,
)

EVIDENCE_KINDS = ("source_credit", "classification", "compilation")
"""The order `evidence` lists them in."""

CODIFIED_CAP = 20
"""How many US Code sections from the index the codified alternative names."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """A law the evidence named: what "later than this law" is decided on."""

    identifier: str
    kind: str
    congress: int | None
    number: int | None
    date: datetime.date | None

    @classmethod
    def of_law(cls, law: LawRef) -> Candidate:
        return cls(law.identifier, law.kind, law.congress, law.number, law.enacted)

    @classmethod
    def of_pl(cls, congress: int, number: int, date: datetime.date | None) -> Candidate:
        return cls(f"/us/pl/{congress}/{number}", "pl", congress, number, date)

    @property
    def pl(self) -> str | None:
        """`118-67` for a public law, None for an act or a private law."""
        if self.kind == "pl" and self.congress is not None and self.number is not None:
            return f"{self.congress}-{self.number}"
        return None

    @property
    def label(self) -> str:
        return law_label_of_identifier(self.identifier)


@dataclass(frozen=True, slots=True)
class Amended:
    """The decision: the wire shape of `currency.amended`, plus the citing
    US Code sections the codified alternative reuses."""

    status: str
    """`known_amended` | `no_record` | `unknown`."""
    latest: Candidate | None
    evidence: tuple[str, ...]
    citing: tuple[str, ...]
    """US Code sections whose source credits cite the unit, deduplicated, in
    identifier order, at most `CODIFIED_CAP`."""


# ------------------------------------------------------------------ ordering


def later(candidate: Candidate, reference: Candidate) -> bool:
    """True when `candidate` is a later law than `reference`.

    `(congress, number)` when both carry them and the kinds agree or the
    congresses differ (a public and a private law of one congress are
    numbered in separate sequences); else the dates; else False.
    """
    if candidate.identifier == reference.identifier:
        return False
    numbered = (
        candidate.congress is not None and candidate.number is not None
        and reference.congress is not None and reference.number is not None
    )
    if numbered and (candidate.kind == reference.kind or candidate.congress != reference.congress):
        return (candidate.congress, candidate.number) > (reference.congress, reference.number)
    if candidate.date is not None and reference.date is not None:
        return candidate.date > reference.date
    return False


def newest(candidates: Iterable[Candidate]) -> Candidate | None:
    """The candidate no other is later than; the first one wins a tie or an
    incomparable pair."""
    best: Candidate | None = None
    for candidate in candidates:
        if best is None or later(candidate, best):
            best = candidate
    return best


def _fires(candidate: Candidate, law: LawRef) -> bool:
    if candidate.identifier == law.identifier or candidate.identifier in law.aliases:
        return False
    return later(candidate, Candidate.of_law(law))


# ------------------------------------------------------------------ evidence


def _credit_candidates(credits: Sequence[SourceCreditEvidence]) -> list[Candidate]:
    out: list[Candidate] = []
    for credit in credits:
        for cite in credit.laws:
            out.append(Candidate(cite.identifier, cite.kind, cite.congress, cite.number, cite.date))
    return out


def _classification_candidates(rows: Sequence[ClassificationRow]) -> list[Candidate]:
    return [
        Candidate.of_pl(row.pl_congress, row.pl_num, None)
        for row in rows
        if row.action != "new" and row.pl_congress is not None and row.pl_num is not None
    ]


def _parse_pl(label: str | None) -> tuple[int, int] | None:
    """`118-67` → (118, 67)."""
    if not label:
        return None
    congress, _, number = label.partition("-")
    try:
        return int(congress), int(number)
    except ValueError:
        return None


def _normalized(text: str | None) -> str:
    return " ".join((text or "").split())


def _compilation_candidates(
    repository: Repository,
    counterparts: Sequence[CompCounterpart],
    *,
    section_text: str | None,
    compare_text: bool,
) -> list[Candidate]:
    """One candidate per counterpart current through a public law. For a
    section with `compare_text`, only when the compiled text differs from
    the enacted text; a counterpart that cannot be read is skipped."""
    out: list[Candidate] = []
    for counterpart in counterparts:
        pl = _parse_pl(counterpart.version.current_through_pl)
        if pl is None:
            continue
        if compare_text and section_text is not None and counterpart.level == "section":
            compiled = repository.get_comp_unit(counterpart.identifier)
            if compiled is None or _normalized(compiled.text) == _normalized(section_text):
                continue
        out.append(Candidate.of_pl(pl[0], pl[1], counterpart.version.current_through_date))
    return out


def _with_dates(repository: Repository, candidates: dict[str, list[Candidate]]) -> dict[str, list[Candidate]]:
    """Fill the enactment dates of undated candidates the store holds."""
    undated = [c.identifier for group in candidates.values() for c in group if c.date is None]
    if not undated:
        return candidates
    dates = repository.enacted_dates(undated)
    if not dates:
        return candidates
    return {
        kind: [
            Candidate(c.identifier, c.kind, c.congress, c.number, dates.get(c.identifier)) if c.date is None else c
            for c in group
        ]
        for kind, group in candidates.items()
    }


def citing_sections(credits: Sequence[SourceCreditEvidence]) -> tuple[str, ...]:
    """The US Code sections whose source credits cite the unit, for the
    codified alternative."""
    return tuple(sorted({credit.from_identifier for credit in credits})[:CODIFIED_CAP])


# ------------------------------------------------------------------ decision


def decide(
    repository: Repository,
    *,
    law: LawRef,
    level: str,
    num: str | None,
    text: str | None = None,
) -> Amended:
    """`currency.amended` for a unit of `law` at `level`. `text` is the
    enacted section's text when the compilation comparison is wanted."""
    section_num = num if level == "section" else None
    credits = repository.source_credit_evidence(law.identifier, section_num)
    rows = repository.classification_amendments(law.identifier, section_num)
    counterparts = repository.compiled_counterparts(law.identifier, section_num)
    candidates = _with_dates(
        repository,
        {
            "source_credit": _credit_candidates(credits),
            "classification": _classification_candidates(rows),
            "compilation": _compilation_candidates(
                repository, counterparts,
                section_text=text if section_num is not None else None,
                compare_text=text is not None,
            ),
        },
    )
    fired: dict[str, list[Candidate]] = {
        kind: [c for c in candidates[kind] if _fires(c, law)] for kind in EVIDENCE_KINDS
    }
    evidence = tuple(kind for kind in EVIDENCE_KINDS if fired[kind])
    citing = citing_sections(credits)
    if evidence:
        latest = newest(c for kind in EVIDENCE_KINDS for c in fired[kind])
        return Amended("known_amended", latest, evidence, citing)
    coverage = repository.index_coverage(law.identifier)
    known = coverage.cited or coverage.classified or coverage.tables_cover
    status = "no_record" if known and law.kind != "pvtl" else "unknown"
    return Amended(status, None, (), citing)


def amended_for_unit(repository: Repository, result: UnitResult) -> Amended:
    """The decision for a served unit, with the text comparison."""
    return decide(repository, law=result.law, level=result.level, num=result.num, text=result.text)


def amended_for_label(repository: Repository, info: LabelInfo) -> Amended:
    """The decision for a `labels` answer: no text comparison."""
    return decide(repository, law=info.law, level=info.level, num=info.num, text=None)


def codified_from_index(repository: Repository, law: LawRef, level: str, num: str | None) -> tuple[str, ...]:
    """`citing_sections` for a unit, when no decision was made first."""
    section_num = num if level == "section" else None
    return citing_sections(repository.source_credit_evidence(law.identifier, section_num))
