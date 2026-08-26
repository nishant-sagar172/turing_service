"""Add composite index on calls (client_id, created_at) for analytics

Every analytics query filters ``Call.created_at`` within a date range on top of
the tenant filter, and ``get_timeseries`` additionally groups by
``date_trunc(..., created_at)``. ``calls`` was indexed on ``client_id``,
``batch_id``, ``contact_number``, ``patient_ref`` and ``voice_call_id`` but not
``created_at``, so every analytics call scanned all of a client's rows to apply
the date filter. One composite index serves both predicates.

Built CONCURRENTLY: a plain CREATE INDEX takes ACCESS EXCLUSIVE on the table
and would block all writes to ``calls`` for the duration of the build, which on
a populated table means a live outage of the webhook/reconcile write path.
CONCURRENTLY cannot run inside a transaction, hence the autocommit block.

Revision ID: 0007_calls_client_created_index
Revises: 0006_call_analysis_urgency
Create Date: 2026-08-12

"""
from alembic import op

revision = "0007_calls_client_created_index"
down_revision = "0006_call_analysis_urgency"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_calls_client_created"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX_NAME,
            "calls",
            ["client_id", "created_at"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            INDEX_NAME,
            table_name="calls",
            postgresql_concurrently=True,
            if_exists=True,
        )
