"""Add source column to tweet_summaries."""

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "tweet_summaries",
        sa.Column("source", sa.Text, nullable=False, server_default="twitter"),
    )


def downgrade() -> None:
    op.drop_column("tweet_summaries", "source")
