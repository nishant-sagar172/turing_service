"""initial schema: clients, agent catalog, batches, calls, request_logs

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("contact_email", sa.String(256), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_clients_name", "clients", ["name"])
    op.create_unique_constraint("uq_clients_slug", "clients", ["slug"])

    op.create_table(
        "client_api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_client_api_keys_client_id", "client_api_keys", ["client_id"])
    op.create_index("ix_client_api_keys_key_prefix", "client_api_keys", ["key_prefix"])
    op.create_unique_constraint("uq_client_api_keys_key_hash", "client_api_keys",
                                 ["key_hash"])

    op.create_table(
        "client_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visible_fields", JSONB, nullable=True),
        sa.Column("default_from_number", sa.String(32), nullable=True),
        sa.Column("webhook_url", sa.Text, nullable=True),
        sa.Column("webhook_secret", sa.String(128), nullable=True),
        sa.Column("settings", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_client_config_client_id", "client_config",
                                 ["client_id"])

    op.create_table(
        "agent_catalog",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("voice_agent_id", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(256), nullable=True),
        sa.Column("agent_status", sa.String(32), nullable=True),
        sa.Column("snapshot", JSONB, nullable=True),
        sa.Column("is_present", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_agent_catalog_voice_agent_id", "agent_catalog",
                                 ["voice_agent_id"])

    op.create_table(
        "client_agent_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voice_agent_id", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("variable_overrides", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_client_agent_config_client_id", "client_agent_config",
                     ["client_id"])
    op.create_index("ix_client_agent_config_voice_agent_id", "client_agent_config",
                     ["voice_agent_id"])
    op.create_unique_constraint("uq_client_agent", "client_agent_config",
                                 ["client_id", "voice_agent_id"])

    op.create_table(
        "agent_drift_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("voice_agent_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_drift_events_client_id", "agent_drift_events",
                     ["client_id"])
    op.create_index("ix_agent_drift_events_voice_agent_id", "agent_drift_events",
                     ["voice_agent_id"])

    op.create_table(
        "batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("from_number", sa.String(32), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False, server_default="batch"),
        sa.Column("retry_config", JSONB, nullable=True),
        sa.Column("voice_batch_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("valid_count", sa.Integer, nullable=True),
        sa.Column("scheduled_at", sa.String(64), nullable=True),
        sa.Column("recipients_snapshot", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_batches_client_id", "batches", ["client_id"])
    op.create_index("ix_batches_voice_batch_id", "batches", ["voice_batch_id"])
    op.create_unique_constraint("uq_batch_client_voice_id", "batches",
                                 ["client_id", "voice_batch_id"])

    op.create_table(
        "calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True),
                  sa.ForeignKey("batches.id"), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("contact_number", sa.String(32), nullable=True),
        sa.Column("patient_ref", sa.String(128), nullable=True),
        sa.Column("voice_call_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("recording_url", sa.Text, nullable=True),
        sa.Column("extracted_data", JSONB, nullable=True),
        sa.Column("cost", sa.Float, nullable=True),
        sa.Column("duration", sa.Float, nullable=True),
        sa.Column("hangup_reason", sa.String(128), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_calls_client_id", "calls", ["client_id"])
    op.create_index("ix_calls_batch_id", "calls", ["batch_id"])
    op.create_index("ix_calls_contact_number", "calls", ["contact_number"])
    op.create_index("ix_calls_patient_ref", "calls", ["patient_ref"])
    op.create_index("ix_calls_voice_call_id", "calls", ["voice_call_id"])
    op.create_unique_constraint("uq_call_client_voice_id", "calls",
                                 ["client_id", "voice_call_id"])

    op.create_table(
        "request_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("endpoint", sa.String(256), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_request_logs_request_id", "request_logs", ["request_id"])
    op.create_index("ix_request_logs_client_id", "request_logs", ["client_id"])


def downgrade() -> None:
    op.drop_table("request_logs")
    op.drop_table("calls")
    op.drop_table("batches")
    op.drop_table("agent_drift_events")
    op.drop_table("client_agent_config")
    op.drop_table("agent_catalog")
    op.drop_table("client_config")
    op.drop_table("client_api_keys")
    op.drop_table("clients")
