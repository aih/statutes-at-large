"""Response models: the public JSON contract and the OpenAPI docs.

A translation of `storage`'s dataclasses rather than a reuse of them, so the
wire format does not move when an internal field is renamed. Nothing here
imports from `db`.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.currency import Amended, Candidate
from citeparse import ParsedCitation
from storage import (
    GOVINFO_PLAW_LINK,
    CitationIndexStatus,
    CitedBy,
    CitingSection,
    ClassificationCheckInfo,
    ClassificationFileRef,
    ClassificationStatus,
    CollectionStatus,
    CompRef,
    LabelInfo,
    LawRef,
    LawSources,
    LawSummary,
    PageRef,
    Provision,
    SourceCheckInfo,
    StatPageDocument,
    StatPageResult,
    UnitRef,
    UnitResult,
)


class ErrorOut(BaseModel):
    detail: str


# ---------------------------------------------------------------------- laws


class LawSourceOut(BaseModel):
    """The GovInfo package the stored copy of the law came from."""

    collection: str = Field(description="`STATUTE` | `PLAW`.", examples=["STATUTE", "PLAW"])
    package: str = Field(examples=["STATUTE-64", "PLAW-118publ22"])
    granule: str | None = Field(default=None, description="Null for a PLAW package.", examples=["STATUTE-64-Pg563"])


class LawOut(BaseModel):
    identifier: str = Field(examples=["/us/pl/81/740"])
    kind: str = Field(description="`pl` | `pvtl` | `act`.")
    congress: int | None
    number: int | None
    chapter: int | None = Field(
        default=None, description="The chapter number; laws from 1901 to 1957 carry one beside the law number."
    )
    label: str = Field(examples=["Public Law 81-740"])
    aliases: list[str] = Field(
        default_factory=list,
        description="Every identifier the law answers to, the primary one first.",
        examples=[["/us/pl/81/740", "/us/act/1950-08-30/ch823"]],
    )
    short_titles: list[str] = Field(default_factory=list)
    official_title: str | None = None
    doc_type: str | None = None
    enacted: datetime.date | None
    citation: str | None = Field(default=None, examples=["64 Stat. 563"])
    source: LawSourceOut

    @classmethod
    def of(cls, law: LawRef) -> LawOut:
        return cls(
            identifier=law.identifier,
            kind=law.kind,
            congress=law.congress,
            number=law.number,
            chapter=law.chapter,
            label=law.label,
            aliases=list(law.aliases),
            short_titles=list(law.short_titles),
            official_title=law.official_title,
            doc_type=law.doc_type,
            enacted=law.enacted,
            citation=law.citation,
            source=LawSourceOut(
                collection=law.source_collection,
                package=law.source_package,
                granule=law.source_granule,
            ),
        )


# ------------------------------------------------------------------ currency


class LatestOut(BaseModel):
    """The newest law the evidence recorded."""

    pl: str | None = Field(description="`118-67` for a public law; null for an act.", examples=["118-67"])
    identifier: str = Field(examples=["/us/pl/118/67"])
    label: str = Field(examples=["Public Law 118-67"])
    enacted: datetime.date | None = Field(description="Null when no date is recorded for the law.")

    @classmethod
    def of(cls, latest: Candidate) -> LatestOut:
        return cls(pl=latest.pl, identifier=latest.identifier, label=latest.label, enacted=latest.date)


class AmendedOut(BaseModel):
    status: Literal["known_amended", "no_record", "unknown"] = Field(
        description="`known_amended`: a US Code source credit citing the unit names a later law, a "
        "classification row of a later law amends a section this unit was classified to, or a "
        "compilation current through a later law has different text. `no_record`: none of those, "
        "and the indexes know the law. `unknown`: a private law, or a law in no index (design section 4; "
        "`api/currency.py`)."
    )
    latest: LatestOut | None = Field(default=None, description="The newest law among the evidence that fired.")
    evidence: list[str] = Field(
        default_factory=list,
        description="The evidence that fired, in the order `source_credit`, `classification`, `compilation`.",
    )

    @classmethod
    def of(cls, amended: Amended) -> AmendedOut:
        return cls(
            status=amended.status,
            latest=LatestOut.of(amended.latest) if amended.latest is not None else None,
            evidence=list(amended.evidence),
        )


class CurrencyOut(BaseModel):
    kind: Literal["as_enacted"]
    date: datetime.date | None = Field(description="The enactment date.")
    amended: AmendedOut

    @classmethod
    def as_enacted(cls, law: LawRef, amended: AmendedOut) -> CurrencyOut:
        return cls(kind="as_enacted", date=law.enacted, amended=amended)


class AlternativeOut(BaseModel):
    """Another view of the same provision."""

    view: str = Field(description="`compiled` | `codified` | `enacted`.")
    identifier: str | None = None
    identifiers: list[str] | None = None
    current_through: dict[str, Any] | None = Field(
        default=None, description="`{pl, enacted}` for a compiled alternative."
    )
    url: str


class ProvenanceOut(BaseModel):
    text: str = Field(description="`gpo-uslm`: the text is GovInfo's USLM, from the volume file or the PLAW file.")
    identifiers: str = Field(
        description="Where the identifiers in the XML came from. `rules-1.0`: assigned by the volume loader "
        "(`ingest/identifiers.py`). `gpo-uslm`: read from a PLAW file. `gpo-uslm+rules-1.0`: a PLAW file with "
        "some levels filled in by rule where GPO wrote no identifier."
    )
    sha256: str = Field(description="The content hash of the served unit.")


class PageOut(BaseModel):
    page: str = Field(examples=["/us/stat/64/564"])
    pdf: str = Field(examples=["https://www.govinfo.gov/link/statute/64/564"])

    @classmethod
    def of(cls, page: PageRef) -> PageOut:
        return cls(page=page.identifier, pdf=page.pdf)


# --------------------------------------------------------------------- units


class AncestorOut(BaseModel):
    identifier: str
    level: str
    num: str | None
    heading: str | None

    @classmethod
    def of(cls, ref: UnitRef) -> AncestorOut:
        return cls(identifier=ref.identifier, level=ref.level, num=ref.num, heading=ref.heading)


class TocEntryOut(BaseModel):
    identifier: str
    level: str
    num: str | None
    heading: str | None
    is_section: bool = False

    @classmethod
    def of(cls, ref: UnitRef) -> TocEntryOut:
        return cls(
            identifier=ref.identifier, level=ref.level, num=ref.num, heading=ref.heading, is_section=ref.is_section
        )


class ProvisionOut(BaseModel):
    identifier: str
    found: bool
    xml: str | None = None
    text: str | None = None

    @classmethod
    def of(cls, provision: Provision) -> ProvisionOut:
        return cls(identifier=provision.identifier, found=provision.found, xml=provision.xml, text=provision.text)


class UnitOut(BaseModel):
    """An enacted-view answer: a law, a hierarchy node, or a section (design section 4)."""

    identifier: str = Field(description="The identifier asked for, normalized.")
    served_identifier: str = Field(description="The stored unit that answered.")
    view: Literal["enacted"]
    resolution: str = Field(description="`exact` | `prefix` | `section_number` | `alias` (design section 3).")
    law: LawOut
    level: str = Field(description="`law`, `section`, or a hierarchy level (`title`, `division`, …).")
    num: str | None
    heading: str | None
    currency: CurrencyOut
    alternatives: list[AlternativeOut] = Field(default_factory=list)
    note: str
    provenance: ProvenanceOut
    pages: list[PageOut] = Field(description="The Statutes at Large pages the unit spans, with GovInfo links.")
    text: str = Field(description="The served unit's reading text.")
    xml_url: str = Field(description="This request's URL with `format=xml`.")
    ancestors: list[AncestorOut] = Field(default_factory=list)
    children: list[TocEntryOut] = Field(
        default_factory=list,
        description="The table of contents under a law or hierarchy node. Empty for a section.",
    )
    provision: ProvisionOut | None = Field(
        default=None,
        description="Set when the request went below a section: the path cut from the section's XML, found or not.",
    )
    occurrences: int = Field(description="How many elements the source numbered with this identifier.")

    @classmethod
    def of(
        cls,
        result: UnitResult,
        *,
        note: str,
        alternatives: list[AlternativeOut],
        xml_url: str,
        amended: AmendedOut,
    ) -> UnitOut:
        law = result.law
        return cls(
            identifier=result.requested_identifier,
            served_identifier=result.served_identifier,
            view="enacted",
            resolution=result.resolution,
            law=LawOut.of(law),
            level=result.level,
            num=result.num,
            heading=result.heading,
            currency=CurrencyOut.as_enacted(law, amended),
            alternatives=alternatives,
            note=note,
            provenance=ProvenanceOut(
                text=law.provenance_text,
                identifiers=law.provenance_identifiers,
                sha256=result.content_hash,
            ),
            pages=[PageOut.of(p) for p in result.pages],
            text=result.text,
            xml_url=xml_url,
            ancestors=[AncestorOut.of(a) for a in result.ancestors],
            children=[TocEntryOut.of(c) for c in result.children],
            provision=ProvisionOut.of(result.provision) if result.provision else None,
            occurrences=result.occurrences,
        )


class NotFoundOut(BaseModel):
    """A 404 that carries the alternatives the identifier does have."""

    detail: str
    alternatives: list[AlternativeOut] = Field(default_factory=list)


# --------------------------------------------------------------- law summary


class CompilationOut(BaseModel):
    file_id: str
    package_id: str
    identifier_prefix: str = Field(examples=["/us/sComp/83/703"])
    display_title: str | None
    current_through: dict[str, Any] | None = Field(
        default=None, description="`{pl, enacted}` of the current version."
    )

    @classmethod
    def of(cls, comp: CompRef) -> CompilationOut:
        current = comp.current
        return cls(
            file_id=comp.file_id,
            package_id=comp.package_id,
            identifier_prefix=comp.identifier_prefix,
            display_title=comp.display_title,
            current_through=(
                {"pl": current.current_through_pl, "enacted": current.current_through_date}
                if current is not None
                else None
            ),
        )


class VolumeSourceOut(BaseModel):
    """The Statutes at Large volume that prints the law."""

    package: str = Field(examples=["STATUTE-137"])
    loaded: bool = Field(description="The volume file has been loaded, whether or not the law is served from it.")
    govinfo: str | None = Field(
        description="The GovInfo link to the law's first page; null when no page is recorded.",
        examples=["https://www.govinfo.gov/link/statute/137/112"],
    )


class PlawSourceOut(BaseModel):
    """The law's `PLAW` package on GovInfo (the 104th Congress onward)."""

    package: str | None = Field(
        description="`PLAW-118publ22`; null for a law before the 104th Congress.", examples=["PLAW-118publ22"]
    )
    uslm: bool = Field(description="GovInfo has USLM for the package: a public law of the 113th Congress onward.")
    loaded: bool = Field(description="The law is served from this package.")
    govinfo: str | None = Field(
        description="The GovInfo link to the package; null when there is none.",
        examples=["https://www.govinfo.gov/link/plaw/118/public/22"],
    )


