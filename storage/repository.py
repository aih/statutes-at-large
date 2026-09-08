"""The `Repository` interface: the only thing `api/` is allowed to know about storage.

Nothing below names a table, a column, or SQL. Results are frozen dataclasses,
and every resolution decision (design section 3: exact match, longest stored
prefix, section-number index, alias) happens behind this line.

Two views share the vocabulary (design section 4):

  * **enacted** — a law as printed in the Statutes at Large, addressed by
    `/us/pl/…`, `/us/pvtl/…`, `/us/act/…`; never updated.
  * **compiled** — a Statute Compilation from the House Office of the Legislative
    Counsel, addressed by `/us/sComp/…`, current through a public law.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from storage.identifiers import law_label

GOVINFO_STATUTE_LINK = "https://www.govinfo.gov/link/statute/{volume}/{page}"
GOVINFO_PLAW_LINK = "https://www.govinfo.gov/link/plaw/{congress}/{kind}/{number}"
GOVINFO_COMPS_DETAILS = "https://www.govinfo.gov/app/details/{package_id}"

SOURCE_CHECK_STALE_AFTER = datetime.timedelta(days=7)
"""How old the last successful poll of a collection may get before `/status`
reports it stale."""


class RepositoryError(Exception):
    """Base for the errors a repository raises rather than returning None."""


class RepositoryUnavailableError(RepositoryError):
    """The store cannot answer right now: every connection is busy."""


@dataclass(frozen=True, slots=True)
class LawRef:
    """One law, as everything outside storage sees it."""

    identifier: str
    kind: str
    """`pl` | `pvtl` | `act`."""
    congress: int | None
    number: int | None
    chapter: int | None
    enacted: datetime.date | None
    doc_type: str | None
    official_title: str | None
    short_titles: tuple[str, ...]
    stat_volume: int
    stat_page_first: str | None
    stat_page_last: str | None
    citation: str | None
    source_collection: str
    source_package: str
    source_granule: str | None
    provenance_text: str
    provenance_identifiers: str
    content_hash: str
    aliases: tuple[str, ...] = ()
    """Every identifier the law answers to, the primary one first."""

    @property
    def label(self) -> str:
        """`Public Law 83-703`, `Act of August 30, 1954, ch. 1073`."""
        return law_label(self.kind, self.congress, self.number, self.chapter, self.enacted)

    @property
    def govinfo_pdf(self) -> str | None:
        if self.stat_page_first is None:
            return None
        return GOVINFO_STATUTE_LINK.format(volume=self.stat_volume, page=self.stat_page_first)


@dataclass(frozen=True, slots=True)
class UnitRef:
    """A table-of-contents entry: a structural node or a section."""

    identifier: str
    level: str
    num: str | None
    heading: str | None
    is_section: bool = False
    occurrence: int = 1


@dataclass(frozen=True, slots=True)
class Provision:
    """A sub-section path cut from its section at request time."""

    identifier: str
    found: bool
    xml: str | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class PageRef:
    volume: int
    page: str

    @property
    def identifier(self) -> str:
        return f"/us/stat/{self.volume}/{self.page}"

    @property
    def pdf(self) -> str:
        return GOVINFO_STATUTE_LINK.format(volume=self.volume, page=self.page)


@dataclass(frozen=True, slots=True)
class UnitResult:
    """What an enacted-view identifier resolved to.

    `level` is `law` when the identifier named the law itself, or when nothing
    under it matched and the law is the longest stored prefix.
    """

    requested_identifier: str
    served_identifier: str
    resolution: str
    """`exact` | `prefix` | `section_number` | `alias`.

    `alias` means the law was addressed by an identifier other than its
    primary one (a chapter form for a numbered law, rule 4); `served_identifier`
    then carries the primary form. `prefix` means the stored unit is an ancestor
    of what was asked for (rule 2). `section_number` means the section was found
    by number under a different hierarchy (rule 3)."""

    law: LawRef
    level: str
    num: str | None
    heading: str | None
    xml: str
    text: str
    content_hash: str
    ancestors: tuple[UnitRef, ...]
    children: tuple[UnitRef, ...]
    """For the law and for hierarchy nodes: the units directly under it, in
    reading order. Empty for a section."""
    pages: tuple[PageRef, ...]
    provision: Provision | None = None
    """Set when the request went below the served unit and the served unit is a
    section: the path cut from the section's XML, found or not."""
    occurrences: int = 1
    """How many elements the source numbered with this identifier (1 is the
    usual answer)."""

    @property
    def is_exact(self) -> bool:
        return self.resolution == "exact"

    @property
    def is_section(self) -> bool:
        return self.level == "section"

    @property
    def unit_label(self) -> str:
        """`section 1`, `title I`, `the law`, for the note sentence."""
        if self.level == "law":
            return "the law"
        return f"{self.level} {self.num}" if self.num else self.level


