"""thesis: deterministic price exit thresholds

Adds stop_below / take_above to the theses table. Free-text exit_if conditions are judged by the
LLM, which is right for "has the capex been cut?" and wrong for a stop loss — `ltp <= 275` is
arithmetic and must not depend on a model's daily reading. Nullable, so existing theses are
unaffected until a threshold is set.

Revision ID: e7a3c1d95b24
Revises: c4e9a1f2b8d0
"""

from alembic import op
import sqlalchemy as sa

revision = "e7a3c1d95b24"
down_revision = "c4e9a1f2b8d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("theses", sa.Column("stop_below", sa.Float(), nullable=True))
    op.add_column("theses", sa.Column("take_above", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("theses", "take_above")
    op.drop_column("theses", "stop_below")
