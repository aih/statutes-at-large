"""pending_laws: public laws Congress.gov lists that are not loaded (ADR-0031)

Revision ID: b7e2c4a91f05
Revises: 9c1f2b7d3e40
Create Date: 2026-10-13 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2c4a91f05'
down_revision: Union[str, None] = '9c1f2b7d3e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pending_laws',
        sa.Column('identifier', sa.Text(), nullable=False),
        sa.Column('congress', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('bill_type', sa.Text(), nullable=False),
        sa.Column('bill_number', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('action_date', sa.Date(), nullable=True),
        sa.Column('congress_gov_url', sa.Text(), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('identifier'),
    )
    op.create_index(op.f('ix_pending_laws_congress'), 'pending_laws', ['congress'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pending_laws_congress'), table_name='pending_laws')
    op.drop_table('pending_laws')
