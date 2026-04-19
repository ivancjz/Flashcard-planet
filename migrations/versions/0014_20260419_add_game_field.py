"""Add game field to assets, price_history, asset_signals, alerts, raw_listings.

Strategy: add column with server_default='pokemon', then backfill to ensure
every row that was previously scoped to the Pokemon category is correctly tagged.
upgrade() includes a pre-flight check so it fails fast if unexpected categories
exist — protecting against running this migration against data we haven't audited.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-19 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Pre-flight: assert no non-Pokemon categories exist ────────────────────
    dirty = bind.execute(
        text(
            "SELECT category, COUNT(*) AS n FROM assets "
            "WHERE category != 'Pokemon' GROUP BY category"
        )
    ).fetchall()
    if dirty:
        raise RuntimeError(
            f"Unexpected asset categories found — cannot safely backfill: {dirty}"
        )

    # ── 1. assets ─────────────────────────────────────────────────────────────
    op.add_column(
        "assets",
        sa.Column(
            "game",
            sa.String(length=32),
            nullable=False,
            server_default="pokemon",
        ),
    )

    # ── 2. price_history ──────────────────────────────────────────────────────
    op.add_column(
        "price_history",
        sa.Column(
            "game",
            sa.String(length=32),
            nullable=False,
            server_default="pokemon",
        ),
    )

    # ── 3. asset_signals ──────────────────────────────────────────────────────
    op.add_column(
        "asset_signals",
        sa.Column(
            "game",
            sa.String(length=32),
            nullable=False,
            server_default="pokemon",
        ),
    )

    # ── 4. alerts ─────────────────────────────────────────────────────────────
    op.add_column(
        "alerts",
        sa.Column(
            "game",
            sa.String(length=32),
            nullable=False,
            server_default="pokemon",
        ),
    )

    # ── 5. raw_listings (mapped_asset_id is nullable → game is nullable) ──────
    op.add_column(
        "raw_listings",
        sa.Column(
            "game",
            sa.String(length=32),
            nullable=True,
            server_default="pokemon",
        ),
    )

    # ── Backfill assets ───────────────────────────────────────────────────────
    op.execute(
        "UPDATE assets SET game = 'pokemon' WHERE category = 'Pokemon'"
    )

    # ── Backfill price_history via asset_id FK ────────────────────────────────
    op.execute(
        """
        UPDATE price_history
        SET game = assets.game
        FROM assets
        WHERE assets.id = price_history.asset_id
        """
    )

    # ── Backfill asset_signals via asset_id FK ────────────────────────────────
    op.execute(
        """
        UPDATE asset_signals
        SET game = assets.game
        FROM assets
        WHERE assets.id = asset_signals.asset_id
        """
    )

    # ── Backfill alerts via asset_id FK ──────────────────────────────────────
    op.execute(
        """
        UPDATE alerts
        SET game = assets.game
        FROM assets
        WHERE assets.id = alerts.asset_id
        """
    )

    # ── Backfill raw_listings via mapped_asset_id (nullable) ─────────────────
    op.execute(
        """
        UPDATE raw_listings
        SET game = assets.game
        FROM assets
        WHERE assets.id = raw_listings.mapped_asset_id
        AND raw_listings.mapped_asset_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("raw_listings", "game")
    op.drop_column("alerts", "game")
    op.drop_column("asset_signals", "game")
    op.drop_column("price_history", "game")
    op.drop_column("assets", "game")
