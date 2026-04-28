import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from statistics import median as _median
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.auth.dependencies import get_current_user as get_session_user
from backend.app.backstage import gap_detector as _gap_detector
from backend.app.core.config import get_settings
from backend.app.ingestion.ebay_sold import _fetch_finding_completed
from backend.app.ingestion.title_parser import parse_listing_title
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.enums import AccessTier
from backend.app.models.graded_observation_audit import GradedObservationAudit
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
from backend.app.services.signal_service import sweep_signals
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


@router.get("/diag/ingestion-history")
def admin_diag_ingestion_history(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Historical ingestion activity to diagnose crash loop onset."""
    window = db.execute(text("""
        SELECT job_name, status, started_at, finished_at, records_written, errors, error_message
        FROM scheduler_run_log
        WHERE started_at BETWEEN '2026-04-23 11:30'::timestamptz AND '2026-04-23 14:30'::timestamptz
        ORDER BY started_at ASC
    """)).fetchall()

    last_success = db.execute(text("""
        SELECT started_at, finished_at, records_written
        FROM scheduler_run_log
        WHERE job_name = 'ingestion' AND status = 'success'
        ORDER BY started_at DESC
        LIMIT 3
    """)).fetchall()

    return {
        "window_11:30_to_14:30": [dict(r._mapping) for r in window],
        "ingestion_last_success": [dict(r._mapping) for r in last_success],
    }


@router.get("/diag/ygo-verify")
def admin_diag_ygo_verify(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Post-merge verification: scheduler_run_log + YGO asset counts + ingestion orphan diagnosis."""
    sched = db.execute(text("""
        SELECT job_name, status, started_at, finished_at, records_written
        FROM scheduler_run_log
        WHERE job_name IN ('yugioh-ingestion', 'ingestion', 'signals')
        ORDER BY started_at DESC
        LIMIT 10
    """)).fetchall()

    assets = db.execute(text("""
        SELECT metadata->>'set_code' AS set_code, COUNT(*) AS assets
        FROM assets
        WHERE external_id LIKE 'yugioh:%'
        GROUP BY set_code
        ORDER BY set_code
    """)).fetchall()

    orphans = db.execute(text("""
        SELECT id, job_name, started_at, finished_at, records_written, error_message
        FROM scheduler_run_log
        WHERE job_name = 'ingestion'
          AND finished_at IS NULL
        ORDER BY started_at DESC
    """)).fetchall()

    gaps = db.execute(text("""
        SELECT started_at,
          LAG(started_at) OVER (ORDER BY started_at) AS prev_run,
          ROUND(EXTRACT(EPOCH FROM (started_at - LAG(started_at) OVER (ORDER BY started_at)))/60, 1) AS minutes_gap
        FROM scheduler_run_log
        WHERE job_name = 'ingestion'
          AND started_at > NOW() - INTERVAL '4 hours'
        ORDER BY started_at DESC
    """)).fetchall()

    last_completed = db.execute(text("""
        SELECT id, status, started_at, finished_at, records_written, errors, error_message
        FROM scheduler_run_log
        WHERE job_name = 'ingestion'
          AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 3
    """)).fetchall()

    return {
        "scheduler_run_log": [dict(r._mapping) for r in sched],
        "ygo_assets_by_set": [dict(r._mapping) for r in assets],
        "ygo_total": sum(r.assets for r in assets),
        "ingestion_orphan_count": len(orphans),
        "ingestion_orphans": [dict(r._mapping) for r in orphans],
        "ingestion_gap_minutes": [dict(r._mapping) for r in gaps],
        "ingestion_last_completed": [dict(r._mapping) for r in last_completed],
    }


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


@router.get("/diag/pred-accuracy")
def admin_pred_accuracy(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """One-off: prediction accuracy for Up/Down signals made 7-14 days ago vs prices 7 days later."""
    from sqlalchemy import text
    # asset_signal_history has no price_at_event; fetch price closest to pred_time
    # and closest price in the 7d-later window from price_history (pokemon_tcg_api only).
    sql = text("""
        WITH past_predictions AS (
          SELECT
            ash.asset_id,
            ash.computed_at AS pred_time,
            ash.prediction,
            ph_then.price AS price_then
          FROM asset_signal_history ash
          JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = ash.asset_id
              AND source = 'pokemon_tcg_api'
              AND captured_at <= ash.computed_at
            ORDER BY captured_at DESC
            LIMIT 1
          ) ph_then ON true
          WHERE ash.computed_at BETWEEN NOW() - INTERVAL '14 days' AND NOW() - INTERVAL '7 days'
            AND ash.prediction IN ('Up', 'Down')
        ),
        later_prices AS (
          SELECT DISTINCT ON (asset_id)
            asset_id, price
          FROM price_history
          WHERE source = 'pokemon_tcg_api'
            AND captured_at BETWEEN NOW() - INTERVAL '7 days' AND NOW() - INTERVAL '6 days'
          ORDER BY asset_id, captured_at DESC
        )
        SELECT
          p.prediction,
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE l.price > p.price_then) AS went_up,
          COUNT(*) FILTER (WHERE l.price < p.price_then) AS went_down,
          ROUND(100.0 * COUNT(*) FILTER (
            WHERE (p.prediction = 'Up' AND l.price > p.price_then)
               OR (p.prediction = 'Down' AND l.price < p.price_then)
          ) / NULLIF(COUNT(*), 0), 1) AS accuracy_pct
        FROM past_predictions p
        JOIN later_prices l ON l.asset_id = p.asset_id
        GROUP BY p.prediction
        ORDER BY p.prediction
    """)
    rows = db.execute(sql).fetchall()
    if not rows:
        diag = db.execute(text("""
            SELECT
              MIN(computed_at) AS first_signal,
              MAX(computed_at) AS last_signal,
              COUNT(*) FILTER (WHERE prediction IN ('Up','Down')) AS predictions_total,
              COUNT(*) FILTER (WHERE prediction IN ('Up','Down') AND computed_at >= NOW() - INTERVAL '14 days') AS predictions_last_14d
            FROM asset_signal_history
        """)).fetchone()
        return {
            "result": [],
            "diagnostic": {
                "note": "No data in 7-14 day window — project may be too new",
                "first_signal": diag[0].isoformat() if diag[0] else None,
                "last_signal": diag[1].isoformat() if diag[1] else None,
                "predictions_total": diag[2],
                "predictions_last_14d": diag[3],
                "earliest_usable_date": "Need data >= 14 days old; rerun after project has been running 14+ days",
            }
        }
    return [
        {
            "prediction": r[0],
            "total": r[1],
            "went_up": r[2],
            "went_down": r[3],
            "accuracy_pct": float(r[4]) if r[4] is not None else None,
        }
        for r in rows
    ]


_VALID_HUMAN_LABELS = {
    "graded_correct", "wrong_segment", "wrong_asset",
    "not_single_card", "non_english", "unclear",
}


@router.get("/diag/graded-shadow-admission")
def admin_graded_shadow_diag(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Phase 0 graded shadow admission — audit summary and review sample.

    Removal condition: Remove after Phase 2 manual review complete and
    Phase 3 graded enablement decision made.
    """
    rows = db.scalars(select(GradedObservationAudit)).all()

    total_by_decision: dict[str, int] = {}
    total_by_segment: dict[str, int] = {}
    reviewed = 0
    unreviewed = 0
    label_by_decision: dict[str, dict[str, int]] = {}

    for row in rows:
        total_by_decision[row.shadow_decision] = total_by_decision.get(row.shadow_decision, 0) + 1
        seg = row.parser_market_segment or "null"
        total_by_segment[seg] = total_by_segment.get(seg, 0) + 1
        if row.human_label:
            reviewed += 1
            bucket = label_by_decision.setdefault(row.shadow_decision, {})
            bucket[row.human_label] = bucket.get(row.human_label, 0) + 1
        else:
            unreviewed += 1

    # Stratified sample: up to 5 per decision bucket from unreviewed rows
    sample_buckets: dict[str, list] = {}
    for row in rows:
        if row.human_label is None:
            b = sample_buckets.setdefault(row.shadow_decision, [])
            if len(b) < 5:
                b.append({
                    "id": str(row.id),
                    "raw_title": row.raw_title,
                    "shadow_decision": row.shadow_decision,
                    "parser_market_segment": row.parser_market_segment,
                    "parser_confidence": row.parser_confidence,
                    "parser_notes": row.parser_notes,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
    unreviewed_sample = [item for bucket in sample_buckets.values() for item in bucket]

    return {
        "total_by_decision": total_by_decision,
        "total_by_segment": total_by_segment,
        "reviewed_count": reviewed,
        "unreviewed_count": unreviewed,
        "precision_by_decision": label_by_decision,
        "unreviewed_sample": unreviewed_sample,
        "removal_condition": (
            "Remove after Phase 2 manual review complete and "
            "Phase 3 graded enablement decision made"
        ),
    }


@router.post("/diag/graded-shadow-admission/label")
def admin_graded_shadow_label(
    payload: dict,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Label a graded_observation_audit row for human review."""
    row_id = payload.get("id")
    human_label = payload.get("human_label")
    reviewer_notes = payload.get("reviewer_notes")

    if human_label not in _VALID_HUMAN_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid human_label {human_label!r}. "
                   f"Allowed: {sorted(_VALID_HUMAN_LABELS)}",
        )

    try:
        row_uuid = uuid.UUID(str(row_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid id format")

    row = db.scalar(
        select(GradedObservationAudit).where(GradedObservationAudit.id == row_uuid)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Audit row not found")

    row.human_label = human_label
    row.human_reviewed_at = datetime.now(timezone.utc)
    if reviewer_notes is not None:
        row.reviewer_notes = reviewer_notes
    db.commit()
    db.refresh(row)

    return {
        "id": str(row.id),
        "human_label": row.human_label,
        "human_reviewed_at": row.human_reviewed_at.isoformat() if row.human_reviewed_at else None,
        "reviewer_notes": row.reviewer_notes,
        "shadow_decision": row.shadow_decision,
        "raw_title": row.raw_title,
    }


# TEMP — Phase 0 Gate 3: verify graded listings never entered price_history
# Remove alongside graded-shadow-admission diag endpoints (Phase 2 complete)
@router.get("/diag/graded-price-check")
def admin_graded_price_check(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Gate 3 (corrected): check ebay_sold price_history for true graded leakage.

    'unknown' is not graded — it is honest parser uncertainty (ambiguous title,
    partial grade signal). Gate 3 excludes 'unknown' and checks only for
    canonical graded segments (psa_*, bgs_*, cgc_*, sgc_*).

    gate3_pass=False means Phase 0 has a graded-price leak — stop condition.
    unknown_rows is a separate data-hygiene metric; non-zero is expected and OK.
    """
    graded_rows = db.execute(text("""
        SELECT
            market_segment,
            COUNT(*)          AS n,
            MIN(captured_at)::text AS earliest,
            MAX(captured_at)::text AS latest
        FROM price_history
        WHERE source = 'ebay_sold'
          AND market_segment IS NOT NULL
          AND market_segment NOT IN ('raw', 'unknown')
        GROUP BY market_segment
        ORDER BY n DESC
    """)).fetchall()

    unknown_rows = db.execute(text("""
        SELECT COUNT(*) AS n FROM price_history
        WHERE source = 'ebay_sold' AND market_segment = 'unknown'
    """)).scalar() or 0

    # Diagnose: asset names behind the unknown rows (for Phase 0 investigation only)
    unknown_sample = db.execute(text("""
        SELECT
            ph.id::text,
            a.name            AS asset_name,
            ph.price::text,
            ph.captured_at::text
        FROM price_history ph
        JOIN assets a ON a.id = ph.asset_id
        WHERE ph.source = 'ebay_sold'
          AND ph.market_segment = 'unknown'
        ORDER BY ph.captured_at DESC
        LIMIT 20
    """)).fetchall()

    graded_total = sum(r[1] for r in graded_rows)
    return {
        "gate3_pass": graded_total == 0,
        "graded_rows_total": graded_total,
        "graded_by_segment": [
            {"segment": r[0], "n": r[1], "earliest": r[2], "latest": r[3]}
            for r in graded_rows
        ],
        "unknown_rows_total": unknown_rows,
        "unknown_sample": [
            {"id": r[0], "asset_name": r[1], "price": r[2], "captured_at": r[3]}
            for r in unknown_sample
        ],
        "note": (
            "'unknown' is parser uncertainty, not graded leakage. "
            "gate3_pass only fails for canonical graded segments."
        ),
    }


# TEMP — remove after cleanup confirmed (future-timestamp rows deleted)
@router.post("/trigger/delete-future-timestamps")
def admin_delete_future_timestamps(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Delete price_history rows with captured_at > NOW().

    Root cause: ebay_sold ingest had no upper-bound filter; eBay scheduled
    auctions with future end_time were written to the DB. Fix is in ebay_sold.py.
    This one-shot cleans the 749 rows that accumulated before the fix.
    """
    result = db.execute(text("""
        DELETE FROM price_history
        WHERE captured_at > NOW()
    """))
    db.commit()
    return {"ok": True, "rows_deleted": result.rowcount}


# TEMP DIAG ENDPOINT — future-captured_at audit (surfaced 2026-04-27)
# Remove after root cause identified and confirmed fixed
@router.get("/diag/future-timestamps")
def admin_future_timestamps(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Find price_history rows with captured_at > NOW() — indicates ingest timestamp bug."""
    rows = db.execute(text("""
        SELECT
            source,
            COUNT(*)                    AS future_rows,
            MIN(captured_at)::text      AS earliest_future,
            MAX(captured_at)::text      AS latest_future,
            MIN(asset_id::text)         AS sample_asset_id
        FROM price_history
        WHERE captured_at > NOW()
        GROUP BY source
        ORDER BY future_rows DESC
    """)).fetchall()
    return {
        "now": db.execute(text("SELECT NOW()::text")).scalar(),
        "future_rows_by_source": [
            {
                "source": r[0],
                "future_rows": r[1],
                "earliest_future": r[2],
                "latest_future": r[3],
                "sample_asset_id": r[4],
            }
            for r in rows
        ],
        "total_future_rows": sum(r[1] for r in rows),
    }


# TEMP DIAG ENDPOINT — PR #28 verification
# Remove after rarity coverage analysis is documented (target: 2026-05-04)
@router.get("/diag/ygo-rarity-coverage")
def admin_ygo_rarity_coverage(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Per-rarity YGO price coverage — most-recent ygoprodeck_api row per asset."""
    rows = db.execute(text("""
        SELECT
            COALESCE(a.metadata->>'rarity', '— unknown —') AS rarity,
            COUNT(*)                                        AS asset_count,
            COUNT(ph.id)                                    AS with_price_rows,
            COUNT(CASE WHEN ph.price > 0 THEN 1 END)       AS with_nonzero_price,
            ROUND(AVG(CASE WHEN ph.price > 0 THEN ph.price END)::numeric, 2) AS avg_nonzero_price
        FROM assets a
        LEFT JOIN price_history ph
               ON ph.asset_id = a.id
              AND ph.source = 'ygoprodeck_api'
              AND ph.captured_at = (
                  SELECT MAX(captured_at) FROM price_history
                  WHERE asset_id = a.id AND source = 'ygoprodeck_api'
              )
        WHERE a.game = 'yugioh'
        GROUP BY a.metadata->>'rarity'
        ORDER BY asset_count DESC
    """)).fetchall()
    total = sum(r[1] for r in rows)
    with_price = sum(r[2] for r in rows)
    with_nonzero = sum(r[3] for r in rows)
    return {
        "summary": {
            "total_ygo_assets": total,
            "with_any_price_row": with_price,
            "with_nonzero_price": with_nonzero,
            "coverage_pct": round(with_nonzero / total * 100, 1) if total else 0,
        },
        "by_rarity": [
            {
                "rarity": r[0],
                "asset_count": r[1],
                "with_price_rows": r[2],
                "with_nonzero_price": r[3],
                "avg_nonzero_price": float(r[4]) if r[4] else None,
            }
            for r in rows
        ],
    }


@router.get("/diag/null-audit")
def admin_null_audit(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    nulls = db.execute(text("""
        SELECT source,
               COUNT(*) AS null_rows,
               MIN(captured_at)::text AS earliest_null,
               MAX(captured_at)::text AS latest_null
        FROM price_history
        WHERE market_segment IS NULL
        GROUP BY source
        ORDER BY null_rows DESC
    """)).fetchall()
    version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {
        "alembic_version": version,
        "null_audit": [{"source": r[0], "null_rows": r[1], "earliest": r[2], "latest": r[3]} for r in nulls],
    }


@router.get("/diag/ygo-verify-26")
def admin_ygo_verify_26(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Post-PR-26 verification: A/B migration+nulls, C new YGO ingest, D YGO signals, E Pokemon regression."""
    # A: alembic version
    version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()

    # B: any remaining NULLs
    nulls = db.execute(text("""
        SELECT source, COUNT(*) AS null_rows
        FROM price_history WHERE market_segment IS NULL
        GROUP BY source ORDER BY null_rows DESC
    """)).fetchall()

    # C: new YGO rows in last 15 min (run after first ingestion post-deploy)
    ygo_recent = db.execute(text("""
        SELECT market_segment, COUNT(*) AS n, MAX(captured_at)::text AS latest
        FROM price_history
        WHERE source = 'ygoprodeck_api'
          AND captured_at > NOW() - INTERVAL '15 minutes'
        GROUP BY market_segment
    """)).fetchall()

    # D: YGO signal distribution (run after first sweep post-deploy)
    ygo_signals = db.execute(text("""
        SELECT s.label, COUNT(*) AS n
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE a.game = 'yugioh'
        GROUP BY s.label ORDER BY n DESC
    """)).fetchall()

    # E: Pokemon signal regression check (asset_signals is one-row-per-asset upsert)
    pokemon_signals = db.execute(text("""
        SELECT s.label, COUNT(*) AS n
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE a.game = 'pokemon'
        GROUP BY s.label ORDER BY n DESC
    """)).fetchall()

    return {
        "A_alembic_version": version,
        "A_pass": version == "0025",
        "B_null_rows": [{"source": r[0], "count": r[1]} for r in nulls],
        "B_pass": len(nulls) == 0,
        "C_ygo_recent_15min": [{"segment": r[0], "n": r[1], "latest": r[2]} for r in ygo_recent],
        "C_pass": any(r[0] == "raw" for r in ygo_recent) if ygo_recent else None,
        "D_ygo_signals": [{"label": r[0], "n": r[1]} for r in ygo_signals],
        "D_pass": any(r[0] != "INSUFFICIENT_DATA" for r in ygo_signals) if ygo_signals else None,
        "E_pokemon_signals": [{"label": r[0], "n": r[1]} for r in pokemon_signals],
        "E_breakout": next((r[1] for r in pokemon_signals if r[0] == "BREAKOUT"), 0),
        "E_move": next((r[1] for r in pokemon_signals if r[0] == "MOVE"), 0),
        "E_pass": None,  # manual: compare to PR B baseline (BREAKOUT~115, MOVE~188)
    }


# TEMP — PR #29 verification: YGO metadata.set nested block fix
# Remove after D_new_rows_set_id confirmed (after first yugioh-ingestion post-deploy, ~6h)
@router.get("/diag/ygo-set-fix-verify")
def admin_ygo_set_fix_verify(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Post-PR-29 verification for YGO metadata.set nested block fix.

    B: migration 0028 backfilled all existing YGO rows.
    C: /filters/sets-style query now returns rows for YGO (expect 13 sets).
    D: New YGO rows written after deploy also have nested set block.
    """
    # B: did migration 0028 backfill all existing rows?
    b = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE metadata->'set'->>'id' IS NOT NULL) AS with_nested_set,
          COUNT(*)                                                    AS total_ygo,
          COUNT(*) FILTER (WHERE metadata->>'set_code' IS NOT NULL)  AS with_flat_set_code
        FROM assets
        WHERE game = 'yugioh'
    """)).fetchone()

    # C: cardinality check — set.id must group cards into expansion buckets, not one-per-card.
    # The specific bug was set.id = card_number (e.g. "LEDE-EN001" per card).
    # Regression check: count assets where set.id == card_number (must be 0 after fix).
    c_card = db.execute(text("""
        SELECT COUNT(*) FROM assets
        WHERE game = 'yugioh'
          AND metadata->'set'->>'id' = card_number
    """)).scalar() or 0

    c_cardinality = db.execute(text("""
        SELECT
          COUNT(DISTINCT metadata->'set'->>'id') AS unique_set_ids,
          COUNT(*)                               AS total_assets
        FROM assets
        WHERE game = 'yugioh'
          AND metadata->'set'->>'id' IS NOT NULL
    """)).fetchone()

    c_sets = db.execute(text("""
        SELECT
          metadata->'set'->>'id'   AS set_id,
          metadata->'set'->>'name' AS set_name,
          COUNT(*)                 AS card_count
        FROM assets
        WHERE game = 'yugioh'
          AND metadata->'set'->>'id' IS NOT NULL
        GROUP BY metadata->'set'->>'id', metadata->'set'->>'name'
        ORDER BY card_count DESC
    """)).fetchall()

    # D: new YGO rows since last deploy have nested set block (run after next ingestion ~6h)
    d_rows = db.execute(text("""
        SELECT
          metadata->'set'->>'id' AS set_id,
          market_segment,
          COUNT(*) AS n,
          MAX(ph.captured_at)::text AS latest
        FROM price_history ph
        JOIN assets a ON a.id = ph.asset_id
        WHERE a.game = 'yugioh'
          AND ph.captured_at > NOW() - INTERVAL '15 minutes'
        GROUP BY 1, 2
    """)).fetchall()

    with_nested = b[0] if b else 0
    total_ygo = b[1] if b else 0
    with_flat = b[2] if b else 0
    unique_set_ids = c_cardinality[0] if c_cardinality else 0
    total_assets = c_cardinality[1] if c_cardinality else 0

    return {
        "B_with_nested_set": with_nested,
        "B_total_ygo": total_ygo,
        "B_with_flat_set_code": with_flat,
        "B_pass": with_nested == total_ygo and total_ygo > 0,
        # C_regression_zero is the primary correctness signal:
        #   0 = set.id is never equal to card_number (printing code) — bug is gone.
        #   > 0 = bug still present for that many assets.
        # C_unique_set_ids << C_total_assets confirms grouping; exact bucket count
        # is NOT asserted (some sets may have no data if fetch failed at ingest time).
        "C_regression_zero": c_card == 0,
        "C_assets_with_printing_code_as_set_id": c_card,
        "C_unique_set_ids": unique_set_ids,
        "C_total_assets": total_assets,
        "C_sets": [{"set_id": r[0], "set_name": r[1], "card_count": r[2]} for r in c_sets],
        "D_new_rows_15min": [{"set_id": r[0], "segment": r[1], "n": r[2], "latest": r[3]} for r in d_rows],
        "D_new_rows_have_set_id": all(r[0] is not None for r in d_rows) if d_rows else None,
    }


# TEMP — one-shot price volatility check for YGO; remove after pct_unchanged decision made
@router.get("/diag/ygo-price-volatility")
def admin_ygo_price_volatility(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """How much do YGOPRODeck prices actually change? Answers 'does YGO need eBay sold?'

    pct_unchanged > 80%: source prices are static → YGO needs eBay sold for signals.
    pct_unchanged 30-80%: sparse movement, consider baseline window or weight tuning.
    pct_unchanged < 30%: prices are moving, signals should work once baseline fills.
    """
    row = db.execute(text("""
        SELECT
          COUNT(DISTINCT asset_id)                                                        AS assets,
          COUNT(*) FILTER (WHERE price_changes_count = 0) * 100.0 / NULLIF(COUNT(*), 0)  AS pct_unchanged,
          AVG(price_changes_count)                                                        AS avg_changes,
          MAX(price_changes_count)                                                        AS max_changes
        FROM (
          SELECT asset_id, COUNT(DISTINCT price) AS price_changes_count
          FROM price_history
          WHERE source = 'ygoprodeck_api'
            AND captured_at >= NOW() - INTERVAL '14 days'
          GROUP BY asset_id
        ) t
    """)).fetchone()

    # Also show per-asset breakdown for assets that DO move
    movers = db.execute(text("""
        SELECT a.name, a.card_number, COUNT(DISTINCT ph.price) AS distinct_prices,
               MIN(ph.price)::text AS min_price, MAX(ph.price)::text AS max_price
        FROM price_history ph
        JOIN assets a ON a.id = ph.asset_id
        WHERE ph.source = 'ygoprodeck_api'
          AND ph.captured_at >= NOW() - INTERVAL '14 days'
        GROUP BY a.id, a.name, a.card_number
        HAVING COUNT(DISTINCT ph.price) > 1
        ORDER BY COUNT(DISTINCT ph.price) DESC
        LIMIT 10
    """)).fetchall()

    return {
        "assets": row[0] if row else 0,
        "pct_unchanged": float(row[1]) if row and row[1] is not None else None,
        "avg_changes": float(row[2]) if row and row[2] is not None else None,
        "max_changes": int(row[3]) if row and row[3] is not None else None,
        "top_movers": [
            {"name": r[0], "card_number": r[1], "distinct_prices": r[2],
             "min": r[3], "max": r[4]}
            for r in movers
        ],
    }


# TEMP — PR #29 backfill: migration 0028 used `metadata ? 'set_code'` which psycopg
# interprets as a parameter placeholder — UPDATE matched 0 rows. This trigger uses
# `metadata->>'set_code' IS NOT NULL` (equivalent but safe) to do the same backfill.
# Remove after B_pass confirmed in /diag/ygo-set-fix-verify.
@router.post("/trigger/backfill-ygo-set-nested")
def admin_trigger_backfill_ygo_set_nested(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Backfill metadata.set nested block for existing YGO assets.

    Migration 0028 silently matched 0 rows because the PostgreSQL JSONB `?` operator
    was interpreted as a psycopg parameter placeholder. This endpoint uses the
    `->>` text-extraction form which is parameterization-safe.

    Idempotent: the WHERE clause only touches rows where metadata.set.id is not yet set.
    """
    result = db.execute(text("""
        UPDATE assets
        SET metadata = metadata || jsonb_build_object(
            'set', jsonb_build_object(
                'id',    split_part(metadata->>'set_code', '-', 1),
                'name',  metadata->>'set_name',
                'total', NULL
            )
        )
        WHERE game = 'yugioh'
          AND metadata->>'set_code' IS NOT NULL
          AND COALESCE(metadata->'set'->>'id', '') = ''
    """))
    db.commit()
    return {"ok": True, "rows_updated": result.rowcount}


# TEMP — remove after B_pass confirmed (alembic 0025 pre-ran; NULL rows accumulated post-migration)
@router.post("/trigger/backfill-ygo-segment")
def admin_trigger_backfill_ygo_segment(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Backfill market_segment='raw' for ygoprodeck_api rows still NULL after 0025.

    0025 ran before the ygo.py ingest fix deployed; rows written in the gap
    came in with market_segment=NULL and were not covered by the migration.
    This is a one-shot idempotent UPDATE — safe to re-run.
    """
    result = db.execute(text("""
        UPDATE price_history
        SET market_segment = 'raw'
        WHERE source = 'ygoprodeck_api'
          AND market_segment IS NULL
    """))
    db.commit()
    return {"ok": True, "rows_updated": result.rowcount}


@router.post("/trigger/signal-sweep")
def admin_trigger_signal_sweep(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Run a signal sweep immediately and return the result counts."""
    result = sweep_signals(db)
    return {
        "ok": True,
        "total": result.total,
        "breakout": result.breakout,
        "move": result.move,
        "watch": result.watch,
        "idle": result.idle,
        "insufficient_data": result.insufficient_data,
    }


# REMOVE AFTER: YGO eBay feasibility spike confirmed — then delete this endpoint and the
#               _fetch_finding_completed / parse_listing_title imports above.
_YGO_SPIKE_CONFIRM_TOKEN = "ygo-ebay-spike-2026-04-29"
_YGO_SPIKE_PREFERRED_SETS = ["LEDE", "PHNI", "AGOV", "POTE", "TOCH"]
_YGO_SPIKE_SAMPLE_SIZE = 10
_YGO_SPIKE_LISTINGS_PER_ASSET = 20
_YGO_SPIKE_MAX_API_CALLS = 30


@router.post("/trigger/ygo-ebay-spike")
def admin_trigger_ygo_ebay_spike(
    confirm: str = Query(default=""),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """Read-only YGO eBay feasibility spike.

    Runs pre-flight checks (budget + active jobs), then queries eBay findCompletedItems
    for up to 10 sampled YGO assets (1 per expansion set). No DB writes.

    Requires ?confirm=ygo-ebay-spike-2026-04-29 to protect against accidental triggers.

    Remove this endpoint once the spike report has been reviewed.
    """
    if confirm != _YGO_SPIKE_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"Pass ?confirm={_YGO_SPIKE_CONFIRM_TOKEN} to run the spike.",
        )

    settings = get_settings()

    # ── Pre-flight 1: budget check ────────────────────────────────────────────
    budget_row = db.execute(text("""
        SELECT
          SUM(CASE
                WHEN (metadata->>'ebay_sold_last_ingested_at') >=
                     date_trunc('day', NOW() AT TIME ZONE 'UTC')::text
                THEN 1 ELSE 0
              END) AS calls_today
        FROM assets
    """)).fetchone()
    calls_today = int(budget_row.calls_today or 0)
    budget_limit = settings.ebay_daily_budget_limit
    budget_remaining = budget_limit - calls_today
    budget_ok = budget_remaining >= _YGO_SPIKE_MAX_API_CALLS

    # ── Pre-flight 2: active jobs check ───────────────────────────────────────
    active_jobs = db.execute(text("""
        SELECT job_name, started_at
        FROM scheduler_run_log
        WHERE finished_at IS NULL
          AND started_at > NOW() - INTERVAL '15 minutes'
        ORDER BY started_at DESC
    """)).fetchall()
    jobs_ok = len(active_jobs) == 0

    preflight = {
        "budget_limit": budget_limit,
        "calls_today": calls_today,
        "budget_remaining": budget_remaining,
        "budget_ok": budget_ok,
        "active_jobs": [{"job_name": r.job_name, "started_at": str(r.started_at)} for r in active_jobs],
        "jobs_ok": jobs_ok,
        "preflight_pass": budget_ok and jobs_ok,
    }

    if not preflight["preflight_pass"]:
        return {"ok": False, "preflight": preflight, "report": None}

    # ── Sample YGO assets ─────────────────────────────────────────────────────
    all_ygo: list[Asset] = db.execute(
        select(Asset).where(Asset.game == "yugioh").order_by(Asset.external_id)
    ).scalars().all()

    def _expansion(a: Asset) -> str:
        return (a.metadata_json or {}).get("set", {}).get("id", "") or (a.card_number or "").split("-")[0]

    preferred = [a for a in all_ygo if _expansion(a) in _YGO_SPIKE_PREFERRED_SETS]
    rest = [a for a in all_ygo if _expansion(a) not in _YGO_SPIKE_PREFERRED_SETS]
    seen_sets: set[str] = set()
    sampled: list[Asset] = []
    for asset in preferred + rest:
        exp = _expansion(asset)
        if exp not in seen_sets:
            seen_sets.add(exp)
            sampled.append(asset)
        if len(sampled) >= _YGO_SPIKE_SAMPLE_SIZE:
            break

    # ── eBay search ───────────────────────────────────────────────────────────
    api_calls_used = 0
    per_asset: list[dict] = []

    with httpx.Client() as client:
        for asset in sampled:
            if api_calls_used >= _YGO_SPIKE_MAX_API_CALLS:
                per_asset.append({
                    "external_id": asset.external_id,
                    "name": asset.name,
                    "set_id": _expansion(asset),
                    "error": "budget_exhausted",
                })
                continue

            query = f"{asset.name} {asset.card_number or ''} {asset.variant or ''}".strip()
            raw_listings = _fetch_finding_completed(client, query)
            api_calls_used += 1

            if raw_listings is None:
                per_asset.append({
                    "external_id": asset.external_id,
                    "name": asset.name,
                    "set_id": _expansion(asset),
                    "error": "ebay_api_error",
                })
                continue

            counts: dict[str, int] = {"raw": 0, "graded": 0, "unknown": 0, "excluded": 0}
            titles: list[str] = []
            for item in raw_listings[:_YGO_SPIKE_LISTINGS_PER_ASSET]:
                title = item.get("title", "")
                result = parse_listing_title(title)
                if result.excluded:
                    counts["excluded"] += 1
                elif result.market_segment == "raw":
                    counts["raw"] += 1
                elif result.grade_company:
                    counts["graded"] += 1
                else:
                    counts["unknown"] += 1
                titles.append(title[:80])

            total_this = counts["raw"] + counts["graded"] + counts["unknown"] + counts["excluded"]
            per_asset.append({
                "external_id": asset.external_id,
                "name": asset.name,
                "set_id": _expansion(asset),
                "card_number": asset.card_number,
                "rarity": asset.variant,
                "listings": total_this,
                "raw": counts["raw"],
                "graded": counts["graded"],
                "unknown": counts["unknown"],
                "excluded": counts["excluded"],
                "sample_titles": titles[:5],
            })

    # ── Aggregate stats ───────────────────────────────────────────────────────
    ok_results = [r for r in per_asset if "error" not in r]
    listing_counts = [r["listings"] for r in ok_results]
    med = _median(listing_counts) if listing_counts else 0.0
    zero_assets = sum(1 for r in ok_results if r["listings"] == 0)
    total_raw = sum(r["raw"] for r in ok_results)
    total_graded = sum(r["graded"] for r in ok_results)
    total_unknown = sum(r["unknown"] for r in ok_results)
    total_scored = total_raw + total_graded + total_unknown
    raw_pct = total_raw / total_scored * 100 if total_scored else 0.0
    graded_pct = total_graded / total_scored * 100 if total_scored else 0.0
    unknown_pct = total_unknown / total_scored * 100 if total_scored else 0.0

    q1 = med >= 5
    q2 = raw_pct >= 60.0
    q3 = 10.0 <= graded_pct <= 50.0

    recommendation: str
    if q1 and q2 and q3:
        recommendation = "ALL_PASS: proceed to Phase B (YGO eBay ingest PR)"
    elif not q1 and zero_assets > len(ok_results) // 2:
        recommendation = "Q1_FAIL: consider popular cards only or expand lookback to 60 days"
    elif not q1:
        recommendation = "Q1_FAIL: volume sparse; consider expanding lookback to 60 days"
    elif not q2:
        recommendation = "Q2_FAIL: parse_listing_title needs YGO-specific patterns before Phase B"
    elif graded_pct > 50.0:
        recommendation = "Q3_HIGH: graded parser must be production-ready before enabling YGO eBay"
    else:
        recommendation = "Q3_LOW: graded shadow audit can stay disabled for YGO initially"

    report = {
        "assets_sampled": len(sampled),
        "api_calls_used": api_calls_used,
        "api_budget_max": _YGO_SPIKE_MAX_API_CALLS,
        "total_listings": sum(r["listings"] for r in ok_results),
        "median_listings_per_asset": round(med, 1),
        "assets_with_zero_listings": zero_assets,
        "raw_pct": round(raw_pct, 1),
        "graded_pct": round(graded_pct, 1),
        "unknown_pct": round(unknown_pct, 1),
        "q1_pass": q1,
        "q2_pass": q2,
        "q3_pass": q3,
        "recommendation": recommendation,
        "per_asset": per_asset,
    }

    return {"ok": True, "preflight": preflight, "report": report}
