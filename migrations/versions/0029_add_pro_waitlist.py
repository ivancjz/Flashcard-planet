"""add pro_waitlist table

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pro_waitlist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("signed_up_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_page", sa.String(64), nullable=True),
        sa.Column("locale", sa.String(16), nullable=True),
        sa.Column("ip_country", sa.String(4), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_pro_waitlist_email", "pro_waitlist", ["email"])


def downgrade() -> None:
    op.drop_index("ix_pro_waitlist_email", table_name="pro_waitlist")
    op.drop_table("pro_waitlist")
