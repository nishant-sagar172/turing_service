"""phone_number_catalog and client_phone_numbers tables for per-client number assignment

Revision ID: 0003_phone_number_catalog
Revises: 0002_widen_batch_status
Create Date: 2026-08-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003_phone_number_catalog"
down_revision = "0002_widen_batch_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_number_catalog",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("telephony_provider", sa.String(64), nullable=True),
        sa.Column("rented", sa.Boolean, nullable=True),
        sa.Column("renewal_at", sa.String(64), nullable=True),
        sa.Column("is_present", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("snapshot", JSONB, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("phone_number", name="uq_phone_number_catalog_number"),
    )

    op.create_table(
        "client_phone_numbers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("phone_number_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["phone_number_id"], ["phone_number_catalog.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("client_id", "phone_number_id",
                            name="uq_client_phone_number"),
    )
    op.create_index("ix_client_phone_numbers_client_id",
                    "client_phone_numbers", ["client_id"])
    op.create_index("ix_client_phone_numbers_phone_number_id",
                    "client_phone_numbers", ["phone_number_id"])


def downgrade() -> None:
    op.drop_table("client_phone_numbers")
    op.drop_table("phone_number_catalog")
