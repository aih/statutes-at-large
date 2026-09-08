"""The schema (design section 6). `storage/` reads it; `ingest/` writes it.

Column types are the portable SQLAlchemy ones (`Text`, `JSON`, `Date`,
`DateTime`) rather than Postgres dialect types, so the same models run the test
suite over SQLite and the deployment over Postgres.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Law(Base):
    """One enacted law: a public law, a private law, or a chapter-numbered act."""

    __tablename__ = "laws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    """The primary identifier: `/us/pl/81/443`, `/us/pvtl/81/375`,
    `/us/act/1890-07-02/ch647`."""

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    """`pl` | `pvtl` | `act`. A string, not an enum."""

    congress: Mapped[int | None] = mapped_column(Integer)
    number: Mapped[int | None] = mapped_column(Integer)
    """Public- or private-law number. Null for a chapter-only act."""

    chapter: Mapped[int | None] = mapped_column(Integer)
    """Chapter number, for laws through 1957."""

    enacted: Mapped[datetime.date | None] = mapped_column(Date)
    doc_type: Mapped[str | None] = mapped_column(Text)
    """`An Act` | `Joint Resolution`, as the long title names it."""

    official_title: Mapped[str | None] = mapped_column(Text)
    short_titles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    stat_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    stat_page_first: Mapped[str | None] = mapped_column(Text)
    """Page label, lower case: `919`, `b3`."""
    stat_page_last: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(Text)
    """`68 Stat. 919`."""

    source_collection: Mapped[str] = mapped_column(Text, nullable=False)
    source_package: Mapped[str] = mapped_column(Text, nullable=False)
    source_granule: Mapped[str | None] = mapped_column(Text)
    seq_in_volume: Mapped[int] = mapped_column(Integer, nullable=False)

    provenance_text: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_identifiers: Mapped[str] = mapped_column(Text, nullable=False)
    xml: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    loaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    aliases: Mapped[list["LawAlias"]] = relationship(
        back_populates="law", cascade="all, delete-orphan"
    )
    units: Mapped[list["Unit"]] = relationship(
        back_populates="law", cascade="all, delete-orphan", order_by="Unit.seq"
    )

    __table_args__ = (
        Index("ix_laws_congress_number", "congress", "number"),
        Index("ix_laws_volume_seq", "stat_volume", "seq_in_volume"),
    )


class LawAlias(Base):
    """Every identifier a law answers to, the primary one included.

    A law from 1901 to 1957 has a public-law number and a chapter number; both
    forms resolve here (design section 3, rule 4).
    """

    __tablename__ = "law_aliases"

    identifier: Mapped[str] = mapped_column(Text, primary_key=True)
    law_id: Mapped[int] = mapped_column(
        ForeignKey("laws.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    law: Mapped[Law] = relationship(back_populates="aliases")


class Unit(Base):
    """A structural node or a section of a law.

    Sections are the storage atom: `xml` is set for sections and holds the
    section with `identifier` attributes stamped on every level below it.
    Sub-section paths are cut from the section at request time. Hierarchy nodes
    (division, title, chapter, ...) carry heading and order and no XML.
    """

    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    law_id: Mapped[int] = mapped_column(
        ForeignKey("laws.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    """Relative to the law's primary identifier: `/us/pl/81/740/s3`."""

    occurrence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    """1 for the first element with this identifier in the law; 2, 3, ... when the
    source numbers two sections alike."""

    parent_identifier: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    """`section` | `division` | `title` | `subtitle` | `chapter` | ..."""

    num: Mapped[str | None] = mapped_column(Text)
    """The designator value: `3`, `I`, `A`."""

    heading: Mapped[str | None] = mapped_column(Text)
    section_num: Mapped[str | None] = mapped_column(Text)
    """For sections: `num`, for the section-number index (rule 3)."""

    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    ancestors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    """`[{identifier, level, num, heading}, ...]` from the law down to the
    parent."""

    xml: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    first_page: Mapped[str | None] = mapped_column(Text)
    """Stat. page label the unit starts on."""
    pages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    """Every page label a marker inside the unit names, in order."""

    law: Mapped[Law] = relationship(back_populates="units")

    __table_args__ = (
        UniqueConstraint("identifier", "occurrence", name="uq_units_identifier"),
        Index("ix_units_law_section_num", "law_id", "section_num"),
    )


