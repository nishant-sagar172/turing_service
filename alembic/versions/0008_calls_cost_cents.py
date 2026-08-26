"""Add calls.cost_cents (integer minor units) alongside the float cost column

``calls.cost`` is a binary Float that analytics sums and averages across
potentially thousands of rows. Binary floats cannot represent most decimal cents
exactly, so aggregated totals — figures a client reconciles against an invoice —
accumulate rounding error as volume grows.

This migration is deliberately ADDITIVE ONLY. ``cost`` is neither dropped nor
stopped being written, and no API response changes: the application dual-writes
both columns, and readers migrate to ``cost_cents`` in a later release. That
keeps this step reversible with no data loss.

Revision ID: 0008_calls_cost_cents
Revises: 0007_calls_client_created_index
Create Date: 2026-08-12

"""
from alembic import op
import sqlalchemy as sa

revision = "0008_calls_cost_cents"
down_revision = "0007_calls_client_created_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("cost_cents", sa.Integer(), nullable=True))
    # Backfill from the existing float. ROUND before casting so 2.499999 lands
    # on 250 rather than truncating to 249.
    op.execute(
        "UPDATE calls SET cost_cents = ROUND(cost * 100)::integer "
        "WHERE cost IS NOT NULL AND cost_cents IS NULL"
    )


def downgrade() -> None:
    op.drop_column("calls", "cost_cents")