class LawSourcesOut(BaseModel):
    """Which collections hold the law and which one it is served from."""

    served_from: str = Field(description="`STATUTE` | `PLAW`.", examples=["PLAW"])
    package: str = Field(description="The package the served copy came from.", examples=["PLAW-118publ22"])
    identifiers: str = Field(description="The served copy's `provenance.identifiers` value.", examples=["gpo-uslm"])
    volume: VolumeSourceOut
    plaw: PlawSourceOut

    @classmethod
    def of(cls, sources: LawSources | None, law: LawRef) -> LawSourcesOut:
        """From `Repository.law_sources`; from the law alone when the store returned none."""
        if sources is None:
            return cls(
                served_from=law.source_collection,
                package=law.source_package,
                identifiers=law.provenance_identifiers,
                volume=VolumeSourceOut(
                    package=f"STATUTE-{law.stat_volume}",
                    loaded=law.source_collection == "STATUTE",
                    govinfo=law.govinfo_pdf,
                ),
                plaw=PlawSourceOut(package=None, uslm=False, loaded=law.source_collection == "PLAW", govinfo=None),
            )
        plaw_link = None
        if sources.plaw_package is not None and law.congress is not None and law.number is not None:
            plaw_link = GOVINFO_PLAW_LINK.format(
                congress=law.congress, kind="public" if law.kind == "pl" else "private", number=law.number
            )
        return cls(
            served_from=sources.served_from,
            package=sources.package,
            identifiers=sources.provenance_identifiers,
            volume=VolumeSourceOut(
                package=sources.volume_package, loaded=sources.volume_loaded, govinfo=law.govinfo_pdf
            ),
            plaw=PlawSourceOut(
                package=sources.plaw_package,
                uslm=sources.plaw_uslm,
                loaded=sources.served_from == "PLAW",
                govinfo=plaw_link,
            ),
        )