class StatPage(Base):
    """Which laws start on or span a Statutes at Large page."""

    __tablename__ = "stat_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[str] = mapped_column(Text, nullable=False)
    """Lower-case label: `921`, `b3`."""
    law_id: Mapped[int] = mapped_column(
        ForeignKey("laws.id", ondelete="CASCADE"), nullable=False, index=True
    )
    starts_here: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unit_identifier: Mapped[str | None] = mapped_column(Text)
    """The unit inside which the page marker falls, when it falls inside one."""

    __table_args__ = (
        UniqueConstraint("volume", "page", "law_id", name="uq_stat_pages"),
        Index("ix_stat_pages_volume_page", "volume", "page"),
    )


class Comp(Base):
    """A Statute Compilation package from GovInfo `COMPS`."""

    __tablename__ = "comps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    """`meta/property[@role='fileId']`: `1630`."""
    package_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    """`COMPS-1630`."""

    identifier_prefix: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    """`/us/sComp/83/703`, from the compilation's own identifiers."""
    law_congress: Mapped[int | None] = mapped_column(Integer)
    law_number: Mapped[int | None] = mapped_column(Integer)
    """The second number of the prefix: a public-law number, or a chapter number
    for an act before public-law numbering (`/us/sComp/51/647`)."""
    law_id: Mapped[int | None] = mapped_column(
        ForeignKey("laws.id", ondelete="SET NULL"), index=True
    )

    title: Mapped[str | None] = mapped_column(Text)
    display_title: Mapped[str | None] = mapped_column(Text)
    short_titles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    approved_date: Mapped[datetime.date | None] = mapped_column(Date)
    partial_of: Mapped[str | None] = mapped_column(Text)
    """For a compilation split into one file per title: the title designator
    (`II`), else null."""

    versions: Mapped[list["CompVersion"]] = relationship(
        back_populates="comp", cascade="all, delete-orphan", order_by="CompVersion.id"
    )


class CompVersion(Base):
    """One fetched state of a compilation. A new row whenever the
    `currentThroughPublicLaw` or the content hash changes."""

    __tablename__ = "comp_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comp_id: Mapped[int] = mapped_column(
        ForeignKey("comps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_through_pl: Mapped[str | None] = mapped_column(Text)
    """`118-67`, hyphen."""
    current_through_date: Mapped[datetime.date | None] = mapped_column(Date)
    govinfo_last_modified: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    xml: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    comp: Mapped[Comp] = relationship(back_populates="versions")
    units: Mapped[list["CompUnit"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="CompUnit.seq"
    )

    __table_args__ = (
        UniqueConstraint("comp_id", "content_hash", name="uq_comp_versions_hash"),
    )


class CompUnit(Base):
    """A structural node or section of one compilation version."""

    __tablename__ = "comp_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comp_version_id: Mapped[int] = mapped_column(
        ForeignKey("comp_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    """`/us/sComp/83/703/tI/ch1./s1`, as GPO wrote it."""
    parent_identifier: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    num: Mapped[str | None] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text)
    section_num: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    ancestors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    xml: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    usc_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    """`/us/usc/...` hrefs of the section's `editorialNote[@role='uscRef']`."""

    version: Mapped[CompVersion] = relationship(back_populates="units")

    __table_args__ = (
        UniqueConstraint(
            "comp_version_id", "identifier", name="uq_comp_units_identifier"
        ),
        Index("ix_comp_units_identifier", "identifier"),
        Index("ix_comp_units_version_section", "comp_version_id", "section_num"),
    )


class SourceCheck(Base):
    """One poll of a source collection, successful or not (a row either way)."""

    __tablename__ = "source_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    """`STATUTE` | `COMPS` | `PLAW`."""
    checked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    newest_last_modified: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    newest_package: Mapped[str | None] = mapped_column(Text)
    packages_seen: Mapped[int | None] = mapped_column(Integer)
    new_packages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
