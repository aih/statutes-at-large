"""data_version, its triggers, congress_summaries, and two covering indexes (ADR-0037)

Revision ID: c5d0e7a3f218
Revises: e4a1c9d27b63
Create Date: 2026-10-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d0e7a3f218'
down_revision: Union[str, None] = 'e4a1c9d27b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The tables the Congress summaries read; a write to any of them moves the stamp.
TABLES = (
    'laws',
    'units',
    'law_aliases',
    'comps',
    'citations',
    'classifications',
    'classification_files',
    'pending_laws',
)


def upgrade() -> None:
    op.create_table(
        'data_version',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('changed_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute("INSERT INTO data_version (id, version, changed_at) VALUES (1, 0, clock_timestamp()::text)")
    op.create_table(
        'congress_summaries',
        sa.Column('congress', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('changed_at', sa.Text(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('congress'),
    )
    # Once per transaction: the first write sets a transaction-local flag.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bump_data_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('statutes.data_version_bumped', true) IS DISTINCT FROM 'on' THEN
                UPDATE data_version SET version = version + 1, changed_at = clock_timestamp()::text WHERE id = 1;
                PERFORM set_config('statutes.data_version_bumped', 'on', true);
            END IF;
            RETURN NULL;
        END
        $$
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER data_version_{table} AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION bump_data_version()"
        )
    # Index-only scans for the section count and the citation counts.
    op.create_index('ix_units_level_law', 'units', ['level', 'law_id'])
    op.create_index('ix_citations_to_law_from', 'citations', ['to_law', 'from_identifier', 'from_title'])


def downgrade() -> None:
    op.drop_index('ix_citations_to_law_from', table_name='citations')
    op.drop_index('ix_units_level_law', table_name='units')
    for table in TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS data_version_{table} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS bump_data_version()")
    op.drop_table('congress_summaries')
    op.drop_table('data_version')
