"""laws.public_private, and an act's congress from its approval date (ADR-0033)

Revision ID: e4a1c9d27b63
Revises: b7e2c4a91f05
Create Date: 2026-10-19 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a1c9d27b63'
down_revision: Union[str, None] = 'b7e2c4a91f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# `ingest.identifiers.congress_of_act` in SQL: the Congress sitting on the
# approval date (a term began March 4 of an odd year until 1935, January 3
# since), except on the March 4 a term ended when the stored congress is the
# outgoing one.
_TERM_YEAR = """
    CASE WHEN to_char(enacted, 'MM-DD') >= CASE WHEN enacted < DATE '1935-01-03' THEN '03-04' ELSE '01-03' END
         THEN extract(year FROM enacted)::int
         ELSE extract(year FROM enacted)::int - 1 END
"""
_DATED = f"((({_TERM_YEAR}) - 1 + ({_TERM_YEAR}) % 2 - 1789) / 2 + 1)"


def upgrade() -> None:
    op.add_column('laws', sa.Column('public_private', sa.Text(), nullable=True))
    # A stored law's XML is its whole `pLaw`, `meta` first, so the first
    # `publicPrivate` is the law's own. The loaders set the column from here on.
    op.execute(
        "UPDATE laws SET public_private = substring(xml from '<publicPrivate>(public|private)</publicPrivate>')"
    )
    op.execute(
        f"""
        UPDATE laws SET congress = {_DATED}
        WHERE kind = 'act' AND enacted IS NOT NULL
          AND congress IS DISTINCT FROM {_DATED}
          AND NOT (enacted < DATE '1935-01-03' AND to_char(enacted, 'MM-DD') = '03-04'
                   AND extract(year FROM enacted)::int % 2 = 1 AND coalesce(congress, -1) = {_DATED} - 1)
        """
    )


def downgrade() -> None:
    # The congress an act had before is not kept; a volume reload restores
    # whatever the loader then decides.
    op.drop_column('laws', 'public_private')
