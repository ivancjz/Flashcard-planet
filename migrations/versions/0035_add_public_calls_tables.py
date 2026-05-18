"""add public calls tables (predictions, predictions_audit, market_events)

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-18

Adds three tables for the Public Calls feature (Phase 1):
  - predictions: locked prediction records with immutable core columns
  - predictions_audit: append-only audit trail for every state change
  - market_events: event registry for driver attribution engine (Phase 3)

DB-level trigger blocks UPDATE on the four immutable prediction columns.
All changes are additive and backward-compatible.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("prediction_text", sa.Text, nullable=False),
        sa.Column("threshold_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("threshold_currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("threshold_direction", sa.String(16), nullable=False),
        sa.Column("threshold_band_high", sa.Numeric(12, 2), nullable=True),
        sa.Column("stated_probability", sa.Numeric(5, 4), nullable=False),
        sa.Column("driver_attribution", sa.String(32), nullable=True),
        sa.Column("driver_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("is_paper", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("resolution_status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "threshold_direction IN ('above','below','within_band')",
            name="ck_predictions_threshold_direction",
        ),
        sa.CheckConstraint(
            "stated_probability >= 0 AND stated_probability <= 1",
            name="ck_predictions_stated_probability",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('PENDING','HIT','MISS','AMBIGUOUS','VOIDED')",
            name="ck_predictions_resolution_status",
        ),
        sa.CheckConstraint(
            "driver_attribution IS NULL OR driver_attribution IN "
            "('MACRO','META_SHIFT','SUPPLY_SHOCK','EVENT_DRIVEN','INFLUENCER_PROVENANCE','UNKNOWN')",
            name="ck_predictions_driver_attribution",
        ),
        sa.CheckConstraint(
            "driver_confidence IS NULL OR (driver_confidence >= 0 AND driver_confidence <= 1)",
            name="ck_predictions_driver_confidence",
        ),
        sa.CheckConstraint(
            "threshold_direction IS DISTINCT FROM 'within_band' OR threshold_band_high IS NOT NULL",
            name="ck_predictions_band_high_required",
        ),
    )

    op.create_index(
        "ix_predictions_resolution_pending",
        "predictions",
        ["resolution_date"],
        postgresql_where=sa.text("resolution_status = 'PENDING'"),
    )
    op.create_index("ix_predictions_asset_id", "predictions", ["asset_id"])

    op.create_table(
        "predictions_audit",
        sa.Column("audit_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("changed_by", sa.String(128), nullable=True),
        sa.Column("old_state", JSONB, nullable=True),
        sa.Column("new_state", JSONB, nullable=True),
    )
    op.create_index(
        "ix_predictions_audit_prediction_id",
        "predictions_audit",
        ["prediction_id"],
    )

    op.create_table(
        "market_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("affected_asset_ids", JSONB, nullable=True),
        sa.Column("affected_set_ids", JSONB, nullable=True),
        sa.Column("expected_window_days", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ('INFLUENCER','SUPPLY','TOURNAMENT','RELEASE')",
            name="ck_market_events_event_type",
        ),
    )
    op.create_index(
        "ix_market_events_date",
        "market_events",
        [sa.text("event_date DESC")],
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION predictions_immutable_check()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.predicted_at IS DISTINCT FROM OLD.predicted_at THEN
                RAISE EXCEPTION 'predicted_at is immutable';
            END IF;
            IF NEW.resolution_date IS DISTINCT FROM OLD.resolution_date THEN
                RAISE EXCEPTION 'resolution_date is immutable';
            END IF;
            IF NEW.threshold_value IS DISTINCT FROM OLD.threshold_value THEN
                RAISE EXCEPTION 'threshold_value is immutable';
            END IF;
            IF NEW.stated_probability IS DISTINCT FROM OLD.stated_probability THEN
                RAISE EXCEPTION 'stated_probability is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER predictions_block_immutable
            BEFORE UPDATE ON predictions
            FOR EACH ROW EXECUTE FUNCTION predictions_immutable_check();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS predictions_block_immutable ON predictions")
    op.execute("DROP FUNCTION IF EXISTS predictions_immutable_check()")
    op.drop_index("ix_market_events_date", table_name="market_events")
    op.drop_table("market_events")
    op.drop_index("ix_predictions_audit_prediction_id", table_name="predictions_audit")
    op.drop_table("predictions_audit")
    op.drop_index("ix_predictions_asset_id", table_name="predictions")
    op.drop_index("ix_predictions_resolution_pending", table_name="predictions")
    op.drop_table("predictions")
