"""Add tweet_keywords and tweet_summaries tables for Twitter RAG pipeline."""

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tweet_keywords",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("keyword", sa.Text, nullable=False),
        sa.Column("game", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("mention_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "tweet_summaries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tweet_id", sa.Text, nullable=False),
        sa.Column("keyword", sa.Text, nullable=False),
        sa.Column("tweet_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_unique_constraint("uq_tweet_summaries_tweet_id", "tweet_summaries", ["tweet_id"])
    op.create_index("ix_tweet_summaries_tweet_date", "tweet_summaries", ["tweet_date"])
    op.create_index("ix_tweet_summaries_keyword", "tweet_summaries", ["keyword"])

    # Add vector column and ivfflat index via raw SQL (pgvector not in SA type system)
    op.execute("ALTER TABLE tweet_summaries ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tweet_summaries_embedding
        ON tweet_summaries USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    # Explicitly drop indices and constraints before tables
    # (vector extension intentionally left installed — other tables may use it)
    op.drop_index("ix_tweet_summaries_embedding", table_name="tweet_summaries", if_exists=True)
    op.drop_index("ix_tweet_summaries_tweet_date", table_name="tweet_summaries")
    op.drop_index("ix_tweet_summaries_keyword", table_name="tweet_summaries")
    op.drop_constraint("uq_tweet_summaries_tweet_id", "tweet_summaries", type_="unique")
    op.drop_table("tweet_summaries")
    op.drop_table("tweet_keywords")
