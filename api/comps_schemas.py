"""Response models of the compiled view (design section 4) and the `/comps`
listings (section 5)."""

from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CurrentThroughOut(BaseModel):
    pl: str | None = Field(None, description="`118-67`: the public law the compilation incorporates amendments through.")
    enacted: datetime.date | None = Field(None, description="That law's enactment date.")


class CompVersionOut(BaseModel):
    current_through: CurrentThroughOut
    fetched: datetime.date | None = Field(None, description="The day this version was fetched from GovInfo.")
    govinfo_last_modified: str | None = None
    is_current: bool
    url: str = Field(description="This identifier pinned to the version with `?through=`.")


class UnitRefOut(BaseModel):
    identifier: str
    level: str
    num: str | None = None
    heading: str | None = None
    is_section: bool = False


class CompOut(BaseModel):
    file_id: str
    package_id: str
    identifier_prefix: str
    display_title: str | None = None
    title: str | None = None
    short_titles: list[str] = []
    law_identifier: str | None = Field(None, description="The enacted law this compiles, when it is loaded.")
    partial_of: str | None = Field(None, description="The title designator when the file is one title of a larger act.")
    current_through: CurrentThroughOut | None = None
    govinfo_last_modified: str | None = None
    url: str
    govinfo_details: str


class CompListOut(BaseModel):
    comps: list[CompOut]


class CompDetailOut(CompOut):
    versions: list[CompVersionOut] = []
    toc: list[UnitRefOut] | None = Field(None, description="The top-level units of the current version; null when the file cannot be told apart from another with the same prefix.")


class CompilationOut(BaseModel):
    file_id: str
    package_id: str
    display_title: str | None = None
    short_titles: list[str] = []
    identifier_prefix: str
    law_identifier: str | None = None
    partial_of: str | None = None
    govinfo_details: str


class LawOut(BaseModel):
    congress: int | None = None
    number: int | None = Field(None, description="The public-law number, or the chapter number for an act before 1901.")
    identifier: str | None = Field(None, description="`/us/pl/83/703`; the loaded law's identifier when it is loaded.")
    loaded: bool = False


class CurrencyOut(BaseModel):
    kind: Literal["compiled"] = "compiled"
    current_through: CurrentThroughOut
    fetched: datetime.date | None = None
    govinfo_last_modified: str | None = None


class ProvenanceOut(BaseModel):
    text: str
    identifiers: str
    sha256: str


class ProvisionOut(BaseModel):
    identifier: str
    found: bool
    text: str | None = None
    xml: str | None = None


class CompUnitOut(BaseModel):
    identifier: str
    served_identifier: str
    view: Literal["compiled"] = "compiled"
    resolution: str
    compilation: CompilationOut
    law: LawOut
    currency: CurrencyOut
    versions: list[CompVersionOut]
    alternatives: list[dict[str, Any]]
    note: str
    provenance: ProvenanceOut
    usc_refs: list[str]
    text: str = Field(
        description="The served unit's reading text. Empty for `level: \"compilation\"` and for a hierarchy "
        "level; a section (and a `provision`) carries its own text."
    )
    xml_url: str
    level: str
    num: str | None = None
    heading: str | None = None
    section_num: str | None = None
    ancestors: list[UnitRefOut]
    children: list[UnitRefOut]
    provision: ProvisionOut | None = None
    files: list[CompilationOut] = Field(
        default=[],
        description="On a compilation root with no whole-act file, the per-title files the answer gathers, in "
        "title order; `compilation` then names the first of them with the act's title and no `partial_of`, "
        "and `children` are every file's top-level units. Empty when the answer comes from one file.",
    )
