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

    units: tuple[UnitRef, ...] = ()
    """The units the page touches: the one the marker falls in, then every unit
    of the law that starts on the page, in reading order. Empty unless the
    slice was asked for."""
    xml: str | None = None
    """The law's USLM between the page's marker and the next one (ADR-0020),
    None unless the slice was asked for."""
    text: str | None = None
    """The reading text of the slice."""
    to_identifier: str | None = None
    """The page identifier the range ends at; None at the law's end."""


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
class LawSources:
    """Which collections hold a law, and which one it is served from (design
    section 2; ADR-0011). A public law of the 113th Congress onward is served
    from its `PLAW` package once that is loaded; the volume-derived copy is
    replaced and the volume is still recorded as holding it."""

    law_identifier: str
    served_from: str
    """`STATUTE` | `PLAW`: `source_collection` of the stored copy."""
    package: str
    provenance_identifiers: str
    """`rules-1.0`, `gpo-uslm`, or `gpo-uslm+rules-1.0`."""
    volume: int
    volume_package: str
    """`STATUTE-137`."""
    volume_loaded: bool
    """The volume file has been loaded: a law from it is stored, or a
    `STATUTE` check names it."""
    plaw_package: str | None
    """`PLAW-118publ22` for a public or private law of the 104th Congress
    onward, whether or not it is loaded; None before that."""
    plaw_uslm: bool
    """GovInfo has USLM for the package: a public law of the 113th onward."""


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
    files: tuple[CompRef, ...] = ()
    """The per-title files a compilation root gathers when the act has no
    whole-act file, in title order (ADR-0007, decision 8). Empty when the
    answer comes from one file."""

    @property
    def is_exact(self) -> bool:
        return self.resolution == "exact"

    @property
    def is_gathered(self) -> bool:
        """A root answered from several per-title files rather than one document."""
        return bool(self.files)

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
    laws_by_congress: tuple[tuple[int, int], ...] = field(default=())
    """`PLAW` only: (congress, laws loaded) pairs, congress ascending."""

    @property
    def congresses(self) -> tuple[int, ...]:
        return tuple(c for c, _ in self.laws_by_congress)


# ------------------------------------------------------- stage 3: the indexes


@dataclass(frozen=True, slots=True)
class CitationRef:
    """One `<ref>` from a US Code section to a law, act, or Stat. page."""

    from_identifier: str
    release_label: str
    context: str
    """`sourceCredit` | `note` | `text`."""
    note_topic: str | None
    seq: int
    to_identifier: str
    to_kind: str
    """`pl` | `pvtl` | `act` | `stat`."""
    to_law: str | None
    to_section_num: str | None
    to_congress: int | None
    to_number: int | None
    to_chapter: int | None
    to_date: datetime.date | None


@dataclass(frozen=True, slots=True)
class CitingSection:
    """A US Code section that cites the asked-for unit, with the refs that do."""

    identifier: str
    citation: str | None
    heading: str | None
    release_label: str
    refs: tuple[CitationRef, ...]


@dataclass(frozen=True, slots=True)
class CitedBy:
    """The answer to "which US Code sections cite this unit" (design section 5)."""

    requested_identifier: str
    law_identifier: str
    """The law's primary form when it is loaded, else the form asked for."""
    law: LawRef | None
    aliases: tuple[str, ...]
    """Every identifier the citing side may have used for the law."""
    section_num: str | None
    below: str | None
    """The path below the section that was asked for (`e/1`), when any."""
    sections: tuple[CitingSection, ...]
    total: int
    """Distinct citing sections over every context asked for."""
    contexts: dict[str, int]
    """Matching refs per context, over the whole answer."""
    release_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LawCite:
    """A law named by a ref in one citing section's source credit."""

    identifier: str
    kind: str
    congress: int | None
    number: int | None
    chapter: int | None
    date: datetime.date | None
    seq: int


