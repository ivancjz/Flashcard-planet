import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.backstage.gap_detector import get_gap_report
from backend.app.core.config import get_settings
from backend.app.models.enums import AccessTier
from backend.app.models.user import User
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


def require_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    """Enforce admin API key authentication for protected routes.

    Returns:
        401 — X-Admin-Key header is absent (no credentials provided).
        403 — X-Admin-Key header is present but incorrect.

    If ADMIN_API_KEY is not configured (empty string) the endpoint is
    inaccessible to everyone. A warning is logged at startup so the
    operator knows the route is locked.
    """
    expected_key = get_settings().admin_api_key

    if not expected_key:
        logger.warning(
            "ADMIN_API_KEY is not configured. "
            "All requests to admin endpoints will be rejected until it is set."
        )
        raise HTTPException(status_code=403, detail="Admin key not configured on this server.")

    if not x_admin_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Admin-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(x_admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Forbidden")


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
  <div style="{_CARD_STYLE}"><h2>Data Health</h2>{health_html}</div>
  <h2 style="margin-top:24px;">Pools</h2>
  {pools_html}
</body>
</html>"""


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
    return jsonable_encoder(get_gap_report(db))


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
