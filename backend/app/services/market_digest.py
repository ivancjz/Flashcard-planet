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

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.models.digest_explanation_cache import DigestExplanationCache
from backend.app.models.digest_send_log import DigestSendLog
from backend.app.models.user import User
from backend.app.services.llm_provider import get_llm_provider

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


@dataclass
class DigestStats:
    total_assets: int
    games: list[str]
    last_updated_utc: datetime


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
              AND market_segment = 'raw'
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
                  AND market_segment = 'raw'
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
                  AND market_segment = 'raw'
                ORDER BY captured_at DESC LIMIT 1
            ) ph ON TRUE
            ORDER BY COALESCE(wl.wl_count, 0) DESC, s.liquidity_score DESC NULLS LAST
            LIMIT 5
        """)).fetchall()
        _add(popular_rows, "popular")

    return selected


_SYSTEM_PROMPT = (
    "You are a TCG investment analyst. Write one concise sentence (≤20 words) "
    "explaining why a card received its signal, based on the card name, signal type, "
    "and 7-day price change provided. Be factual and direct."
)


def get_or_generate_explanation(
    db: Session,
    card_id: uuid.UUID,
    signal_type: str,
    date_utc: date,
    card_name: str,
    price_delta_pct: Optional[float],
) -> str:
    """Cache-first LLM explanation. Cache key: (card_id, date_utc, signal_type)."""
    cached = db.scalars(
        select(DigestExplanationCache).where(
            DigestExplanationCache.card_id == card_id,
            DigestExplanationCache.date_utc == date_utc,
            DigestExplanationCache.signal_type == signal_type,
        )
    ).first()

    if cached is not None:
        return cached.explanation

    # Cache miss — call LLM
    delta_str = f"{price_delta_pct:+.1f}%" if price_delta_pct is not None else "N/A"
    user_msg = f"{card_name} | signal={signal_type} | 7d_change={delta_str}"
    try:
        text_result = get_llm_provider().generate_text(_SYSTEM_PROMPT, user_msg, 80)
    except Exception as e:
        logger.warning("digest_llm_failed card=%s error=%s", card_id, e)
        text_result = None

    explanation = text_result or f"{card_name} received a {signal_type} signal with {delta_str} price change."

    provider = os.getenv("LLM_PROVIDER", "anthropic")
    row = DigestExplanationCache(
        card_id=card_id,
        signal_type=signal_type,
        date_utc=date_utc,
        explanation=explanation,
        generated_by=provider,
    )
    db.add(row)
    db.commit()
    return explanation


def render_digest_subject(cards: list[DigestCard], trigger_type: str) -> str:
    if trigger_type == "weekly_fallback":
        return "Your weekly TCG market digest"
    breakout_count = sum(1 for c in cards if c.signal_type == "BREAKOUT")
    return f"Today's TCG market — {breakout_count} BREAKOUTs"


def render_digest_html(
    user: User,
    cards: list[DigestCard],
    trigger_type: str,
    stats: DigestStats,
) -> str:
    from jinja2 import Environment, FileSystemLoader
    from pathlib import Path

    template_dir = Path(__file__).resolve().parents[2] / "email" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    tmpl = env.get_template("market_digest.html")

    name = getattr(user, "username", None) or (
        user.email.split("@")[0] if user.email else "TCG investor"
    )
    return tmpl.render(
        user_name=name,
        cards=cards,
        trigger_type=trigger_type,
        stats=stats,
        app_url=os.getenv("APP_URL", "https://flashcard-planet.up.railway.app"),
    )


def resolve_subscribers(db: Session) -> list[User] | None:
    """Return the list of users to send digest to.

    In DRY_RUN mode: returns [operator_user] if the operator email exists in DB,
    None otherwise (caller must treat None as abort — logs no_op).
    In normal mode: returns all active Plus/Pro subscribers with digest enabled.
    """
    if DRY_RUN:
        operator = db.scalars(
            select(User).where(User.email == DRY_RUN_EMAIL)
        ).first()
        return [operator] if operator is not None else None

    return db.scalars(
        select(User).where(
            User.subscription_tier.in_(["plus", "pro"]),
            User.subscription_status.in_(["active", "trialing"]),
            User.digest_frequency != "off",
        )
    ).all()


def _get_digest_stats(db: Session) -> DigestStats:
    row = db.execute(text("""
        SELECT
            COUNT(DISTINCT a.id)       AS total_assets,
            ARRAY_AGG(DISTINCT a.game) AS games,
            MAX(ph.captured_at)        AS last_updated_utc
        FROM assets a
        LEFT JOIN price_history ph ON ph.asset_id = a.id
    """)).fetchone()
    return DigestStats(
        total_assets=row.total_assets or 0,
        games=sorted(row.games or []),
        last_updated_utc=row.last_updated_utc or datetime.now(UTC),
    )


def send_digest(
    db: Session,
    user: User,
    cards: list[DigestCard],
    trigger_type: str,
    today: date,
) -> None:
    """Build + send email + write audit log + update user.last_digest_sent_at."""
    from backend.app.email.resend_client import send_digest_email

    stats = _get_digest_stats(db)
    subject = render_digest_subject(cards, trigger_type)
    html = render_digest_html(user, cards, trigger_type, stats)

    to_email = DRY_RUN_EMAIL if DRY_RUN else user.email
    dedupe_key = f"user{user.id}-{today.isoformat()}"

    try:
        send_digest_email(to_email, subject, html)
        status = "sent"
        error_msg = None
    except Exception as e:
        status = "failed"
        error_msg = str(e)
        logger.error("digest_send_failed user=%s error=%s", user.id, e)

    log_row = DigestSendLog(
        user_id=user.id,
        subject=subject,
        cards_included=[str(c.asset_id) for c in cards],
        trigger_type=trigger_type,
        delivery_status=status,
        error_message=error_msg,
        dedupe_key=dedupe_key,
    )
    db.add(log_row)

    if status == "sent":
        user.last_digest_sent_at = datetime.now(UTC)

    db.commit()
