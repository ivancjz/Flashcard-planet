"""add subscription fields to users

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-02

Adds LemonSqueezy subscription tracking columns to users table.
All nullable/defaulted — fully backward-compatible with existing rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_VALID_STATUSES = ("free", "trialing", "active", "past_due", "cancelled", "expired")


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "subscription_status", sa.String(20), nullable=False, server_default="free"
    ))
    op.add_column("users", sa.Column(
        "subscription_provider", sa.String(20), nullable=True
    ))
    op.add_column("users", sa.Column(
        "subscription_provider_id", sa.String(128), nullable=True
    ))
    op.add_column("users", sa.Column(
        "subscription_current_period_end", sa.DateTime(), nullable=True
    ))
    op.add_column("users", sa.Column(
        "subscription_cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("users", sa.Column(
        "trial_started_at", sa.DateTime(), nullable=True
    ))
    op.add_column("users", sa.Column(
        "trial_ends_at", sa.DateTime(), nullable=True
    ))
    op.create_index("ix_users_subscription_status", "users", ["subscription_status"])

    # Verify: all existing users must have subscription_status = 'free' after migration
    op.execute("UPDATE users SET subscription_status = 'free' WHERE subscription_status NOT IN %s"
               % (str(_VALID_STATUSES),))


def downgrade() -> None:
    op.drop_index("ix_users_subscription_status", table_name="users")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "trial_started_at")
    op.drop_column("users", "subscription_cancel_at_period_end")
    op.drop_column("users", "subscription_current_period_end")
    op.drop_column("users", "subscription_provider_id")
    op.drop_column("users", "subscription_provider")
    op.drop_column("users", "subscription_status")
