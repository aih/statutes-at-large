"""The `alternatives` list of a response: the other views of the same provision
(design section 4). Stage 1 has no compiled or codified counterparts loaded,
so the list is empty; stage 2 fills it from `Repository.compiled_counterparts`.
"""

from __future__ import annotations

from api.schemas import AlternativeOut
from storage import Repository, UnitResult


def alternatives_for(repository: Repository, result: UnitResult) -> list[AlternativeOut]:
    """The other views available for an enacted unit."""
    return []