@dataclass(frozen=True, slots=True)
class LawSummary:
    law: LawRef
    toc: tuple[UnitRef, ...]
    """Every unit of the law in reading order, sections and hierarchy nodes
    alike; the `depth` order is the source's."""
    section_count: int


@dataclass(frozen=True, slots=True)
class StatPageDocument:
    law: LawRef
    starts_here: bool
    unit_identifier: str | None
    """The unit in which the page marker falls, when it falls inside one."""


@dataclass(frozen=True, slots=True)
class StatPageResult:
    volume: int
    page: str
    documents: tuple[StatPageDocument, ...]

    @property
    def identifier(self) -> str:
        return f"/us/stat/{self.volume}/{self.page}"

    @property
    def pdf(self) -> str:
        return GOVINFO_STATUTE_LINK.format(volume=self.volume, page=self.page)


@dataclass(frozen=True, slots=True)
class LabelInfo:
    """One answer of the batched `labels` lookup."""

    identifier: str
    served_identifier: str
    resolution: str
    law: LawRef
    level: str
    num: str | None
    heading: str | None


# ------------------------------------------------------------------ compilations


@dataclass(frozen=True, slots=True)
class CompVersionRef:
    id: int
    current_through_pl: str | None
    """`118-67`."""
    current_through_date: datetime.date | None
    govinfo_last_modified: datetime.datetime | None
    fetched_at: datetime.datetime
    content_hash: str
    is_current: bool


@dataclass(frozen=True, slots=True)
class CompRef:
    file_id: str
    package_id: str
    identifier_prefix: str
    """`/us/sComp/83/703`."""
    law_congress: int | None
    law_number: int | None
    law_identifier: str | None
    """The enacted law this compiles, when it is loaded."""
    title: str | None
    display_title: str | None
    short_titles: tuple[str, ...]
    approved_date: datetime.date | None
    partial_of: str | None
    """The title designator when the compilation is one title of a larger act
    (`II` for the Social Security Act title files)."""
    current: CompVersionRef | None
    versions: tuple[CompVersionRef, ...] = ()

    @property
    def govinfo_details(self) -> str:
        return GOVINFO_COMPS_DETAILS.format(package_id=self.package_id)

    @property
    def short_title(self) -> str | None:
        return self.short_titles[0] if self.short_titles else self.display_title


@dataclass(frozen=True, slots=True)
class CompUnitResult:
    requested_identifier: str
    served_identifier: str
    resolution: str
    """`exact` | `prefix` | `section_number`."""
    comp: CompRef
    version: CompVersionRef
    pinned: bool
    """True when the caller named a `through=` and this version is it."""
    level: str
    num: str | None
    heading: str | None
    xml: str
    text: str
    content_hash: str
    ancestors: tuple[UnitRef, ...]
    children: tuple[UnitRef, ...]
    usc_refs: tuple[str, ...]
    """`/us/usc/…` identifiers the compilation's editorial note gives for this
    section."""
    provision: Provision | None = None
    section_num: str | None = None

    @property
    def is_exact(self) -> bool:
        return self.resolution == "exact"

    @property
    def unit_label(self) -> str:
        if self.level == "compilation":
            return "the compilation"
        return f"{self.level} {self.num}" if self.num else self.level


