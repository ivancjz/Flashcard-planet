import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.auth.dependencies import get_current_user as get_session_user
from backend.app.backstage import gap_detector as _gap_detector
from backend.app.core.config import get_settings
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.enums import AccessTier
from backend.app.models.price_history import PriceHistory
from backend.app.models.scheduler_run_log import SchedulerRunLog
from backend.app.models.user import User
from backend.app.services.scheduler_run_log_service import (
    JOB_BULK_REFRESH,
    JOB_EBAY,
    JOB_HEARTBEAT,
    JOB_INGESTION,
    JOB_RETRY,
    JOB_SIGNALS,
)
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.smart_pool_service import get_smart_pool_candidates
from backend.app.services.upgrade_service import (
    approve_upgrade_request,
    list_pending_requests,
    reject_upgrade_request,
)
from backend.app.services.user_service import set_user_tier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    session_user=Depends(get_session_user),
) -> None:
    """Allow access via X-Admin-Key header OR session user in ADMIN_EMAILS whitelist."""
    settings = get_settings()

    # Path 1: API key (programmatic access, bot scripts)
    if x_admin_key:
        expected = settings.admin_api_key
        if not expected:
            raise HTTPException(status_code=403, detail="Admin key not configured on this server.")
        if not secrets.compare_digest(x_admin_key, expected):
            raise HTTPException(status_code=403, detail="Forbidden")
        return

    # Path 2: Session user in email whitelist (web UI admin)
    if session_user is not None:
        if session_user.email and session_user.email.lower() in settings.admin_email_set:
            return
        # Authenticated but not admin — 404 to hide backend existence
        raise HTTPException(status_code=404)

    # Neither credential valid — 401 (no credentials provided)
    raise HTTPException(
        status_code=401,
        detail="Missing X-Admin-Key header.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


_KPI_COLORS = {
    "green":   "background:#16a34a;color:white",
    "yellow":  "background:#ca8a04;color:white",
    "red":     "background:#dc2626;color:white",
    "unknown": "background:#6b7280;color:white",
}

_CARD_STYLE = "border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:16px;"


def _kpi_badge(status: str, label: str = "") -> str:
    style = _KPI_COLORS.get(status, _KPI_COLORS["unknown"])
    text = label or status.upper()
    return f'<span style="{style};padding:2px 8px;border-radius:4px;font-size:0.8em;">{text}</span>'


def _render_block_error(block: dict) -> str:
    from html import escape
    error_text = escape(str(block.get("error", "unknown error")))
    return f'<p style="color:#dc2626;">Block failed: {error_text}</p>'


def _render_retry_queue_card(block: dict | None) -> str:
    if not block or block.get("status") == "error":
        if block and block.get("status") == "error":
            return f'<div style="{_CARD_STYLE}"><h2>Backfill Retry Queue</h2>{_render_block_error(block)}</div>'
        return ""

    pending = block.get("total_pending", 0)
    permanent = block.get("total_permanent", 0)
    by_type = block.get("by_failure_type", {})
    pending_kpi = block.get("pending_kpi", "unknown")
    permanent_kpi = block.get("permanent_kpi", "unknown")

    type_rows = "".join(
        f"<tr><td>{ftype.replace('_', ' ').title()}</td><td>{count}</td></tr>"
        for ftype, count in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
    ) or "<tr><td colspan='2' style='color:#6b7280;'>No failures recorded</td></tr>"

    warning_html = (
        "<p style='color:#dc2626;margin-top:8px;'>&#9888; Permanent failures require human review.</p>"
        if permanent > 0 else ""
    )

    return f"""
    <div style="{_CARD_STYLE}">
      <h2>Backfill Retry Queue</h2>
      <p>Pending retries: <strong>{pending}</strong>
         &nbsp;{_kpi_badge(pending_kpi)}</p>
      <p>Permanent failures: <strong>{permanent}</strong>
         &nbsp;{_kpi_badge(permanent_kpi)}</p>
      <details style="margin-top:8px;">
        <summary style="cursor:pointer;color:#374151;">By failure type</summary>
        <table border="1" cellpadding="4" style="border-collapse:collapse;margin-top:8px;">
          <thead><tr><th>Type</th><th>Count</th></tr></thead>
          <tbody>{type_rows}</tbody>
        </table>
      </details>
      {warning_html}
    </div>
    """


def _render_diagnostics_html(summary: dict) -> str:
    generated_at = summary.get("generated_at", "N/A")

    # Ingestion block
    ingestion = summary.get("ingestion")
    if ingestion:
        ingestion_html = f"""
        <p>Observations logged: <strong>{ingestion.get("observations_logged", "N/A")}</strong></p>
        <p>Observations matched: <strong>{ingestion.get("observations_matched", "N/A")}</strong></p>
        <p>Observations unmatched: <strong>{ingestion.get("observations_unmatched", "N/A")}</strong></p>
        <p>Requires review: <strong>{ingestion.get("observations_require_review", "N/A")}</strong></p>
        """
    else:
        ingestion_html = "<p>No ingestion result available for this session.</p>"

    # Observation stage block
    obs = summary.get("observation_stage", {})
    obs_logged = obs.get("observations_logged", 0)
    obs_matched = obs.get("observations_matched", 0)
    match_rate = round(obs_matched / obs_logged * 100, 1) if obs_logged else 0.0
    from backend.app.core.kpi_thresholds import kpi_status
    match_kpi = kpi_status("match_rate_pct", match_rate)
    observation_html = f"""
    <p>Window: {obs.get("window", "N/A")}</p>
    <p>Observations logged: <strong>{obs_logged}</strong></p>
    <p>Observations matched: <strong>{obs_matched}</strong>
       &nbsp;{_kpi_badge(match_kpi, f"{match_rate}%")}</p>
    <p>Requires review: <strong>{obs.get("observations_require_review", "N/A")}</strong></p>
    """

    # Signal health block
    sig = summary.get("signal_health", {})
    if sig.get("status") == "error":
        signal_html = _render_block_error(sig)
    else:
        label_rows = "".join(
            f"<tr><td>{label}</td><td>{count}</td></tr>"
            for label, count in sig.get("label_counts", {}).items()
        )
        hcp = sig.get("high_confidence_pct", 0)
        sig_kpi = sig.get("kpi_status", "unknown")
        signal_html = f"""
        <p>Total signals: <strong>{sig.get("total_signals", 0)}</strong></p>
        <p>High confidence (&ge;70): <strong>{sig.get("high_confidence_count", 0)}</strong>
           &nbsp;{_kpi_badge(sig_kpi, f"{hcp}%")}</p>
        <table border="1" cellpadding="4" style="border-collapse:collapse;margin-top:8px;">
          <thead><tr><th>Label</th><th>Count</th></tr></thead>
          <tbody>{label_rows}</tbody>
        </table>
        """

    # Review queue block
    rev = summary.get("review_queue", {})
    if rev.get("status") == "error":
        review_html = _render_block_error(rev)
    else:
        rev_kpi = rev.get("kpi_status", "unknown")
        review_html = f"""
        <p>Pending review: <strong>{rev.get("pending_count", 0)}</strong>
           &nbsp;{_kpi_badge(rev_kpi)}</p>
        """

    # Health block
    health = summary.get("health", {})
    health_html = f"""
    <p>Total assets: <strong>{health.get("total_assets", "N/A")}</strong></p>
    <p>Assets with history: <strong>{health.get("assets_with_real_history", "N/A")}</strong></p>
    <p>Assets without history: <strong>{health.get("assets_without_real_history", "N/A")}</strong></p>
    <p>Row change (24h): <strong>{health.get("row_change_pct_last_24h", "N/A")}</strong></p>
    <p>Row change (7d): <strong>{health.get("row_change_pct_last_7d", "N/A")}</strong></p>
    """

    # Pool blocks
    pools_html = ""
    for pool in summary.get("pools", []):
        pools_html += f"""
        <div style="{_CARD_STYLE}">
          <h3 style="margin:0 0 8px 0;">{pool.get("label", pool.get("key", "Pool"))}</h3>
          <p>Total assets: <strong>{pool.get("total_assets", "N/A")}</strong></p>
          <p>With history: <strong>{pool.get("assets_with_real_history", "N/A")}</strong></p>
          <p>Without history: <strong>{pool.get("assets_without_real_history", "N/A")}</strong></p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Flashcard Planet — Diagnostics</title>
  <style>body{{font-family:sans-serif;max-width:900px;margin:40px auto;padding:0 16px;}}
  h1{{margin-bottom:4px;}}h2{{margin:0 0 8px 0;font-size:1.1em;color:#374151;}}</style>
</head>
<body>
  <h1>Flashcard Planet — Diagnostics</h1>
  <p style="color:#6b7280;margin-top:0;">Generated: {generated_at}</p>

  <div style="{_CARD_STYLE}"><h2>Ingestion (last run)</h2>{ingestion_html}</div>
  <div style="{_CARD_STYLE}"><h2>Observation Stage (24h)</h2>{observation_html}</div>
  <div style="{_CARD_STYLE}"><h2>Signal Health</h2>{signal_html}</div>
  <div style="{_CARD_STYLE}"><h2>Review Queue</h2>{review_html}</div>
  {_render_retry_queue_card(summary.get("backfill_retry_queue"))}
  {_render_scheduler_card(summary.get("scheduler"))}
  {_render_missing_price_card(summary.get("missing_price"))}
  <div style="{_CARD_STYLE}"><h2>Data Health</h2>{health_html}</div>
  <h2 style="margin-top:24px;">Pools</h2>
  {pools_html}
</body>
</html>"""


def _render_scheduler_card(block: dict | None) -> str:
    if not block or block.get("status") == "error":
        if block and block.get("status") == "error":
            return f'<div style="{_CARD_STYLE}"><h2>Scheduler Jobs</h2>{_render_block_error(block)}</div>'
        return ""

    _STATUS_COLORS = {
        "success":   "background:#16a34a;color:white",
        "error":     "background:#dc2626;color:white",
        "running":   "background:#ca8a04;color:white",
        "never_run": "background:#6b7280;color:white",
    }

    def _job_row(label: str, run: dict) -> str:
        from html import escape
        status = run.get("status", "never_run")
        started = run.get("started_at") or "—"
        duration = run.get("duration_seconds")
        dur_str = f"{duration:.0f}s" if duration is not None else "—"
        written = run.get("records_written", 0)
        errors  = run.get("errors", 0)
        err_str = f' <span style="color:#dc2626;">({errors} errors)</span>' if errors else ""
        color_style = _STATUS_COLORS.get(status, _STATUS_COLORS["never_run"])
        badge = f'<span style="{color_style};padding:1px 6px;border-radius:4px;font-size:0.8em;">{escape(status)}</span>'
        started_str = started[:16] if started != "—" else "—"
        return (
            f"<tr>"
            f"<td style='padding:4px 8px;'>{escape(label)}</td>"
            f"<td style='padding:4px 8px;'>{badge}</td>"
            f"<td style='padding:4px 8px;'>{escape(started_str)}</td>"
            f"<td style='padding:4px 8px;'>{escape(dur_str)}&nbsp;·&nbsp;{written} written{err_str}</td>"
            f"</tr>"
        )

    rows = "".join([
        _job_row("Ingestion",  block.get("ingestion",  {})),
        _job_row("Backfill",   block.get("backfill",   {})),
        _job_row("Retry pass", block.get("retry",      {})),
        _job_row("Signals",    block.get("signals",    {})),
    ])

    return f"""
    <div style="{_CARD_STYLE}">
      <h2>Scheduler Jobs</h2>
      <table border="1" cellpadding="4" style="border-collapse:collapse;width:100%;">
        <thead><tr><th>Job</th><th>Status</th><th>Last started</th><th>Detail</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """


def _render_missing_price_card(block: dict | None) -> str:
    if not block or block.get("status") == "error":
        if block and block.get("status") == "error":
            return f'<div style="{_CARD_STYLE}"><h2>Missing Reference Price</h2>{_render_block_error(block)}</div>'
        return ""

    pct    = block.get("missing_price_pct", 0)
    count  = block.get("assets_missing_price", 0)
    status = block.get("missing_price_pct_status", "unknown")
    return f"""
    <div style="{_CARD_STYLE}">
      <h2>Missing Reference Price</h2>
      <p>Assets without price history: <strong>{count}</strong>
         &nbsp;{_kpi_badge(status, f"{pct:.1f}%")}</p>
    </div>
    """


@router.get("/diagnostics", response_class=HTMLResponse)
def diagnostics_page(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    summary = build_standardized_diagnostics_summary(db)
    return HTMLResponse(_render_diagnostics_html(summary))


@router.patch("/users/{discord_user_id}/tier")
def admin_set_user_tier(
    discord_user_id: str,
    tier: AccessTier,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    user = db.scalars(select(User).where(User.discord_user_id == discord_user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    set_user_tier(db, user, tier)
    db.commit()
    return {"ok": True, "discord_user_id": discord_user_id, "tier": user.access_tier}


@router.get("/gaps")
def admin_gaps(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    return jsonable_encoder(_gap_detector.get_gap_report(db))


@router.get("/smart-pool")
def admin_smart_pool(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    candidates = get_smart_pool_candidates(db, top_n=20)
    return jsonable_encoder(
        [
            {
                "asset_id": candidate.asset_id,
                "external_id": candidate.external_id,
                "name": candidate.name,
                "set_name": candidate.set_name,
                "price_change_count_7d": candidate.price_change_count_7d,
                "price_range_pct": candidate.price_range_pct,
                "latest_price": candidate.latest_price,
                "liquidity_score": candidate.liquidity_score,
                "composite_score": candidate.composite_score,
            }
            for candidate in candidates
        ]
    )


@router.get("/upgrade-requests", response_class=HTMLResponse)
def admin_upgrade_queue(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """List all pending Pro upgrade requests."""
    requests = list_pending_requests(db)

    if not requests:
        rows_html = "<tr><td colspan='5' style='text-align:center;color:#6b7280;'>No pending requests.</td></tr>"
    else:
        from html import escape as _escape
        rows_html = "".join(
            f"""
            <tr>
              <td style="padding:8px 12px;">{_escape(str(r.id)[:8])}…</td>
              <td style="padding:8px 12px;">{_escape(str(r.user_id)[:8])}…</td>
              <td style="padding:8px 12px;">{_escape(r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "N/A")}</td>
              <td style="padding:8px 12px;">{_escape(r.note or "—")}</td>
              <td style="padding:8px 12px;">
                <form method="POST" action="/admin/upgrade-requests/{r.id}/approve" style="display:inline">
                  <button style="background:#16a34a;color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;">Approve</button>
                </form>
                &nbsp;
                <form method="POST" action="/admin/upgrade-requests/{r.id}/reject" style="display:inline">
                  <button style="background:#dc2626;color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;">Reject</button>
                </form>
              </td>
            </tr>
            """
            for r in requests
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Upgrade Requests — Admin</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:40px auto;padding:0 16px;}}
table{{width:100%;border-collapse:collapse;}}th,td{{text-align:left;border-bottom:1px solid #e5e7eb;}}
th{{font-size:0.85em;color:#6b7280;padding:8px 12px;}}</style></head>
<body>
  <h1>Upgrade Requests</h1>
  <p><a href="/admin/diagnostics">← Diagnostics</a></p>
  <table>
    <thead><tr><th>Request ID</th><th>User ID</th><th>Submitted</th><th>Note</th><th>Actions</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</body></html>"""
    return HTMLResponse(html)


@router.post("/upgrade-requests/{request_id}/approve")
def admin_approve_upgrade(
    request_id: uuid.UUID,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    result = approve_upgrade_request(db, request_id=request_id)
    db.commit()
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return RedirectResponse(url="/admin/upgrade-requests", status_code=303)


@router.post("/upgrade-requests/{request_id}/reject")
def admin_reject_upgrade(
    request_id: uuid.UUID,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    result = reject_upgrade_request(db, request_id=request_id)
    db.commit()
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return RedirectResponse(url="/admin/upgrade-requests", status_code=303)


def _last_run_summary(db: Session, job_name: str) -> dict[str, Any] | None:
    row = (
        db.query(SchedulerRunLog)
        .filter(SchedulerRunLog.job_name == job_name)
        .order_by(SchedulerRunLog.started_at.desc())
        .limit(1)
        .first()
    )
    if row is None:
        return {"status": "never_run"}
    duration_ms: int | None = None
    if row.finished_at is not None and row.started_at is not None:
        duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
    return {
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "status": row.status,
        "records_written": row.records_written,
        "errors": row.errors,
        "duration_ms": duration_ms,
    }


@router.get("/stats")
def admin_stats(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Operational snapshot. Read-only."""
    now = datetime.now(timezone.utc)
    # captured_at is tz-naive in the DB; use a naive cutoff to avoid comparison errors
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)

    # Asset counts
    total_assets = db.query(func.count(Asset.id)).scalar() or 0
    pokemon_assets = (
        db.query(func.count(Asset.id)).filter(Asset.game == "pokemon").scalar() or 0
    )
    assets_with_prices = (
        db.query(func.count(func.distinct(PriceHistory.asset_id))).scalar() or 0
    )

    # Price history
    total_price_rows = db.query(func.count(PriceHistory.id)).scalar() or 0
    latest_captured_at_val = db.query(func.max(PriceHistory.captured_at)).scalar()
    source_rows = (
        db.query(PriceHistory.source, func.count(PriceHistory.id))
        .filter(PriceHistory.captured_at >= cutoff_24h)
        .group_by(PriceHistory.source)
        .all()
    )
    source_24h = {src: cnt for src, cnt in source_rows}

    # Signal distribution (from asset_signals.label — one row per asset)
    signal_rows = (
        db.query(AssetSignal.label, func.count(AssetSignal.id))
        .group_by(AssetSignal.label)
        .all()
    )
    signal_counts = {label: cnt for label, cnt in signal_rows}
    signal_total = sum(signal_counts.values())
    latest_signal_at_val = db.query(func.max(AssetSignal.computed_at)).scalar()

    # Scheduler last runs (job names from scheduler_run_log_service constants)
    scheduler = {
        "last_ingestion": _last_run_summary(db, JOB_INGESTION),
        "last_retry": _last_run_summary(db, JOB_RETRY),
        "last_signals": _last_run_summary(db, JOB_SIGNALS),
        "last_ebay": _last_run_summary(db, JOB_EBAY),
        "last_bulk_refresh": _last_run_summary(db, JOB_BULK_REFRESH),
        "last_heartbeat": _last_run_summary(db, JOB_HEARTBEAT),
    }

    return {
        "snapshot_at": now.isoformat(),
        "assets": {
            "total": total_assets,
            "pokemon": pokemon_assets,
            "with_price_history": assets_with_prices,
            "without_price_history": total_assets - assets_with_prices,
        },
        "price_history": {
            "total_rows": total_price_rows,
            "latest_captured_at": latest_captured_at_val.isoformat() if latest_captured_at_val else None,
            "pokemon_tcg_api_rows_last_24h": source_24h.get("pokemon_tcg_api", 0),
            "ebay_sold_rows_last_24h": source_24h.get("ebay_sold", 0),
        },
        "signals": {
            "total": signal_total,
            "breakout": signal_counts.get("BREAKOUT", 0),
            "move": signal_counts.get("MOVE", 0),
            "watch": signal_counts.get("WATCH", 0),
            "idle": signal_counts.get("IDLE", 0),
            "insufficient_data": signal_counts.get("INSUFFICIENT_DATA", 0),
            "latest_computed_at": latest_signal_at_val.isoformat() if latest_signal_at_val else None,
        },
        "scheduler": scheduler,
    }


@router.get("/diag/duplicates")
def admin_diag_duplicates(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    rows = db.execute(text("""
        SELECT name, COUNT(*) AS cnt, array_agg(id::text ORDER BY id::text) AS ids
        FROM assets
        GROUP BY name
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)).fetchall()
    return {"duplicates": [{"name": r.name, "count": r.cnt, "ids": r.ids} for r in rows]}


@router.get("/diag/blastoise")
def admin_diag_blastoise(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    rows = db.execute(text("""
        SELECT ph.source, ph.price::text, ph.captured_at,
               a.metadata->>'set_id' AS set_id,
               a.metadata->>'number' AS card_number,
               a.variant
        FROM price_history ph
        JOIN assets a ON a.id = ph.asset_id
        WHERE a.name = 'Blastoise ex'
        ORDER BY ph.captured_at DESC
        LIMIT 20
    """)).fetchall()
    return {"rows": [dict(r._mapping) for r in rows]}


@router.get("/diag/blastoise-signal")
def admin_diag_blastoise_signal(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT s.label, s.price_delta_pct::text, s.computed_at
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE a.name = 'Blastoise ex'
          AND a.metadata->>'set_id' = 'sv3pt5'
        ORDER BY s.computed_at DESC
        LIMIT 1
    """)).fetchone()
    return dict(row._mapping) if row else {"error": "not found"}


@router.get("/diag/ebay-high-price")
def admin_diag_ebay_high_price(
    threshold: float = 100.0,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    rows = db.execute(text("""
        SELECT a.name, a.metadata->>'set_id' AS set_id, ph.price::text, ph.captured_at
        FROM price_history ph
        JOIN assets a ON a.id = ph.asset_id
        WHERE ph.source = 'ebay_sold'
          AND ph.price > :threshold
        ORDER BY ph.price DESC
        LIMIT 20
    """), {"threshold": threshold}).fetchall()
    return {"rows": [dict(r._mapping) for r in rows], "threshold": threshold}


@router.post("/diag/clean-known-graded-outliers")
def admin_clean_known_graded_outliers(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Delete ebay_sold rows >$500 for cards whose raw value cannot reach that price."""
    result = db.execute(text("""
        DELETE FROM price_history
        WHERE source = 'ebay_sold'
          AND price > 500
          AND asset_id IN (
              SELECT id FROM assets WHERE name = 'Dark Charmeleon'
                AND metadata->>'set_id' = 'base5'
              UNION
              SELECT id FROM assets WHERE name = 'Pikachu'
                AND metadata->>'set_id' = 'sm115'
              UNION
              SELECT id FROM assets WHERE name = 'Umbreon ex'
                AND metadata->>'set_id' = 'sv8pt5'
              UNION
              SELECT id FROM assets WHERE name = 'Machamp'
                AND metadata->>'set_id' = 'base1'
          )
    """))
    db.commit()
    return {"deleted": result.rowcount}


@router.get("/diag/charizard-base1-high-price")
def admin_diag_charizard_base1(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    rows = db.execute(text("""
        SELECT ph.price::text, ph.captured_at
        FROM price_history ph
        JOIN assets a ON a.id = ph.asset_id
        WHERE a.name = 'Charizard'
          AND a.metadata->>'set_id' = 'base1'
          AND ph.source = 'ebay_sold'
          AND ph.price > 500
        ORDER BY ph.price DESC
    """)).fetchall()
    return {"rows": [dict(r._mapping) for r in rows]}


@router.post("/diag/clean-charizard-base1")
def admin_clean_charizard_base1(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Delete graded-price outliers (>$1500) and duplicate rows for Charizard base1."""
    deleted_high = db.execute(text("""
        DELETE FROM price_history
        WHERE asset_id IN (
            SELECT id FROM assets
            WHERE name = 'Charizard' AND metadata->>'set_id' = 'base1'
        )
        AND source = 'ebay_sold'
        AND price > 1500
    """)).rowcount

    deleted_dupes = db.execute(text("""
        DELETE FROM price_history
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                    ROW_NUMBER() OVER (
                        PARTITION BY asset_id, source, price, captured_at
                        ORDER BY id
                    ) AS rn
                FROM price_history
                WHERE asset_id IN (
                    SELECT id FROM assets
                    WHERE name = 'Charizard' AND metadata->>'set_id' = 'base1'
                )
                AND source = 'ebay_sold'
            ) ranked
            WHERE rn > 1
        )
    """)).rowcount

    remaining = db.execute(text("""
        SELECT COUNT(*) AS cnt,
               MIN(price)::text AS min_price,
               MAX(price)::text AS max_price
        FROM price_history
        WHERE asset_id IN (
            SELECT id FROM assets
            WHERE name = 'Charizard' AND metadata->>'set_id' = 'base1'
        )
        AND source = 'ebay_sold'
    """)).fetchone()

    db.commit()
    return {
        "deleted_high_price": deleted_high,
        "deleted_duplicates": deleted_dupes,
        "remaining_rows": remaining.cnt,
        "remaining_min": remaining.min_price,
        "remaining_max": remaining.max_price,
    }


@router.post("/diag/clean-graded-ebay-outliers")
def admin_clean_graded_ebay_outliers(
    price_threshold: float = 50.0,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Delete ebay_sold price_history rows likely from graded cards (price > threshold)."""
    result = db.execute(text("""
        DELETE FROM price_history
        WHERE source = 'ebay_sold'
          AND price > :threshold
          AND asset_id IN (
              SELECT id FROM assets
              WHERE name = 'Blastoise ex'
                AND metadata->>'set_id' = 'sv3pt5'
          )
    """), {"threshold": price_threshold})
    db.commit()
    return {"deleted": result.rowcount, "price_threshold": price_threshold}


@router.get("/coverage")
def admin_coverage(
    set_id: str = Query(..., description="Pokemon TCG set_id, e.g. swsh7"),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """eBay and TCG API price coverage for a given set."""
    from sqlalchemy import exists

    total = db.query(func.count(Asset.id)).filter(Asset.metadata_json["set_id"].as_string() == set_id).scalar() or 0

    def _covered(source: str) -> int:
        return (
            db.query(func.count(Asset.id))
            .filter(
                Asset.metadata_json["set_id"].as_string() == set_id,
                exists().where(
                    (PriceHistory.asset_id == Asset.id) & (PriceHistory.source == source)
                ),
            )
            .scalar()
            or 0
        )

    ebay = _covered("ebay_sold")
    tcg = _covered("pokemon_tcg_api")

    return {
        "set_id": set_id,
        "total_assets": total,
        "ebay_sold_covered": ebay,
        "ebay_sold_pct": round(ebay / total * 100, 1) if total else 0,
        "pokemon_tcg_api_covered": tcg,
        "pokemon_tcg_api_pct": round(tcg / total * 100, 1) if total else 0,
    }