class LawSummaryOut(BaseModel):
    law: LawOut
    toc: list[TocEntryOut] = Field(description="Every unit of the law in reading order.")
    section_count: int
    compilations: list[CompilationOut] = Field(default_factory=list)
    sources: LawSourcesOut

    @classmethod
    def of(cls, summary: LawSummary, compilations: list[CompRef], sources: LawSources | None) -> LawSummaryOut:
        return cls(
            law=LawOut.of(summary.law),
            toc=[TocEntryOut.of(u) for u in summary.toc],
            section_count=summary.section_count,
            compilations=[CompilationOut.of(c) for c in compilations],
            sources=LawSourcesOut.of(sources, summary.law),
        )


# --------------------------------------------------------------- stat pages


class StatPageDocumentOut(BaseModel):
    identifier: str = Field(examples=["/us/pl/81/740"])
    kind: str
    title: str | None = Field(description="The official title.")
    label: str = Field(examples=["Public Law 81-740"])
    citation: str | None
    enacted: datetime.date | None
    starts_here: bool
    unit_on_page: str | None = Field(description="The unit the page marker falls in, when it falls inside one.")

    @classmethod
    def of(cls, document: StatPageDocument) -> StatPageDocumentOut:
        law = document.law
        return cls(
            identifier=law.identifier,
            kind=law.kind,
            title=law.official_title,
            label=law.label,
            citation=law.citation,
            enacted=law.enacted,
            starts_here=document.starts_here,
            unit_on_page=document.unit_identifier,
        )


