"""Storage layer: the `Repository` interface and its implementation.

`api/` imports from here and never from `db/`. `ingest/` is on the other side
of the boundary and writes `db/` models directly.
"""

from storage.identifiers import (
    ParsedIdentifier,
    StatPageId,
    law_label,
    long_date,
    normalize_identifier,
    normalize_page,
    parse_identifier,
    parse_stat_page,
)
from storage.postgres import PostgresRepository
from storage.repository import (
    GOVINFO_COMPS_DETAILS,
    GOVINFO_PLAW_LINK,
    GOVINFO_STATUTE_LINK,
    SOURCE_CHECK_STALE_AFTER,
    CollectionStatus,
    CompCounterpart,
    CompRef,
    CompUnitResult,
    CompVersionRef,
    LabelInfo,
    LawRef,
    LawSummary,
    PageRef,
    Provision,
    Repository,
    RepositoryError,
    RepositoryUnavailableError,
    SourceCheckInfo,
    StatPageDocument,
    StatPageResult,
    UnitRef,
    UnitResult,
)
from storage.session import get_repository

__all__ = [
    "GOVINFO_COMPS_DETAILS",
    "GOVINFO_PLAW_LINK",
    "GOVINFO_STATUTE_LINK",
    "SOURCE_CHECK_STALE_AFTER",
    "CollectionStatus",
    "CompCounterpart",
    "CompRef",
    "CompUnitResult",
    "CompVersionRef",
    "LabelInfo",
    "LawRef",
    "LawSummary",
    "PageRef",
    "ParsedIdentifier",
    "PostgresRepository",
    "Provision",
    "Repository",
    "RepositoryError",
    "RepositoryUnavailableError",
    "SourceCheckInfo",
    "StatPageDocument",
    "StatPageId",
    "StatPageResult",
    "UnitRef",
    "UnitResult",
    "get_repository",
    "law_label",
    "long_date",
    "normalize_identifier",
    "normalize_page",
    "parse_identifier",
    "parse_stat_page",
]
