"""Add calls.client_ref — the client's own row id, echoed back on the outcome.

The voice engine returns every non-``contact_number`` CSV column under
``context_details.recipient_data``, so a client that sends its own record id as
a column can be handed it back. Without it a client matching a batch outcome to
its own row has only ``patient_ref`` and the phone number, which cannot separate
two recipients sharing a number when neither carries a patient id.

Additive and nullable: existing rows stay NULL and every existing client keeps
working unchanged.

Revision ID: 0014_call_client_ref
Revises: 0013_call_notified_at
Create Date: 2026-09-18

"""

import sqlalchemy as sa
from alembic import op

revision = "0014_call_client_ref"
down_revision = "0013_call_notified_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("client_ref", sa.String(length=128), nullable=True))
    op.create_index("ix_calls_client_ref", "calls", ["client_ref"])


def downgrade() -> None:
    op.drop_index("ix_calls_client_ref", table_name="calls")
    op.drop_column("calls", "client_ref")
