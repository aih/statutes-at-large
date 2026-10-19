"""ix_citations_to_congress: index on citations.to_congress (Issue #19)

Revision ID: d8e3c7b1a209
Revises: b7e2c4a91f05
Create Date: 2026-10-19 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8e3c7b1a209'
down_revision: Union[str, None] = 'b7e2c4a91f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_citations_to_congress', 'citations', ['to_congress'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_citations_to_congress', table_name='citations')
