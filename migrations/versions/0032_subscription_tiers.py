"""add subscription_tier, is_founders, founders_locked_price_usd to users

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-03

Adds the three columns from TASK-301a that were not covered by 0030/0031:
  - subscription_tier: the paid tier ('free'|'plus'|'pro'); LemonSqueezy webhook
    sets this; resolve_tier() reads it with higher priority than access_tier.
  - is_founders: True for users who subscribed during the Founders window and
    hold a lifetime price lock.
  - founders_locked_price_usd: monthly price locked in at signup (e.g. 7.00 or
    20.00).  NULL for non-founders.

Also adds a partial index on subscription_tier WHERE != 'free' so queries for
active paid users are fast even as the free-user base grows.

All new columns are nullable/defaulted — fully backward-compatible.
Downgrade drops only the columns and index added here.
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_VALID_TIERS = ("free", "plus", "pro")


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "subscription_tier",
        sa.String(16),
        nullable=False,
        server_default="free",
    ))
    op.create_check_constraint(
        "ck_users_subscription_tier",
        "users",
        "subscription_tier IN ('free', 'plus', 'pro')",
    )
    op.create_index(
        "ix_users_subscription_tier_paid",
        "users",
        ["subscription_tier"],
        postgresql_where=sa.text("subscription_tier != 'free'"),
    )

    op.add_column("users", sa.Column(
        "is_founders", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("users", sa.Column(
        "founders_locked_price_usd", sa.Numeric(10, 2), nullable=True
    ))

    # Safety: ensure all existing rows satisfy the check constraint
    op.execute(
        "UPDATE users SET subscription_tier = 'free' "
        "WHERE subscription_tier NOT IN ('free', 'plus', 'pro')"
    )


def downgrade() -> None:
    op.drop_column("users", "founders_locked_price_usd")
    op.drop_column("users", "is_founders")
    op.drop_index("ix_users_subscription_tier_paid", table_name="users")
    op.drop_constraint("ck_users_subscription_tier", "users", type_="check")
    op.drop_column("users", "subscription_tier")