@dataclass(frozen=True, slots=True)
class SourceCreditEvidence:
    """One US Code section whose source credit cites the unit, and every law
    that credit names, in order. Evidence for `currency.amended`."""

    from_identifier: str
    release_label: str
    cites: tuple[str, ...]
    """The hrefs in the credit that point at the asked-for unit."""
    laws: tuple[LawCite, ...]


@dataclass(frozen=True, slots=True)
class ClassificationRow:
    congress: int
    session: int
    row_seq: int
    usc_identifier: str | None
    title_num: str | None
    section_raw: str | None
    is_note: bool
    action: str | None
    """`new`, `repealed`, `tr to`, …; None (the table's blank) means amended."""
    description_raw: str | None
    act_name: str | None
    pl_congress: int | None
    pl_num: int | None
    pl_section_raw: str
    pl_section_num: str | None
    stat_volume: int | None
    stat_page_labels: tuple[str, ...]

    @property
    def pl_identifier(self) -> str | None:
        if self.pl_congress is None or self.pl_num is None:
            return None
        return f"/us/pl/{self.pl_congress}/{self.pl_num}"

    @property
    def pl_label(self) -> str | None:
        if self.pl_congress is None or self.pl_num is None:
            return None
        return f"{self.pl_congress}-{self.pl_num}"


@dataclass(frozen=True, slots=True)
class IndexCoverage:
    """Whether the indexes know a law at all: what tells `no_record` from
    `unknown` (design section 4)."""

    law_identifier: str
    cited: bool
    """Some US Code section cites the law (any section, any context)."""
    classified: bool
    """A classification row has this law as its public law."""
    tables_cover: bool
    """A mirrored classification table's covered ranges include the law number."""


@dataclass(frozen=True, slots=True)
class CitationIndexStatus:
    rows: int
    citing_sections: int
    titles: int
    release_labels: tuple[tuple[str, int], ...]
    """(label, rows) pairs, most rows first."""
    loaded_at: datetime.datetime | None
    """When the index was last built (the last `USCODE` check that loaded shards)."""
    checked_at: datetime.datetime | None
    """When the dataset was last asked about, loaded or not
    (`citations --from-hub --if-changed` records a check either way)."""
    dataset_revision: str | None


@dataclass(frozen=True, slots=True)
class ClassificationFileRef:
    congress: int
    session: int
    session_label: str | None
    kind: str
    source_url: str | None
    covered_laws_text: str | None
    covered_ranges: tuple[str, ...]
    first_law: int | None
    last_law: int | None
    prepared_date: datetime.date | None
    stat_volume: int | None
    row_count: int
    upstream_fetched_at: datetime.datetime | None
    mirrored_at: datetime.datetime

    def covers(self, number: int) -> bool:
        for span in self.covered_ranges:
            lo, _, hi = span.partition("-")
            try:
                if int(lo) <= number <= int(hi or lo):
                    return True
            except ValueError:
                continue
        return False


@dataclass(frozen=True, slots=True)
class ClassificationCheckInfo:
    checked_at: datetime.datetime
    ok: bool
    source_url: str
    congress: int | None
    files_seen: int | None
    files_loaded: int | None
    files_unchanged: int | None
    rows_loaded: int | None
    upstream_checked_at: datetime.datetime | None
    upstream_covered_text: str | None
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
class ClassificationStatus:
    files: tuple[ClassificationFileRef, ...]
    rows: int
    congresses: tuple[int, ...]
    last_check: ClassificationCheckInfo | None


