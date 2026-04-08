"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-08 00:00:00.000000+00:00

Captures the full schema that was previously managed by SQLAlchemy create_all().
Existing databases that were bootstrapped with create_all() should be stamped at
this revision with:

    alembic stamp 0001

rather than running upgrade(), which would try to create tables that already exist.
init_db() handles this automatically by detecting pre-existing tables.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # assets
    # ------------------------------------------------------------------
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("set_name", sa.String(255), nullable=True),
        sa.Column("card_number", sa.String(64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("variant", sa.String(128), nullable=True),
        sa.Column("grade_company", sa.String(32), nullable=True),
        sa.Column("grade_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_class",
            "category",
            "name",
            "set_name",
            "card_number",
            "year",
            "language",
            "variant",
            "grade_company",
            "grade_score",
            name="uq_asset_identity",
        ),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_assets_category", "assets", ["category"])
    op.create_index("ix_assets_name", "assets", ["name"])

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discord_user_id", sa.String(32), nullable=False),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("discriminator", sa.String(16), nullable=True),
        sa.Column("global_name", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_user_id"),
    )
    op.create_index("ix_users_discord_user_id", "users", ["discord_user_id"])

    # ------------------------------------------------------------------
    # price_history
    # ------------------------------------------------------------------
    op.create_table(
        "price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("captured_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_history_asset_id", "price_history", ["asset_id"])
    op.create_index("ix_price_history_captured_at", "price_history", ["captured_at"])

    # ------------------------------------------------------------------
    # watchlists
    # ------------------------------------------------------------------
    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "asset_id", name="uq_watchlist_user_asset"),
    )
    op.create_index("ix_watchlists_asset_id", "watchlists", ["asset_id"])

    # ------------------------------------------------------------------
    # alerts
    # ------------------------------------------------------------------
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("threshold_percent", sa.Numeric(8, 2), nullable=True),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_armed", sa.Boolean(), nullable=False),
        sa.Column("last_observed_signal", sa.String(32), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"])

    # ------------------------------------------------------------------
    # observation_match_logs
    # ------------------------------------------------------------------
    op.create_table(
        "observation_match_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_item_id", sa.String(128), nullable=False),
        sa.Column("raw_title", sa.String(255), nullable=True),
        sa.Column("raw_set_name", sa.String(255), nullable=True),
        sa.Column("raw_card_number", sa.String(64), nullable=True),
        sa.Column("raw_language", sa.String(32), nullable=True),
        sa.Column("matched_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canonical_key", sa.String(512), nullable=True),
        sa.Column("match_status", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["matched_asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_observation_match_logs_provider", "observation_match_logs", ["provider"])
    op.create_index("ix_observation_match_logs_external_item_id", "observation_match_logs", ["external_item_id"])
    op.create_index("ix_observation_match_logs_matched_asset_id", "observation_match_logs", ["matched_asset_id"])
    op.create_index("ix_observation_match_logs_canonical_key", "observation_match_logs", ["canonical_key"])
    op.create_index("ix_observation_match_logs_match_status", "observation_match_logs", ["match_status"])
    op.create_index("ix_observation_match_logs_requires_review", "observation_match_logs", ["requires_review"])
    op.create_index("ix_observation_match_logs_created_at", "observation_match_logs", ["created_at"])
    op.create_index(
        "ix_observation_match_logs_provider_item_created",
        "observation_match_logs",
        ["provider", "external_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("observation_match_logs")
    op.drop_table("alerts")
    op.drop_table("watchlists")
    op.drop_table("price_history")
    op.drop_table("users")
    op.drop_table("assets")
