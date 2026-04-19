"""Make assets.category nullable and replace it in the unique constraint with game.

category is being phased out (TASK-001c). New assets will have category=NULL;
existing rows keep their 'Pokemon' value. The unique identity of an asset is
now expressed by game (not category), so we rebuild uq_asset_identity without
category and with game instead.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-19 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the old unique constraint (includes category)
    op.drop_constraint("uq_asset_identity", "assets", type_="unique")

    # 2. Make category nullable
    op.alter_column(
        "assets",
        "category",
        existing_type=sa.String(64),
        nullable=True,
    )

    # 3. Rebuild unique constraint with game instead of category
    op.create_unique_constraint(
        "uq_asset_identity",
        "assets",
        ["asset_class", "game", "name", "set_name", "card_number",
         "year", "language", "variant", "grade_company", "grade_score"],
    )


def downgrade() -> None:
    # Restore category to NOT NULL (fill any NULLs first)
    op.execute("UPDATE assets SET category = 'Pokemon' WHERE category IS NULL")

    op.drop_constraint("uq_asset_identity", "assets", type_="unique")

    op.alter_column(
        "assets",
        "category",
        existing_type=sa.String(64),
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_asset_identity",
        "assets",
        ["asset_class", "category", "name", "set_name", "card_number",
         "year", "language", "variant", "grade_company", "grade_score"],
    )