class Repository(Protocol):
    """Everything the API needs. Implemented by `PostgresRepository`."""

    # ---------------------------------------------------------------- enacted

    def get_unit(self, identifier: str, *, wanted: str = "json") -> UnitResult | None:
        """Resolve an enacted-view identifier (design section 3).

        1. Exact match on a stored unit or on the law.
        2. Otherwise the longest stored prefix; a section prefix has the
           remaining path cut from its XML as `provision`.
        3. Otherwise, when the path names a section number, the section-number
           index under the law.
        4. A law is found by any of its aliases.

        None when no law answers to the identifier.

        `wanted` is `"json"` or `"xml"`. A law's and a hierarchy node's `xml`
        and `text` are empty for both, and `Law.xml` is not read (ADR-0019,
        "XML above a section"). A section carries both regardless of
        `wanted`, and a path below it has its provision cut for both.
        """
        ...

    def get_law(self, identifier: str) -> LawSummary | None:
        ...

    def get_section_by_number(self, law_identifier: str, section_num: str) -> UnitResult | None:
        """Rule 3 on its own: the section with this number, ignoring hierarchy."""
        ...

    def stat_page(self, volume: int, page: str, *, with_slices: bool = False) -> StatPageResult | None:
        """The laws on a printed page. `with_slices` adds each law's slice of
        the page, its text and the units the page touches, which parses the
        law's XML (ADR-0020)."""
        ...

    def labels(self, identifiers: Sequence[str]) -> dict[str, LabelInfo]:
        """Resolution and heading for many identifiers at once; absent when
        nothing answers."""
        ...

    def law_sources(self, law_identifier: str) -> LawSources | None:
        """Which collection the law is served from, whether its volume is
        loaded, and its PLAW package name. None when the law is not loaded."""
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

    def get_comp_unit(self, identifier: str, *, through: str | None = None, wanted: str = "json") -> CompUnitResult | None:
        """Resolve a `/us/sComp/…` identifier in the current version, or in the
        stored version whose `current_through_pl` is `through`.

        None when no compilation has the prefix, or when `through` names no
        stored version.

        `wanted` is `"json"` or `"xml"`. The compilation's and a hierarchy
        node's `xml` and `text` are empty for both, and `CompVersion.xml` is
        not read (ADR-0019, "XML above a section"). A section carries both
        regardless of `wanted`, and a path below it has its provision cut for
        both. A bare prefix with no whole-act file is answered from every
        per-title file under it (`files`).
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

    # ---------------------------------------------------------------- indexes

    def cited_by(self, identifier: str, *, contexts: Sequence[str] | None = None,
                 limit: int = 50, offset: int = 0) -> CitedBy | None:
        """US Code sections whose refs point at the unit (design section 5).

        The law is matched through every alias it answers to (the Code cites
        the Atomic Energy Act of 1954 as `/us/act/1954-08-30/ch1073`). A
        section is matched by number, whatever hierarchy the ref wrote; a path
        below a section matches refs to that path or under it; the law alone
        matches refs to any of its sections (rule 2). `/us/stat/{vol}/{page}`
        matches refs to that page. None when the identifier is not one this
        site serves. `sections` is one page of distinct citing sections in
        identifier order; `total` counts them all.
        """
        ...

    def source_credit_evidence(self, law_identifier: str, section_num: str | None) -> tuple[SourceCreditEvidence, ...]:
        """Every US Code section whose source credit cites the law's section
        (or, with no section, the law), with all the laws that credit names."""
        ...

    def classification_rows(self, law_identifier: str, section_num: str | None = None) -> tuple[ClassificationRow, ...]:
        """The classification table's rows for this public law; with a section
        number, the rows whose `Sec.` cell names it. Empty for a private law
        or an act with no public-law alias."""
        ...

    def classification_amendments(self, law_identifier: str, section_num: str | None) -> tuple[ClassificationRow, ...]:
        """Rows of *later* public laws that classify to a US Code section this
        law's section (or the law) was itself classified to: the tables'
        evidence that the codified text was amended since."""
        ...

    def index_coverage(self, law_identifier: str) -> IndexCoverage:
        ...

    def enacted_dates(self, law_identifiers: Sequence[str]) -> dict[str, datetime.date]:
        """Enactment dates for the laws that are loaded, by any alias."""
        ...

    def citation_index_status(self) -> CitationIndexStatus:
        ...

    def classification_status(self) -> ClassificationStatus:
        ...

    def last_classification_check(self) -> ClassificationCheckInfo | None:
        ...

    # ----------------------------------------------------------------- status

    def collection_status(self, collection: str) -> CollectionStatus:
        ...

    def last_source_check(self, collection: str) -> SourceCheckInfo | None:
        ...
