"""Settle law-number collisions inside one volume before anything is stored.

In the chapter era (through 1957) the law number is read from a marginal note
by a digitization vendor, and volume 64 has 46 numbers each claimed by two
laws. Law numbers run in enactment order inside each series (public, private),
so among the claimants the one whose number sits between its clean neighbours'
numbers is the one the note really says. The others keep their chapter
identifier, which comes from the printed chapter heading and is certain.

After 1957 the number *is* the document number; a collision there means the
source repeated one, and the claimant out of sequence has no other identifier
and is dropped from the load with its citation in the report.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Claim:
    seq: int
    kind: str
    number: int | None
    primary: str
    chapter_form: str | None
    citation: str | None
    title: str | None


@dataclass(slots=True)
class Decision:
    seq: int
    action: str
    """`demote` (store under the chapter form) | `drop` (nothing certain to store it under)."""
    claimed: str
    kept_as: str | None
    citation: str | None
    title: str | None
    reason: str


@dataclass(slots=True)
class NumberingPlan:
    decisions: dict[int, Decision] = field(default_factory=dict)
    out_of_sequence: list[dict] = field(default_factory=list)
    """Numbers kept but not between their neighbours; recorded, not changed."""

    def action_for(self, seq: int) -> Decision | None:
        return self.decisions.get(seq)


def plan_numbering(claims: list[Claim]) -> NumberingPlan:
    plan = NumberingPlan()
    by_series: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        if claim.kind in ("pl", "pvtl") and claim.number is not None:
            by_series[claim.kind].append(claim)

    for kind, series in by_series.items():
        series.sort(key=lambda c: c.seq)
        counts: dict[int, int] = defaultdict(int)
        for claim in series:
            counts[claim.number] += 1  # type: ignore[index]
        clean = [c for c in series if counts[c.number] == 1]  # type: ignore[index]

        def neighbours(claim: Claim) -> tuple[Claim | None, Claim | None]:
            prev = next((c for c in reversed(clean) if c.seq < claim.seq), None)
            nxt = next((c for c in clean if c.seq > claim.seq), None)
            return prev, nxt

        def consistent(claim: Claim) -> bool:
            prev, nxt = neighbours(claim)
            if prev is not None and not (prev.number < claim.number):  # type: ignore[operator]
                return False
            if nxt is not None and not (claim.number < nxt.number):  # type: ignore[operator]
                return False
            return True

        claimants: dict[int, list[Claim]] = defaultdict(list)
        for claim in series:
            if counts[claim.number] > 1:  # type: ignore[index]
                claimants[claim.number].append(claim)  # type: ignore[index]
        for number, group in claimants.items():
            fitting = [c for c in group if consistent(c)]
            keep = fitting[0] if fitting else group[0]
            for claim in group:
                if claim is keep:
                    continue
                if claim.chapter_form is not None:
                    plan.decisions[claim.seq] = Decision(
                        claim.seq, "demote", claim.primary, claim.chapter_form, claim.citation, claim.title,
                        f"law number {number} is also claimed by the law at seq {keep.seq}, whose number fits the sequence",
                    )
                else:
                    plan.decisions[claim.seq] = Decision(
                        claim.seq, "drop", claim.primary, None, claim.citation, claim.title,
                        f"law number {number} is also claimed by the law at seq {keep.seq}; no chapter form to store this one under",
                    )
        for claim in clean:
            if not consistent(claim):
                plan.out_of_sequence.append(
                    {"seq": claim.seq, "identifier": claim.primary, "citation": claim.citation, "title": claim.title}
                )
    return plan