class StatPageOut(BaseModel):
    page: str = Field(description="The page label, lower case.", examples=["564", "a12"])
    identifier: str = Field(examples=["/us/stat/64/564"])
    volume: int
    documents: list[StatPageDocumentOut] = Field(
        description="Every law that starts on or spans the page; the ones that start here first."
    )
    pdf: str

    @classmethod
    def of(cls, page: StatPageResult) -> StatPageOut:
        return cls(
            page=page.page,
            identifier=page.identifier,
            volume=page.volume,
            documents=[StatPageDocumentOut.of(d) for d in page.documents],
            pdf=page.pdf,
        )


# ------------------------------------------------------------------- labels


class LabelsIn(BaseModel):
    identifiers: list[str] = Field(min_length=1, max_length=100)


class LabelCurrencyOut(BaseModel):
    kind: Literal["as_enacted"]
    date: datetime.date | None
    amended: AmendedOut = Field(description="The same block as a unit's `currency.amended`, without the compiled-text comparison.")


class LabelFoundOut(BaseModel):
    exists: Literal[True] = True
    served_identifier: str
    resolution: str
    num: str | None
    heading: str | None
    level: str
    kind: str = Field(description="The law's kind: `pl` | `pvtl` | `act`.")
    law_identifier: str
    law_label: str
    currency: LabelCurrencyOut

    @classmethod
    def of(cls, info: LabelInfo, amended: AmendedOut) -> LabelFoundOut:
        return cls(
            served_identifier=info.served_identifier,
            resolution=info.resolution,
            num=info.num,
            heading=info.heading,
            level=info.level,
            kind=info.law.kind,
            law_identifier=info.law.identifier,
            law_label=info.law.label,
            currency=LabelCurrencyOut(kind="as_enacted", date=info.law.enacted, amended=amended),
        )


class LabelPageDocumentOut(BaseModel):
    identifier: str
    label: str
    kind: str
    starts_here: bool


