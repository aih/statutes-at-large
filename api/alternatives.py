"""The `alternatives` list of an enacted-view response: the other views of the
same provision (design section 4).

A compiled alternative is the compilation's unit with the same section number
under the same law (`Repository.compiled_counterparts`), or the compilation
itself when the law was asked for. A codified alternative is the US Code
section the compilation's own editorial note names for that section; the
citation index of design stage 3 is not built, so a section with no
compilation has no codified alternative yet.

The origins come from the environment (`SITE_ORIGIN`, `USCODE_ORIGIN`), read
here because `api/` may not import `db.config`.
"""

from __future__ import annotations

import os

from api.schemas import AlternativeOut
from storage import CompCounterpart, Repository, UnitResult

SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://statutes.linkedlegislation.org")
USCODE_ORIGIN = os.environ.get("USCODE_ORIGIN", "https://uscode.linkedlegislation.org")


def alternatives_for(repository: Repository, result: UnitResult) -> list[AlternativeOut]:
    """The other views available for an enacted unit."""
    section_num = result.num if result.level == "section" else None
    if result.level not in ("law", "section"):
        # A title or chapter of the enacted law has no unit-level counterpart in
        # a compilation (their hierarchy is written differently); the law does.
        return []
    counterparts = repository.compiled_counterparts(result.law.identifier, section_num)
    return _alternatives(counterparts)


def _alternatives(counterparts: list[CompCounterpart]) -> list[AlternativeOut]:
    out: list[AlternativeOut] = []
    codified: list[str] = []
    for counterpart in counterparts:
        out.append(
            AlternativeOut(
                view="compiled",
                identifier=counterpart.identifier,
                current_through=_current_through(counterpart),
                url=f"{SITE_ORIGIN}{counterpart.identifier}",
            )
        )
        for ref in counterpart.usc_refs:
            if ref not in codified:
                codified.append(ref)
    if codified:
        out.append(
            AlternativeOut(view="codified", identifiers=codified, url=f"{USCODE_ORIGIN}{codified[0]}")
        )
    return out


def _current_through(counterpart: CompCounterpart) -> dict:
    version = counterpart.version
    return {
        "pl": version.current_through_pl,
        "enacted": version.current_through_date.isoformat() if version.current_through_date else None,
    }


def compiled_link(alternatives: list[AlternativeOut]) -> str | None:
    """The first compiled alternative's identifier, for the note."""
    return next((a.identifier for a in alternatives if a.view == "compiled"), None)


def codified_labels(alternatives: list[AlternativeOut]) -> list[str]:
    """`42 U.S.C. 2011` for each codified identifier, for the note."""
    labels: list[str] = []
    for alternative in alternatives:
        if alternative.view != "codified":
            continue
        for identifier in alternative.identifiers or []:
            labels.append(usc_label(identifier))
    return labels


def usc_label(identifier: str) -> str:
    """`/us/usc/t42/s2011` → `42 U.S.C. 2011`; anything else is returned as is."""
    parts = [p for p in identifier.split("/") if p]
    if len(parts) >= 4 and parts[0] == "us" and parts[1] == "usc" and parts[2].startswith("t") and parts[3].startswith("s"):
        rest = "".join(f"({p})" for p in parts[4:])
        return f"{parts[2][1:]} U.S.C. {parts[3][1:]}{rest}"
    return identifier
