"""Seed initial tweet_keywords: 11 TCG price/event keywords."""

from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


KEYWORDS = [
    ("pokemon tcg price",      "pokemon"),
    ("pokemon card price",     "pokemon"),
    ("yugioh price",           "ygo"),
    ("one piece tcg price",    "optcg"),
    ("tcg price spike",        None),
    ("pokemon new set",        "pokemon"),
    ("yugioh new set",         "ygo"),
    ("one piece tcg new set",  "optcg"),
    ("pokemon tcg event",      "pokemon"),
    ("yugioh event",           "ygo"),
    ("tcg reprint",            None),
]


def upgrade() -> None:
    conn = op.get_bind()
    # tweet_keywords has no UNIQUE constraint on keyword, so use WHERE NOT EXISTS guard
    stmt = sa.text(
        "INSERT INTO tweet_keywords (keyword, game) "
        "SELECT :keyword, :game WHERE NOT EXISTS "
        "(SELECT 1 FROM tweet_keywords WHERE keyword = :keyword)"
    )
    for keyword, game in KEYWORDS:
        conn.execute(stmt, {"keyword": keyword, "game": game})


def downgrade() -> None:
    conn = op.get_bind()
    for keyword, _ in KEYWORDS:
        conn.execute(
            sa.text("DELETE FROM tweet_keywords WHERE keyword = :keyword"),
            {"keyword": keyword},
        )
