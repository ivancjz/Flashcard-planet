from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database

router = APIRouter(prefix="/api/v1/web", tags=["web"])


@router.get("/stats")
def web_stats(db: Session = Depends(get_database)):
    total = db.execute(text("SELECT COUNT(*) FROM assets")).scalar() or 0

    signal_rows = db.execute(text(
        "SELECT label, COUNT(*) AS cnt FROM asset_signals GROUP BY label"
    )).fetchall()
    counts: dict[str, int] = {r.label: r.cnt for r in signal_rows}
    for lbl in ("BREAKOUT", "MOVE", "WATCH", "IDLE", "INSUFFICIENT_DATA"):
        counts.setdefault(lbl, 0)

    last_ingest = db.execute(text("""
        SELECT finished_at FROM scheduler_run_log
        WHERE job_name = 'ingestion' AND status = 'success'
        ORDER BY finished_at DESC LIMIT 1
    """)).scalar()

    return {
        "total_assets": total,
        "signal_counts": counts,
        "last_ingest_utc": last_ingest.isoformat() if last_ingest else None,
        "next_ingest_utc": None,
        "sources_active": ["pokemon_tcg_api", "ebay_sold"],
    }


@router.get("/ticker")
def web_ticker(db: Session = Depends(get_database)):
    rows = db.execute(text("""
        SELECT
            a.id::text           AS asset_id,
            a.name,
            s.label              AS signal,
            s.price_delta_pct,
            ph.price             AS current_price
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
            ORDER BY captured_at DESC LIMIT 1
        ) ph ON TRUE
        WHERE s.label IN ('BREAKOUT', 'MOVE', 'WATCH')
          AND s.price_delta_pct IS NOT NULL
        ORDER BY ABS(s.price_delta_pct) DESC
        LIMIT 20
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


_GAME_PRIMARY_SOURCE = {
    "pokemon": "pokemon_tcg_api",
    "yugioh":  "ygoprodeck_api",
}


@router.get("/filters/sets")
def web_filter_sets(
    game: str = Query(default="pokemon"),
    db: Session = Depends(get_database),
):
    """Distinct sets with card counts ordered by count desc."""
    rows = db.execute(text("""
        SELECT
            metadata->'set'->>'id'   AS set_id,
            metadata->'set'->>'name' AS set_name,
            COUNT(*)                 AS card_count
        FROM assets
        WHERE game = :game
          AND metadata->'set'->>'id' IS NOT NULL
        GROUP BY set_id, set_name
        ORDER BY card_count DESC
    """), {"game": game}).fetchall()
    return {"sets": [{"id": r.set_id, "name": r.set_name, "count": r.card_count} for r in rows]}


@router.get("/filters/rarities")
def web_filter_rarities(
    game: str = Query(default="pokemon"),
    db: Session = Depends(get_database),
):
    """Distinct rarities (variant column) with card counts ordered by count desc."""
    rows = db.execute(text("""
        SELECT variant AS rarity, COUNT(*) AS card_count
        FROM assets
        WHERE game = :game
          AND variant IS NOT NULL AND variant != ''
        GROUP BY variant
        ORDER BY card_count DESC
    """), {"game": game}).fetchall()
    return {"rarities": [{"value": r.rarity, "count": r.card_count} for r in rows]}


@router.get("/cards")
def web_cards(
    signal: str = Query(default="ALL"),
    sort: str = Query(default="change"),
    game: str = Query(default="pokemon"),
    search: str | None = Query(default=None),
    set_id: str | None = Query(default=None),
    rarity: str | None = Query(default=None),
    price_min: float | None = Query(default=None),
    price_max: float | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: Session = Depends(get_database),
):
    primary_source = _GAME_PRIMARY_SOURCE.get(game, "pokemon_tcg_api")
    signal_filter = "" if signal == "ALL" else "AND s.label = :signal"
    params: dict = {"limit": limit, "offset": offset, "game": game, "primary_source": primary_source}
    if signal != "ALL":
        params["signal"] = signal

    search_term = (search or "").strip()
    if search_term:
        # Escape SQL LIKE wildcards in user input before wrapping in %...%
        escaped = search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        search_filter = "AND a.name ILIKE :search"
        params["search"] = f"%{escaped}%"
    else:
        search_filter = ""

    # Set filter — comma-separated list of set_id values
    set_ids_list = [s.strip() for s in (set_id or "").split(",") if s.strip()]
    if set_ids_list:
        placeholders = ", ".join(f":set_id_{i}" for i in range(len(set_ids_list)))
        set_filter = f"AND a.metadata->'set'->>'id' IN ({placeholders})"
        for i, sid in enumerate(set_ids_list):
            params[f"set_id_{i}"] = sid
    else:
        set_filter = ""

    # Rarity filter — comma-separated list of variant values
    rarities_list = [r.strip() for r in (rarity or "").split(",") if r.strip()]
    if rarities_list:
        placeholders = ", ".join(f":rarity_{i}" for i in range(len(rarities_list)))
        rarity_filter = f"AND a.variant IN ({placeholders})"
        for i, r in enumerate(rarities_list):
            params[f"rarity_{i}"] = r
    else:
        rarity_filter = ""

    # Price filter — uses current_price stored in signal_context at sweep time
    price_parts: list[str] = []
    if price_min is not None:
        price_parts.append("AND (s.signal_context->>'current_price')::numeric >= :price_min")
        params["price_min"] = price_min
    if price_max is not None:
        price_parts.append("AND (s.signal_context->>'current_price')::numeric <= :price_max")
        params["price_max"] = price_max
    price_filter = " ".join(price_parts)

    # Validate sort — unknown values fall back to change
    if sort not in {"change", "price", "volume", "recent"}:
        sort = "change"

    # COUNT does not need LATERAL join results — simple join is sufficient
    total = db.execute(text(f"""
        SELECT COUNT(*)
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        WHERE a.game = :game
          {signal_filter}
          {search_filter}
          {set_filter}
          {rarity_filter}
          {price_filter}
    """), params).scalar() or 0

    if sort == "change":
        # Sort key (price_delta_pct) is on asset_signals — no LATERAL needed before LIMIT.
        # Inner subquery pages first; outer LATERAL runs only for the returned rows.
        rows = db.execute(text(f"""
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                tcg.price    AS tcg_price,
                ebay.price   AS ebay_price,
                vol.cnt      AS volume_24h
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                WHERE a.game = :game
                  {signal_filter}
                  {search_filter}
                  {set_filter}
                  {rarity_filter}
                  {price_filter}
                        ORDER BY s.price_delta_pct DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = :primary_source
                ORDER BY captured_at DESC LIMIT 1
            ) tcg ON TRUE
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                  AND captured_at >= NOW() - INTERVAL '24 hours'
            ) vol ON TRUE
        """), params).fetchall()
    elif sort == "price":
        # Pre-aggregate latest TCG price per asset once (DISTINCT ON), then join + page.
        # Avoids 5205 correlated LATERAL calls; relies only on the existing asset_id index.
        rows = db.execute(text(f"""
            WITH latest_tcg AS (
                SELECT DISTINCT ON (asset_id) asset_id, price
                FROM price_history
                WHERE source = :primary_source
                ORDER BY asset_id, captured_at DESC
            )
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                sub.tcg_price,
                ebay.price   AS ebay_price,
                vol.cnt      AS volume_24h
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url,
                    tcg.price    AS tcg_price
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                LEFT JOIN latest_tcg tcg ON tcg.asset_id = a.id
                WHERE a.game = :game
                  {signal_filter}
                  {search_filter}
                  {set_filter}
                  {rarity_filter}
                  {price_filter}
                        ORDER BY tcg.price DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                  AND captured_at >= NOW() - INTERVAL '24 hours'
            ) vol ON TRUE
        """), params).fetchall()
    elif sort == "volume":
        # Sort by current_n from signal_context (eBay 24h count at last sweep).
        # Simpler than a full price_history CTE — avoids scanning 200k+ rows.
        rows = db.execute(text(f"""
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                sub.volume_24h,
                tcg.price    AS tcg_price,
                ebay.price   AS ebay_price
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url,
                    (s.signal_context->>'current_n')::int AS volume_24h
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                WHERE a.game = :game
                  {signal_filter}
                  {search_filter}
                  {set_filter}
                  {rarity_filter}
                  {price_filter}
                ORDER BY (s.signal_context->>'current_n')::int DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = :primary_source
                ORDER BY captured_at DESC LIMIT 1
            ) tcg ON TRUE
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
        """), params).fetchall()
    elif sort == "recent":
        # sort=recent: cards ordered by their most recent signal transition.
        # CTE pre-aggregates MAX(computed_at) per asset for transitions only —
        # 110ms on 1.7M history rows via parallel seq scan + hash aggregate.
        # A LATERAL-per-asset approach was tested and took 4.8s (3966 × index seek).
        rows = db.execute(text(f"""
            WITH last_transitions AS (
                SELECT asset_id, MAX(computed_at) AS last_transition_at
                FROM asset_signal_history
                WHERE previous_label IS NOT NULL
                  AND label IS DISTINCT FROM previous_label
                GROUP BY asset_id
            )
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                tcg.price    AS tcg_price,
                ebay.price   AS ebay_price,
                vol.cnt      AS volume_24h
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                LEFT JOIN last_transitions lt ON lt.asset_id = a.id
                WHERE a.game = :game
                  {signal_filter}
                  {search_filter}
                  {set_filter}
                  {rarity_filter}
                  {price_filter}
                ORDER BY lt.last_transition_at DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = :primary_source
                ORDER BY captured_at DESC LIMIT 1
            ) tcg ON TRUE
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                  AND captured_at >= NOW() - INTERVAL '24 hours'
            ) vol ON TRUE
        """), params).fetchall()
    else:
        # Defensive fallback — should be unreachable after sort validation above.
        # Guards against someone adding to SORT_OPTIONS without adding an elif branch.
        rows = []

    return {
        "cards": [dict(r._mapping) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


class CardsBatchRequest(BaseModel):
    asset_ids: list[str] = Field(max_length=500)
    signal: str = "ALL"
    sort: str = "change"
    search: str | None = None
    limit: int = Field(default=200, ge=1, le=500)


@router.post("/cards/batch")
def web_cards_batch(body: CardsBatchRequest, db: Session = Depends(get_database)):
    """Fetch cards by explicit asset_ids list (for Watchlist).
    No game filter — asset UUIDs are game-agnostic.
    Primary source (TCG price) is determined per-asset via SQL CASE on a.game.
    Cap: 500 asset_ids per request.
    """
    # Validate UUIDs; silently skip invalid ones
    valid_ids: list[str] = []
    for s in body.asset_ids:
        try:
            uuid.UUID(s)
            valid_ids.append(s)
        except ValueError:
            continue

    if not valid_ids:
        return {"cards": [], "total": 0, "limit": body.limit, "offset": 0}

    if len(valid_ids) > 500:
        raise HTTPException(
            status_code=400,
            detail=f"Too many asset_ids: {len(valid_ids)}. Maximum 500 per request.",
        )

    placeholders = ", ".join(f"CAST(:asset_id_{i} AS uuid)" for i in range(len(valid_ids)))
    ids_filter = f"a.id IN ({placeholders})"

    params: dict = {"limit": body.limit}
    for i, vid in enumerate(valid_ids):
        params[f"asset_id_{i}"] = vid

    signal_filter = "" if body.signal == "ALL" else "AND s.label = :signal"
    if body.signal != "ALL":
        params["signal"] = body.signal

    search_term = (body.search or "").strip()
    if search_term:
        escaped = search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        search_filter = "AND a.name ILIKE :search"
        params["search"] = f"%{escaped}%"
    else:
        search_filter = ""

    # Primary source is per-asset: derived from a.game column.
    # inner_source_expr: use when `a` is in scope (inside subquery / same FROM clause).
    # sub_source_expr:   use when only `sub` is in scope (outer query referencing subquery).
    inner_source_expr = "CASE a.game WHEN 'yugioh' THEN 'ygoprodeck_api' ELSE 'pokemon_tcg_api' END"
    sub_source_expr = "CASE sub.game WHEN 'yugioh' THEN 'ygoprodeck_api' ELSE 'pokemon_tcg_api' END"

    total = db.execute(text(f"""
        SELECT COUNT(*)
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        WHERE {ids_filter}
          {signal_filter}
          {search_filter}
    """), params).scalar() or 0

    if body.sort == "price":
        rows = db.execute(text(f"""
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                sub.tcg_price,
                ebay.price   AS ebay_price,
                vol.cnt      AS volume_24h
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url,
                    tcg_l.price  AS tcg_price
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                LEFT JOIN LATERAL (
                    SELECT price FROM price_history
                    WHERE asset_id = a.id
                      AND source = {inner_source_expr}
                    ORDER BY captured_at DESC LIMIT 1
                ) tcg_l ON TRUE
                WHERE {ids_filter}
                  {signal_filter}
                  {search_filter}
                ORDER BY tcg_l.price DESC NULLS LAST
                LIMIT :limit
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                  AND captured_at >= NOW() - INTERVAL '24 hours'
            ) vol ON TRUE
        """), params).fetchall()
    elif body.sort == "volume":
        rows = db.execute(text(f"""
            WITH vol_24h AS (
                SELECT asset_id, COUNT(*) AS cnt
                FROM price_history
                WHERE source = 'ebay_sold'
                  AND captured_at >= NOW() - INTERVAL '24 hours'
                GROUP BY asset_id
            )
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                sub.volume_24h,
                tcg.price    AS tcg_price,
                ebay.price   AS ebay_price
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url,
                    a.game,
                    COALESCE(vol.cnt, 0) AS volume_24h
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                LEFT JOIN vol_24h vol ON vol.asset_id = a.id
                WHERE {ids_filter}
                  {signal_filter}
                  {search_filter}
                ORDER BY vol.cnt DESC NULLS LAST
                LIMIT :limit
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id
                  AND source = {sub_source_expr}
                ORDER BY captured_at DESC LIMIT 1
            ) tcg ON TRUE
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
        """), params).fetchall()
    else:
        # Default: sort=change
        rows = db.execute(text(f"""
            SELECT
                sub.asset_id::text,
                sub.name,
                sub.set_name,
                sub.rarity,
                sub.card_type,
                sub.signal,
                sub.price_delta_pct,
                sub.liquidity_score,
                sub.image_url,
                tcg.price    AS tcg_price,
                ebay.price   AS ebay_price,
                vol.cnt      AS volume_24h
            FROM (
                SELECT
                    a.id         AS asset_id,
                    a.name,
                    a.set_name,
                    a.variant    AS rarity,
                    a.category   AS card_type,
                    s.label      AS signal,
                    s.price_delta_pct,
                    s.liquidity_score,
                    a.metadata->'images'->>'small' AS image_url,
                    a.game
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                WHERE {ids_filter}
                  {signal_filter}
                  {search_filter}
                ORDER BY s.price_delta_pct DESC NULLS LAST
                LIMIT :limit
            ) sub
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id
                  AND source = {sub_source_expr}
                ORDER BY captured_at DESC LIMIT 1
            ) tcg ON TRUE
            LEFT JOIN LATERAL (
                SELECT price FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                ORDER BY captured_at DESC LIMIT 1
            ) ebay ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM price_history
                WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
                  AND captured_at >= NOW() - INTERVAL '24 hours'
            ) vol ON TRUE
        """), params).fetchall()

    return {
        "cards": [dict(r._mapping) for r in rows],
        "total": total,
        "limit": body.limit,
        "offset": 0,
    }


@router.get("/cards/{asset_id}")
def web_card_detail(asset_id: str, db: Session = Depends(get_database)):
    row = db.execute(text("""
        SELECT
            a.id::text      AS asset_id,
            a.name,
            a.set_name,
            a.variant       AS rarity,
            a.category      AS card_type,
            s.label         AS signal,
            s.price_delta_pct,
            s.liquidity_score,
            tcg.price       AS tcg_price,
            ebay.price      AS ebay_price,
            a.metadata->'images'->>'small' AS image_url,
            CASE WHEN tcg.price > 0 AND ebay.price IS NOT NULL
                 THEN ROUND(((tcg.price - ebay.price) / tcg.price * 100)::numeric, 1)
                 ELSE NULL END AS spread_pct
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
            ORDER BY captured_at DESC LIMIT 1
        ) tcg ON TRUE
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
            ORDER BY captured_at DESC LIMIT 1
        ) ebay ON TRUE
        WHERE a.id = CAST(:asset_id AS uuid)
    """), {"asset_id": asset_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Card not found")

    history = db.execute(text("""
        SELECT
            DATE(captured_at) AS date,
            AVG(price) FILTER (WHERE source = 'pokemon_tcg_api') AS tcg_price,
            AVG(price) FILTER (WHERE source = 'ebay_sold')       AS ebay_price
        FROM price_history
        WHERE asset_id = CAST(:asset_id AS uuid)
          AND captured_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(captured_at)
        ORDER BY date ASC
    """), {"asset_id": asset_id}).fetchall()

    signal_history = db.execute(text("""
        SELECT
            id::text                            AS id,
            previous_label,
            label                               AS current_label,
            signal_context->>'current_price'    AS price_at_event_raw,
            price_delta_pct,
            computed_at
        FROM asset_signal_history
        WHERE asset_id = CAST(:asset_id AS uuid)
          AND computed_at > NOW() - INTERVAL '30 days'
          AND label IS DISTINCT FROM previous_label
        ORDER BY computed_at DESC
        LIMIT 50
    """), {"asset_id": asset_id}).fetchall()

    def _parse_price(raw: str | None) -> float | None:
        if not raw:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    return {
        **dict(row._mapping),
        "price_history": [
            {"date": str(h.date),
             "tcg_price": float(h.tcg_price) if h.tcg_price else None,
             "ebay_price": float(h.ebay_price) if h.ebay_price else None}
            for h in history
        ],
        "signal_history": [
            {
                "id": sh.id,
                "previous_label": sh.previous_label,
                "current_label": sh.current_label,
                "price_at_event": _parse_price(sh.price_at_event_raw),
                "price_delta_pct": float(sh.price_delta_pct) if sh.price_delta_pct is not None else None,
                "computed_at": sh.computed_at.isoformat(),
            }
            for sh in signal_history
        ],
    }


@router.get("/alerts")
def web_alerts(
    filter: str = Query(default="ALL"),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_database),
):
    high_only = "AND h.label = 'BREAKOUT'" if filter == "HIGH" else ""

    # previous_label stored at write time (signal_service._append_history) — no
    # LAG/LATERAL needed. ix_asset_signal_history_computed_at drives ORDER BY.
    # Old rows (pre-0020 migration) have previous_label=NULL and are excluded.
    rows = db.execute(text(f"""
        SELECT
            h.id::text          AS id,
            h.asset_id::text    AS asset_id,
            a.name              AS card_name,
            h.previous_label    AS previous_signal,
            h.label             AS current_signal,
            h.price_delta_pct,
            h.computed_at       AS created_at,
            CASE h.label
                WHEN 'BREAKOUT' THEN 'high'
                WHEN 'MOVE'     THEN 'medium'
                ELSE 'low'
            END                 AS severity
        FROM asset_signal_history h
        JOIN assets a ON a.id = h.asset_id
        WHERE h.previous_label IS NOT NULL
          AND h.label IS DISTINCT FROM h.previous_label
          {high_only}
        ORDER BY h.computed_at DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    alerts = []
    for r in rows:
        d = dict(r._mapping)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        alerts.append(d)

    return {"alerts": alerts, "total": len(alerts)}
