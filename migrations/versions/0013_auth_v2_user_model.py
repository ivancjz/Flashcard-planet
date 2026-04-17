"""Auth v2: extend users table — email, google_id, last_login_at; discord_user_id nullable.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-18 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("google_id", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.alter_column(
        "users",
        "discord_user_id",
        existing_type=sa.String(length=32),
        nullable=True,
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.alter_column(
        "users",
        "discord_user_id",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "google_id")
    op.drop_column("users", "email")
