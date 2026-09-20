"""Rename task_type -> workflow_code and default_task_type -> default_workflow_code

Turing's "task_type" never meant a task type. Its values (opd/ipd/…) line up with
Kalaam's ``workflows.workflow_code``, while Kalaam uses "task type" for the
clinical task (medication, lab_test, ip_admission). The same name meaning two
different things across the service boundary invites passing ``ip_admission``
where ``ipd`` belongs, so the column is renamed to match what it holds.

A pure rename — the columns were added in 0009 and are still entirely NULL, so
no value migration is needed. Existing values would survive regardless, since
ALTER ... RENAME preserves data.

Revision ID: 0010_workflow_code_rename
Revises: 0009_disposition_columns
Create Date: 2026-09-16

"""

from alembic import op

revision = "0010_workflow_code_rename"
down_revision = "0009_disposition_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("call_analysis", "task_type", new_column_name="workflow_code")
    op.alter_column("batches", "task_type", new_column_name="workflow_code")
    op.alter_column(
        "client_config", "default_task_type", new_column_name="default_workflow_code"
    )
    # The index follows the column name so it stays recognisable.
    op.execute(
        "ALTER INDEX ix_call_analysis_task_type "
        "RENAME TO ix_call_analysis_workflow_code"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX ix_call_analysis_workflow_code "
        "RENAME TO ix_call_analysis_task_type"
    )
    op.alter_column(
        "client_config", "default_workflow_code", new_column_name="default_task_type"
    )
    op.alter_column("batches", "workflow_code", new_column_name="task_type")
    op.alter_column("call_analysis", "workflow_code", new_column_name="task_type")