class LabelPageOut(BaseModel):
    """A Statutes at Large page, for a `/us/stat/{vol}/{page}` identifier:
    what a reader needs to link the reference to the page and say what is on it."""

    exists: Literal[True] = True
    served_identifier: str
    resolution: Literal["exact"] = "exact"
    num: str = Field(description="The page label, lower case.")
    heading: None = None
    level: Literal["page"] = "page"
    kind: Literal["stat"] = "stat"
    volume: int
    page: str
    documents: list[LabelPageDocumentOut] = Field(description="The laws on the page, the ones that start here first.")
    pdf: str

    @classmethod
    def of(cls, page: StatPageResult) -> LabelPageOut:
        return cls(
            served_identifier=page.identifier,
            num=page.page,
            volume=page.volume,
            page=page.page,
            documents=[
                LabelPageDocumentOut(identifier=d.law.identifier, label=d.law.label, kind=d.law.kind, starts_here=d.starts_here)
                for d in page.documents
            ],
            pdf=page.pdf,
        )


class LabelMissingOut(BaseModel):
    exists: Literal[False] = False


LabelOut = LabelFoundOut | LabelPageOut | LabelMissingOut


# ------------------------------------------------------------------- status


class CollectionStatusOut(BaseModel):
    packages_loaded: int
    latest_package: str | None
    latest_loaded_at: datetime.datetime | None
    laws: int
    units: int
    volumes: list[int] = Field(
        default_factory=list,
        description="Statutes at Large volumes: the ones loaded for `STATUTE`, the ones the laws print in for `PLAW`.",
    )
    congresses: list[int] = Field(
        default_factory=list, description="`PLAW` only: the congresses with laws loaded, ascending. Empty otherwise."
    )
    laws_by_congress: dict[int, int] = Field(
        default_factory=dict,
        description="`PLAW` only: laws loaded per congress, keyed by congress number (a string key on the wire, "
        "`{\"118\": 274}`). Empty otherwise.",
    )

    @classmethod
    def of(cls, status: CollectionStatus) -> CollectionStatusOut:
        return cls(
            packages_loaded=status.packages_loaded,
            latest_package=status.latest_package,
            latest_loaded_at=status.latest_loaded_at,
            laws=status.laws,
            units=status.units,
            volumes=list(status.volumes),
            congresses=list(status.congresses),
            laws_by_congress={congress: laws for congress, laws in status.laws_by_congress},
        )


class SourceCheckOut(BaseModel):
    checked_at: datetime.datetime
    ok: bool
    newest_package: str | None
    newest_last_modified: datetime.datetime | None
    packages_seen: int | None
    new_packages: list[str] = Field(default_factory=list)
    error: str | None
    stale: bool = Field(description="True when the check failed or is over a week old.")

    @classmethod
    def of(cls, check: SourceCheckInfo) -> SourceCheckOut:
        return cls(
            checked_at=check.checked_at,
            ok=check.ok,
            newest_package=check.newest_package,
            newest_last_modified=check.newest_last_modified,
            packages_seen=check.packages_seen,
            new_packages=list(check.new_packages),
            error=check.error,
            stale=check.is_stale(),
        )


class CitationsStatusOut(BaseModel):
    """The citation index: rows, citing sections, titles, the release labels."""

    rows: int
    citing_sections: int
    titles: int
    release_labels: list[list[Any]] = Field(
        default_factory=list, description="`[label, rows]` pairs, most rows first; the first 10."
    )
    loaded_at: datetime.datetime | None = Field(description="When the index was last built.")
    checked_at: datetime.datetime | None = Field(
        description="When the dataset was last asked about, whether or not it was reloaded."
    )
    dataset_revision: str | None = Field(description="The `dreamproit/uscode` commit the index was built from.")

    @classmethod
    def of(cls, status: CitationIndexStatus) -> CitationsStatusOut:
        return cls(
            rows=status.rows,
            citing_sections=status.citing_sections,
            titles=status.titles,
            release_labels=[[label, rows] for label, rows in status.release_labels[:10]],
            loaded_at=status.loaded_at,
            checked_at=status.checked_at,
            dataset_revision=status.dataset_revision,
        )


class ClassificationFileOut(BaseModel):
    congress: int
    session: int = Field(description="`1`, `2`; `0` for a whole-congress table.")
    covered_laws_text: str | None = Field(examples=["Public Laws 118-35 to 118-274"])
    row_count: int
    mirrored_at: datetime.datetime

    @classmethod
    def of(cls, file: ClassificationFileRef) -> ClassificationFileOut:
        return cls(
            congress=file.congress,
            session=file.session,
            covered_laws_text=file.covered_laws_text,
            row_count=file.row_count,
            mirrored_at=file.mirrored_at,
        )


