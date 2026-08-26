"""widen batches.status — the voice engine's schedule/stop confirmation
messages (e.g. "scheduled at 2026-07-25T22:00:00+05:30") are descriptive
sentences, not short status codes, and didn't fit the original 32-char column.

Revision ID: 0002_widen_batch_status
Revises: 0001_initial
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_widen_batch_status"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("batches", "status", type_=sa.String(128))


def downgrade() -> None:
    op.alter_column("batches", "status", type_=sa.String(32))
