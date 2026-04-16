"""
alembic/versions/0012_add_scheduler_run_log.py

Run-log table for background scheduler jobs.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_run_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("records_written", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("meta_json", JSONB, nullable=True),
    )
    op.create_index(
        "ix_srl_job_name_started_at",
        "scheduler_run_log",
        ["job_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_srl_job_name_started_at", table_name="scheduler_run_log")
    op.drop_table("scheduler_run_log")
