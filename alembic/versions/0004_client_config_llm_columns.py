"""Add LLM analysis config columns to client_config

Revision ID: 0004_client_config_llm_columns
Revises: 0003_phone_number_catalog
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_client_config_llm_columns"
down_revision = "0003_phone_number_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_config", sa.Column("analysis_llm_provider", sa.String(32), nullable=True))
    op.add_column("client_config", sa.Column("analysis_llm_model", sa.String(128), nullable=True))
    op.add_column("client_config", sa.Column("analysis_prompt_hint", sa.Text, nullable=True))
    op.add_column("client_config", sa.Column("analysis_llm_api_key_enc", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("client_config", "analysis_llm_api_key_enc")
    op.drop_column("client_config", "analysis_prompt_hint")
    op.drop_column("client_config", "analysis_llm_model")
    op.drop_column("client_config", "analysis_llm_provider")