class ClassificationCheckOut(BaseModel):
    checked_at: datetime.datetime
    ok: bool
    files_seen: int | None
    files_loaded: int | None
    rows_loaded: int | None
    upstream_checked_at: datetime.datetime | None = Field(
        description="The US Code site's own last check of uscode.house.gov."
    )
    error: str | None
    stale: bool = Field(description="True when the run failed or is over a week old.")

    @classmethod
    def of(cls, check: ClassificationCheckInfo) -> ClassificationCheckOut:
        return cls(
            checked_at=check.checked_at,
            ok=check.ok,
            files_seen=check.files_seen,
            files_loaded=check.files_loaded,
            rows_loaded=check.rows_loaded,
            upstream_checked_at=check.upstream_checked_at,
            error=check.error,
            stale=check.is_stale(),
        )


class ClassificationsStatusOut(BaseModel):
    """The classification tables mirror: the files held, their rows, the last run."""

    files: list[ClassificationFileOut] = Field(default_factory=list)
    rows: int
    congresses: list[int] = Field(default_factory=list)
    last_check: ClassificationCheckOut | None

    @classmethod
    def of(cls, status: ClassificationStatus) -> ClassificationsStatusOut:
        return cls(
            files=[ClassificationFileOut.of(f) for f in status.files],
            rows=status.rows,
            congresses=list(status.congresses),
            last_check=ClassificationCheckOut.of(status.last_check) if status.last_check is not None else None,
        )


class StatusOut(BaseModel):
    collections: dict[str, CollectionStatusOut] = Field(description="Keyed `STATUTE`, `COMPS`, `PLAW`.")
    checks: dict[str, SourceCheckOut | None] = Field(
        description="The last poll of each collection's source; null when none is recorded."
    )
    stale: bool = Field(
        description="True when any collection with loaded packages has no check or a stale one."
    )
    citations: CitationsStatusOut
    classifications: ClassificationsStatusOut


# ----------------------------------------------------------------- cited-by


class CitedRefOut(BaseModel):
    href: str = Field(
        description="The ref's target as the citing text wrote it.", examples=["/us/pl/104/333/dI/tVIII/s814/e/1"]
    )
    context: str = Field(description="`sourceCredit` | `note` | `text`.")
    note_topic: str | None = Field(default=None, description="The note's topic, for a `note` ref.")
    date: datetime.date | None = Field(default=None, description="The law's date as the citing text gives it.")


class CitingSectionOut(BaseModel):
    identifier: str = Field(examples=["/us/usc/t16/s1"])
    citation: str | None = Field(examples=["16 U.S.C. 1"])
    heading: str | None
    release_label: str = Field(description="The release point of the citing section's title.")
    url: str
    refs: list[CitedRefOut]

    @classmethod
    def of(cls, section: CitingSection, *, url: str) -> CitingSectionOut:
        return cls(
            identifier=section.identifier,
            citation=section.citation,
            heading=section.heading,
            release_label=section.release_label,
            url=url,
            refs=[
                CitedRefOut(href=r.to_identifier, context=r.context, note_topic=r.note_topic, date=r.to_date)
                for r in section.refs
            ],
        )


class CitationIndexOut(BaseModel):
    release_labels: list[list[Any]] = Field(
        default_factory=list, description="`[label, rows]` pairs, the ten labels with most rows; `/status` lists the same ten."
    )
    loaded_at: datetime.datetime | None
    dataset_revision: str | None

    @classmethod
    def of(cls, status: CitationIndexStatus) -> CitationIndexOut:
        return cls(
            release_labels=[[label, rows] for label, rows in status.release_labels[:10]],
            loaded_at=status.loaded_at,
            checked_at=status.checked_at,
            dataset_revision=status.dataset_revision,
        )


