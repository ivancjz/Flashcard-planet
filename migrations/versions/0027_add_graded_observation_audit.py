"""add graded_observation_audit table for Phase 0 shadow admission

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-28

Temporary audit table for Phase 0 graded shadow admission.
Holds graded eBay listings that passed asset compatibility gates
but were withheld from price_history. Supports human review of
parser precision before Phase 3 graded enablement is designed.

Drop this table when Phase 3 decision is made.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graded_observation_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("external_item_id", sa.Text, nullable=False),
        sa.Column("candidate_asset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("raw_title", sa.Text, nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.Text, nullable=False, server_default="USD"),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("parser_market_segment", sa.Text, nullable=True),
        sa.Column("parser_grade_company", sa.Text, nullable=True),
        sa.Column("parser_grade_score", sa.Text, nullable=True),
        sa.Column("parser_confidence", sa.Text, nullable=True),
        sa.Column("parser_notes", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("preflight_grade_info", postgresql.JSONB, nullable=True),
        sa.Column("shadow_decision", sa.Text, nullable=False),
        sa.Column("human_label", sa.Text, nullable=True),
        sa.Column("human_reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # Unique: one audit row per (provider, listing, candidate asset)
    op.create_index(
        "uq_graded_audit_provider_item_asset",
        "graded_observation_audit",
        ["provider", "external_item_id", "candidate_asset_id"],
        unique=True,
    )
    # Review queue: filter by decision + review status
    op.create_index(
        "ix_graded_audit_decision_reviewed_created",
        "graded_observation_audit",
        ["shadow_decision", "human_reviewed_at", "created_at"],
    )
    # Stratified sampling by segment
    op.create_index(
        "ix_graded_audit_segment_created",
        "graded_observation_audit",
        ["parser_market_segment", "created_at"],
    )
    # Asset-level debugging
    op.create_index(
        "ix_graded_audit_asset_created",
        "graded_observation_audit",
        ["candidate_asset_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("graded_observation_audit")
