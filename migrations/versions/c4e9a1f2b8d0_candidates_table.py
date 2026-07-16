"""candidates table (Phase 6 weekly screener)

Revision ID: c4e9a1f2b8d0
Revises: 1378b2c69550
Create Date: 2026-07-16 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e9a1f2b8d0'
down_revision: Union[str, None] = '1378b2c69550'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('candidates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_date', sa.Date(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=True),
    sa.Column('composite', sa.Float(), nullable=True),
    sa.Column('buckets', sa.JSON(), nullable=True),
    sa.Column('market_cap', sa.Float(), nullable=True),
    sa.Column('excluded', sa.Integer(), nullable=True),
    sa.Column('red_flags', sa.JSON(), nullable=True),
    sa.Column('detail', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_candidates_run_date'), 'candidates', ['run_date'], unique=False)
    op.create_index(op.f('ix_candidates_symbol'), 'candidates', ['symbol'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_candidates_symbol'), table_name='candidates')
    op.drop_index(op.f('ix_candidates_run_date'), table_name='candidates')
    op.drop_table('candidates')
