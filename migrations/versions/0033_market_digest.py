"""add Market Digest tables and user digest columns

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users table additions ──────────────────────────────────────────────
    op.add_column("users", sa.Column(
        "digest_frequency",
        sa.String(16),
        nullable=False,
        server_default="daily",
    ))
    op.create_check_constraint(
        "ck_users_digest_frequency",
        "users",
        "digest_frequency IN ('daily', 'weekly', 'off')",
    )
    op.add_column("users", sa.Column(
        "last_digest_sent_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ))

    # ── digest_explanation_cache ───────────────────────────────────────────
    op.create_table(
        "digest_explanation_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("card_id", UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(32), nullable=False),
        sa.Column("date_utc", sa.Date(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_id", "date_utc", "signal_type",
                            name="uq_digest_explanation_cache"),
    )
    op.create_index(
        "ix_digest_explanation_cache_date",
        "digest_explanation_cache",
        ["date_utc"],
    )

    # ── digest_send_log ───────────────────────────────────────────────────
    op.create_table(
        "digest_send_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("cards_included", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("delivery_status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_digest_send_log_dedupe"),
    )
    op.create_check_constraint(
        "ck_digest_send_log_trigger_type",
        "digest_send_log",
        "trigger_type IN ('event', 'weekly_fallback')",
    )
    op.create_check_constraint(
        "ck_digest_send_log_delivery_status",
        "digest_send_log",
        "delivery_status IN ('sent', 'failed', 'skipped')",
    )
    op.create_index(
        "ix_digest_send_log_user_sent",
        "digest_send_log",
        ["user_id", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_digest_send_log_user_sent", table_name="digest_send_log")
    op.drop_table("digest_send_log")
    op.drop_index("ix_digest_explanation_cache_date",
                  table_name="digest_explanation_cache")
    op.drop_table("digest_explanation_cache")
    op.drop_column("users", "last_digest_sent_at")
    op.drop_constraint("ck_users_digest_frequency", "users", type_="check")
    op.drop_column("users", "digest_frequency")