@dataclass(frozen=True, slots=True)
class CompCounterpart:
    """A compiled unit that corresponds to an enacted section (or the reverse),
    matched by law and section number."""

    comp: CompRef
    version: CompVersionRef
    identifier: str
    level: str
    num: str | None
    heading: str | None
    usc_refs: tuple[str, ...]
    content_hash: str | None


# ------------------------------------------------------------------------ status


@dataclass(frozen=True, slots=True)
class SourceCheckInfo:
    collection: str
    checked_at: datetime.datetime
    ok: bool
    newest_last_modified: datetime.datetime | None
    newest_package: str | None
    packages_seen: int | None
    new_packages: tuple[str, ...]
    error: str | None

    def age(self, *, now: datetime.datetime | None = None) -> datetime.timedelta:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        checked_at = self.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=datetime.timezone.utc)
        return now - checked_at

    def is_stale(self, *, now: datetime.datetime | None = None) -> bool:
        return not self.ok or self.age(now=now) > SOURCE_CHECK_STALE_AFTER


@dataclass(frozen=True, slots=True)
class CollectionStatus:
    collection: str
    packages_loaded: int
    latest_package: str | None
    latest_loaded_at: datetime.datetime | None
    laws: int = 0
    units: int = 0
    volumes: tuple[int, ...] = field(default=())


class Repository(Protocol):
    """Everything the API needs. Implemented by `PostgresRepository`."""

    # ---------------------------------------------------------------- enacted

    def get_unit(self, identifier: str) -> UnitResult | None:
        """Resolve an enacted-view identifier (design section 3).

        1. Exact match on a stored unit or on the law.
        2. Otherwise the longest stored prefix; a section prefix has the
           remaining path cut from its XML as `provision`.
        3. Otherwise, when the path names a section number, the section-number
           index under the law.
        4. A law is found by any of its aliases.

        None when no law answers to the identifier.
        """
        ...

    def get_law(self, identifier: str) -> LawSummary | None:
        ...

    def get_section_by_number(self, law_identifier: str, section_num: str) -> UnitResult | None:
        """Rule 3 on its own: the section with this number, ignoring hierarchy."""
        ...

    def stat_page(self, volume: int, page: str) -> StatPageResult | None:
        ...

    def labels(self, identifiers: Sequence[str]) -> dict[str, LabelInfo]:
        """Resolution and heading for many identifiers at once; absent when
        nothing answers."""
        ...

    # --------------------------------------------------------------- compiled

    def compilations_for_law(self, law_identifier: str) -> list[CompRef]:
        """Every compilation whose prefix names this law, with its current version."""
        ...

    def get_comp(self, file_id: str) -> CompRef | None:
        """A compilation with its whole version list."""
        ...

    def list_comps(self, *, law_identifier: str | None = None, q: str | None = None,
                   limit: int = 50) -> list[CompRef]:
        ...

    def get_comp_unit(self, identifier: str, *, through: str | None = None) -> CompUnitResult | None:
        """Resolve a `/us/sComp/…` identifier in the current version, or in the
        stored version whose `current_through_pl` is `through`.

        None when no compilation has the prefix, or when `through` names no
        stored version.
        """
        ...

    def compiled_counterparts(self, law_identifier: str, section_num: str | None) -> list[CompCounterpart]:
        """The compiled units for an enacted law's section (by number, ignoring
        hierarchy), or the compilation roots when `section_num` is None."""
        ...

    def enacted_counterpart(self, comp_prefix: str, section_num: str | None) -> UnitResult | None:
        """The enacted section with this number under the law a compilation
        prefix names, or the law itself when `section_num` is None."""
        ...

    # ----------------------------------------------------------------- status

    def collection_status(self, collection: str) -> CollectionStatus:
        ...

    def last_source_check(self, collection: str) -> SourceCheckInfo | None:
        ...
