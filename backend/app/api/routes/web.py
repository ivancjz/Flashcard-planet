from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/cards")
def web_cards(
    signal: str = Query(default="ALL"),
    sort: str = Query(default="change"),
    game: str = Query(default="pokemon"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: Session = Depends(get_database),
):
    primary_source = _GAME_PRIMARY_SOURCE.get(game, "pokemon_tcg_api")
    signal_filter = "" if signal == "ALL" else "AND s.label = :signal"
    params: dict = {"limit": limit, "offset": offset, "game": game, "primary_source": primary_source}
    if signal != "ALL":
        params["signal"] = signal

    # COUNT does not need LATERAL join results — simple join is sufficient
    total = db.execute(text(f"""
        SELECT COUNT(*)
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        WHERE a.game = :game
          {signal_filter}
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
        # Inner subquery pages by TCG price (one LATERAL); outer fills ebay+vol for 50 rows only
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
                    tcg.price    AS tcg_price
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                LEFT JOIN LATERAL (
                    SELECT price FROM price_history
                    WHERE asset_id = a.id AND source = :primary_source
                    ORDER BY captured_at DESC LIMIT 1
                ) tcg ON TRUE
                WHERE a.game = :game
                  {signal_filter}
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
    else:
        # sort=volume: inner pages by eBay 24h volume (one LATERAL); outer fills tcg+ebay for 50 rows
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
                    vol.cnt      AS volume_24h
                FROM assets a
                JOIN asset_signals s ON s.asset_id = a.id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS cnt FROM price_history
                    WHERE asset_id = a.id AND source = 'ebay_sold'
                      AND captured_at >= NOW() - INTERVAL '24 hours'
                ) vol ON TRUE
                WHERE a.game = :game
                  {signal_filter}
                ORDER BY vol.cnt DESC NULLS LAST
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

    return {
        "cards": [dict(r._mapping) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
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

    return {
        **dict(row._mapping),
        "price_history": [
            {"date": str(h.date),
             "tcg_price": float(h.tcg_price) if h.tcg_price else None,
             "ebay_price": float(h.ebay_price) if h.ebay_price else None}
            for h in history
        ],
    }


@router.get("/alerts")
def web_alerts(
    filter: str = Query(default="ALL"),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_database),
):
    extra = ""
    if filter == "HIGH":
        extra = "AND sub.current_signal = 'BREAKOUT'"

    rows = db.execute(text(f"""
        SELECT
            sub.id::text        AS id,
            sub.asset_id::text  AS asset_id,
            a.name              AS card_name,
            sub.previous_signal,
            sub.current_signal,
            sub.price_delta_pct,
            sub.computed_at     AS created_at,
            CASE sub.current_signal
                WHEN 'BREAKOUT' THEN 'high'
                WHEN 'MOVE'     THEN 'medium'
                ELSE 'low'
            END                 AS severity
        FROM (
            SELECT
                id, asset_id,
                label AS current_signal,
                LAG(label) OVER (PARTITION BY asset_id ORDER BY computed_at) AS previous_signal,
                price_delta_pct,
                computed_at
            FROM asset_signal_history
        ) sub
        JOIN assets a ON a.id = sub.asset_id
        WHERE sub.previous_signal IS DISTINCT FROM sub.current_signal
          AND sub.previous_signal IS NOT NULL
          {extra}
        ORDER BY sub.computed_at DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    alerts = []
    for r in rows:
        d = dict(r._mapping)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        alerts.append(d)

    return {"alerts": alerts, "total": len(alerts)}
