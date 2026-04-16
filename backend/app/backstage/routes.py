import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.backstage.gap_detector import get_gap_report
from backend.app.core.config import get_settings
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.smart_pool_service import get_smart_pool_candidates

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
    return f'<p style="color:#dc2626;">Block failed: {block.get("error", "unknown error")}</p>'


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