class CitedByOut(BaseModel):
    """US Code sections whose refs point at a law, a section of it, or a
    Statutes at Large page (design section 5)."""

    identifier: str = Field(description="The identifier asked for, normalized.")
    law_identifier: str = Field(description="The law's primary form when it is loaded, else the form asked for.")
    law: LawOut | None = Field(description="Null when the law is not loaded; the index still answers.")
    aliases: list[str] = Field(description="Every identifier the citing side may have used for the law.")
    section_num: str | None
    below: str | None = Field(description="The path below the section that was asked for (`e/1`), when any.")
    contexts: dict[str, int] = Field(description="Matching refs per context, over the whole answer.")
    total: int = Field(description="Distinct citing sections over the contexts asked for.")
    limit: int
    offset: int
    release_labels: list[str] = Field(description="The release points the citing sections come from.")
    index: CitationIndexOut
    sections: list[CitingSectionOut] = Field(description="One page of citing sections, in identifier order.")
    note: str

    @classmethod
    def of(
        cls,
        answer: CitedBy,
        *,
        identifier: str,
        limit: int,
        offset: int,
        index: CitationIndexStatus,
        section_url: Callable[[str], str],
        note: str,
    ) -> CitedByOut:
        return cls(
            identifier=identifier,
            law_identifier=answer.law_identifier,
            law=LawOut.of(answer.law) if answer.law is not None else None,
            aliases=list(answer.aliases),
            section_num=answer.section_num,
            below=answer.below,
            contexts=dict(answer.contexts),
            total=answer.total,
            limit=limit,
            offset=offset,
            release_labels=list(answer.release_labels),
            index=CitationIndexOut.of(index),
            sections=[CitingSectionOut.of(s, url=section_url(s.identifier)) for s in answer.sections],
            note=note,
        )


# ---------------------------------------------------------------------- cite


class CiteOut(BaseModel):
    """A written citation resolved to the identifier it names, and whether
    that is loaded (design section 5; `citeparse`)."""

    query: str
    kind: str = Field(description="`pl` | `pvtl` | `act` | `stat` | `sComp` | `usc`; a chapter cited with its page answers with the law's kind.")
    identifier: str = Field(description="The deepest thing the citation named; for a chapter on a page, the law found there.")
    section_identifier: str = Field(description="The section containing `identifier` when the citation went below one.")
    law_identifier: str | None = Field(description="The law's primary identifier when it is loaded, else the form the citation named.")
    label: str = Field(description="The citation in this site's written form.", examples=["Public Law 104-333, section 814(e)(1)"])
    exists: bool | None = Field(description="Whether the target is loaded; null for a US Code citation, which is not checked here.")
    served_identifier: str | None = Field(description="The stored unit or page that answers, on a hit.")
    resolution: str | None = Field(description="`exact` | `prefix` | `section_number` | `alias` (design section 3), on a hit.")
    level: str | None
    num: str | None
    heading: str | None
    law_label: str | None
    url: str | None = Field(description="The citation URL on a hit; the US Code site's URL for a US Code citation; null on a miss.")
    stat_page: str | None = Field(description="A Stat. page the citation gave beside a law, not resolved.")
    hierarchy: list[str] = Field(default_factory=list, description="The hierarchy the citation wrote, as GPO segments; not in the identifier.")
    note: str
    message: str | None = Field(description="Something specific about a hit that did not land exactly: a provision missing from its section, a chapter absent from its page.")

    @classmethod
    def of(
        cls,
        parsed: ParsedCitation,
        query: str,
        *,
        exists: bool | None,
        note: str,
        identifier: str | None = None,
        section_identifier: str | None = None,
        kind: str | None = None,
        label: str | None = None,
        served_identifier: str | None = None,
        resolution: str | None = None,
        level: str | None = None,
        num: str | None = None,
        heading: str | None = None,
        law_identifier: str | None = None,
        law_label: str | None = None,
        url: str | None = None,
        message: str | None = None,
    ) -> CiteOut:
        return cls(
            query=query,
            kind=kind or parsed.kind,
            identifier=identifier or parsed.identifier,
            section_identifier=section_identifier or (parsed.section_identifier if identifier is None else identifier),
            law_identifier=law_identifier or parsed.law_identifier,
            label=label or parsed.label,
            exists=exists,
            served_identifier=served_identifier,
            resolution=resolution,
            level=level,
            num=num,
            heading=heading,
            law_label=law_label,
            url=url,
            stat_page=parsed.stat_page,
            hierarchy=list(parsed.hierarchy),
            note=note,
            message=message,
        )
