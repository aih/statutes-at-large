"""source_checks.source_sha256: the sha of the volume file a load read

Revision ID: 9c1f2b7d3e40
Revises: 4381d4019386
Create Date: 2026-09-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c1f2b7d3e40'
down_revision: Union[str, None] = '4381d4019386'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('source_checks', sa.Column('source_sha256', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('source_checks', 'source_sha256')
