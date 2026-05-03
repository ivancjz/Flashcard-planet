"""Market Digest service — TASK-301e, F-10.

Sends daily email digests to Plus/Pro subscribers at UTC 07:00.
DIGEST_DRY_RUN defaults to 'true' — set DIGEST_DRY_RUN=false in Railway to send to real users.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.user import User

logger = logging.getLogger(__name__)

DRY_RUN: bool = os.getenv("DIGEST_DRY_RUN", "true").lower() == "true"
DRY_RUN_EMAIL = "ivancheng236@gmail.com"


@dataclass
class DigestCard:
    asset_id: uuid.UUID
    name: str
    game: str
    signal_type: str          # 'BREAKOUT' | 'MOVE' | 'popular'
    price_delta_pct: Optional[float]
    current_price: Optional[float]
    explanation: str


def should_send_digest(user: User, today: date, *, has_signals: bool) -> bool:
    """Return True if this user should receive a digest today."""
    if user.digest_frequency == "off":
        return False

    # 24-hour grace period: use trial_started_at if set, else created_at
    account_start = user.trial_started_at or user.created_at
    if account_start is not None:
        if account_start.tzinfo is None:
            account_start = account_start.replace(tzinfo=UTC)
        age_hours = (datetime.now(UTC) - account_start).total_seconds() / 3600
        if age_hours < 24:
            return False

    last_sent_date: Optional[date] = None
    if user.last_digest_sent_at is not None:
        ldt = user.last_digest_sent_at
        if ldt.tzinfo is None:
            ldt = ldt.replace(tzinfo=UTC)
        last_sent_date = ldt.date()

    days_since = (today - last_sent_date).days if last_sent_date else 999

    if user.digest_frequency == "daily":
        return has_signals or days_since >= 7

    if user.digest_frequency == "weekly":
        return days_since >= 7

    return False


def get_digest_candidates(db: Session, today: date) -> list[DigestCard]:
    """Select up to 5 cards: BREAKOUT -> MOVE -> popular. No duplicates."""
    selected: list[DigestCard] = []
    seen_ids: set[uuid.UUID] = set()

    def _add(rows, signal_type: str) -> None:
        for row in rows:
            if len(selected) >= 5:
                break
            aid = uuid.UUID(str(row.asset_id)) if not isinstance(row.asset_id, uuid.UUID) else row.asset_id
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
            selected.append(DigestCard(
                asset_id=aid,
                name=row.name,
                game=row.game,
                signal_type=signal_type,
                price_delta_pct=float(row.price_delta_pct) if row.price_delta_pct is not None else None,
                current_price=float(row.current_price) if row.current_price is not None else None,
                explanation="",
            ))

    # Step 1: BREAKOUTs ordered by signal_score DESC
    breakout_rows = db.execute(text("""
        SELECT
            a.id        AS asset_id,
            a.name,
            a.game,
            s.label,
            s.signal_score,
            s.price_delta_pct,
            ph.price    AS current_price
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id
              AND source = CASE a.game WHEN 'yugioh' THEN 'ygoprodeck_api'
                           ELSE 'pokemon_tcg_api' END
            ORDER BY captured_at DESC LIMIT 1
        ) ph ON TRUE
        WHERE s.label = 'BREAKOUT'
        ORDER BY s.signal_score DESC NULLS LAST
        LIMIT 5
    """)).fetchall()
    _add(breakout_rows, "BREAKOUT")

    # Step 2: MOVEs ordered by |price_delta_pct| DESC
    if len(selected) < 5:
        move_rows = db.execute(text("""
            SELECT
                a.id        AS asset_id,
                a.name,
                a.game,
                s.label,
                s.signal_score,
                s.price_delta_pct,
                ph.price    AS current_price
            FROM assets a
            JOIN asset_signals s ON s.asset_id = a.id
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = a.id
                  AND source = CASE a.game WHEN 'yugioh' THEN 'ygoprodeck_api'
                               ELSE 'pokemon_tcg_api' END
                ORDER BY captured_at DESC LIMIT 1
            ) ph ON TRUE
            WHERE s.label = 'MOVE'
            ORDER BY ABS(s.price_delta_pct) DESC NULLS LAST
            LIMIT 5
        """)).fetchall()
        _add(move_rows, "MOVE")

    # Step 3: Popular (watchlist count past 30 days, else liquidity_score)
    if len(selected) < 5:
        popular_rows = db.execute(text("""
            SELECT
                a.id        AS asset_id,
                a.name,
                a.game,
                s.label,
                s.signal_score,
                s.price_delta_pct,
                ph.price    AS current_price
            FROM assets a
            JOIN asset_signals s ON s.asset_id = a.id
            LEFT JOIN (
                SELECT asset_id, COUNT(*) AS wl_count
                FROM watchlists
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY asset_id
            ) wl ON wl.asset_id = a.id
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = a.id
                  AND source = CASE a.game WHEN 'yugioh' THEN 'ygoprodeck_api'
                               ELSE 'pokemon_tcg_api' END
                ORDER BY captured_at DESC LIMIT 1
            ) ph ON TRUE
            ORDER BY COALESCE(wl.wl_count, 0) DESC, s.liquidity_score DESC NULLS LAST
            LIMIT 5
        """)).fetchall()
        _add(popular_rows, "popular")

    return selected
