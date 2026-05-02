"""add subscription_events audit table

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-02

Records each LemonSqueezy webhook event for audit and idempotency.
event_id (LS-assigned) is unique — prevents double-processing replayed webhooks.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),        # LS webhook event ID (idempotency key)
        sa.Column("event_name", sa.String(64), nullable=False),       # e.g. subscription_created
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("subscription_provider_id", sa.String(128), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),          # full webhook body for audit
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_subscription_events_event_id"),
    )
    op.create_index("ix_subscription_events_user_id", "subscription_events", ["user_id"])
    op.create_index("ix_subscription_events_event_name", "subscription_events", ["event_name"])


def downgrade() -> None:
    op.drop_index("ix_subscription_events_event_name", table_name="subscription_events")
    op.drop_index("ix_subscription_events_user_id", table_name="subscription_events")
    op.drop_table("subscription_events")
