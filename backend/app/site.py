from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.core.config import get_settings
from backend.app.core.price_sources import get_configured_price_providers
from backend.app.models.alert import Alert
from backend.app.models.watchlist import Watchlist
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.price_service import get_top_movers, get_top_value_assets

router = APIRouter(include_in_schema=False)
settings = get_settings()


def _format_decimal(value: Decimal | None, *, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value}{suffix}"


def _format_currency(value: Decimal | None, currency: str = "USD") -> str:
    if value is None:
        return "N/A"
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{value}"


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_dashboard_snapshot(db: Session) -> dict[str, object]:
    diagnostics_summary = build_standardized_diagnostics_summary(db)
    configured_providers = get_configured_price_providers()
    primary_provider = next(
        (provider for provider in configured_providers if provider.is_primary),
        configured_providers[0] if configured_providers else None,
    )
    pools = diagnostics_summary["pools"]
    smart_pool = diagnostics_summary["smart_pool"]

    watchlist_count = int(db.scalar(select(func.count(Watchlist.id))) or 0)
    active_alert_count = int(
        db.scalar(select(func.count(Alert.id)).where(Alert.is_active.is_(True))) or 0
    )

    top_value_assets = get_top_value_assets(db, limit=5)
    top_movers = get_top_movers(db, limit=5)

    high_activity_summary = {
        "headline": smart_pool["headline"],
        "summary": smart_pool["summary"],
        "bullets": list(smart_pool["comparison_lines"]),
    }

    return {
        "generated_at": _to_iso(datetime.utcnow()),
        "product_stage": {
            "headline": "Data layer + signal layer MVP",
            "summary": (
                "Flashcard Planet is currently focused on ingestion quality, signal quality, "
                "watchlist workflows, alert loops, and operator diagnostics. It is not a marketplace yet."
            ),
            "focus_areas": [
                "price history ingestion",
                "prediction and movement signals",
                "watchlists and alerts",
                "provider diagnostics",
            ],
        },
        "provider_snapshot": {
            "active_source": diagnostics_summary["active_price_source"],
            "provider_label": primary_provider.label if primary_provider else "Unconfigured",
            "configured_provider_count": len(configured_providers),
            "tracked_assets": diagnostics_summary["health"]["total_assets"],
            "real_history_assets": diagnostics_summary["health"]["assets_with_real_history"],
            "recent_real_rows_24h": diagnostics_summary["health"]["recent_real_price_rows_last_24h"],
            "assets_changed_24h": diagnostics_summary["health"]["assets_with_price_change_last_24h"],
            "row_change_pct_24h": diagnostics_summary["health"]["row_change_pct_last_24h"],
            "row_change_pct_7d": diagnostics_summary["health"]["row_change_pct_last_7d"],
        },
        "signal_snapshot": {
            "watchlists": watchlist_count,
            "active_alerts": active_alert_count,
            "diagnostics_label": "standardized pool + observation diagnostics",
            "current_note": smart_pool["recommendation"],
        },
        "top_value": [
            {
                "name": item.name,
                "set_name": item.set_name,
                "latest_price": _format_currency(item.latest_price, item.currency),
                "source": item.source,
                "captured_at": _to_iso(item.captured_at),
            }
            for item in top_value_assets
        ],
        "top_movers": [
            {
                "name": item.name,
                "latest_price": _format_currency(item.latest_price),
                "absolute_change": _format_currency(item.absolute_change),
                "percent_change": _format_decimal(item.percent_change, suffix="%"),
                "liquidity_score": item.liquidity_score,
                "liquidity_label": item.liquidity_label,
                "alert_confidence": item.alert_confidence,
                "alert_confidence_label": item.alert_confidence_label,
                "sales_count_7d": item.sales_count_7d,
                "sales_count_30d": item.sales_count_30d,
                "days_since_last_sale": item.days_since_last_sale,
            }
            for item in top_movers
        ],
        "pools": [
            {
                "key": pool["key"],
                "label": pool["label"],
                "assets_with_history": f"{pool['assets_with_real_history']}/{pool['total_assets']}",
                "average_depth": f"{pool['average_history_depth']} rows",
                "changed_assets_7d": (
                    f"{pool['assets_with_price_change_last_7d']}/{pool['assets_with_real_history']}"
                ),
                "row_change_pct_7d": pool["row_change_pct_last_7d"],
                "no_movement_assets": pool["assets_with_no_price_movement_full_history"],
            }
            for pool in pools
        ],
        "high_activity_v2_vs_baseline": high_activity_summary,
        "lookup_examples": ["Umbreon", "Pikachu", "Charizard"],
    }


def _render_nav(current_path: str) -> str:
    items = [
        ("/", "Overview"),
        ("/dashboard", "Live Dashboard"),
        ("/method", "Method / Roadmap"),
    ]
    return "".join(
        (
            f'<a class="nav-link{" is-active" if href == current_path else ""}" '
            f'href="{href}">{label}</a>'
        )
        for href, label in items
    )


def _render_shell(*, title: str, current_path: str, body: str, page_key: str) -> HTMLResponse:
    full_title = f"{title} | {settings.project_name}"
    html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta
      name="description"
      content="Flashcard Planet is building a lightweight data-and-signal layer for collectibles, with live diagnostics, price lookup, watchlists, and alerts."
    />
    <title>{escape(full_title)}</title>
    <link rel="stylesheet" href="/static/site.css" />
    <script defer src="/static/site.js"></script>
  </head>
  <body>
    <div class="background-orb background-orb-one"></div>
    <div class="background-orb background-orb-two"></div>
    <header class="site-header">
      <div class="shell shell-header">
        <a class="brand" href="/">
          <span class="brand-mark">FP</span>
          <span class="brand-copy">
            <strong>Flashcard Planet</strong>
            <small>Data and signal layer for collectible assets</small>
          </span>
        </a>
        <nav class="site-nav">{_render_nav(current_path)}</nav>
      </div>
    </header>
    <main
      class="shell page-shell"
      data-page="{escape(page_key)}"
      data-dashboard-snapshot-url="/dashboard/snapshot"
      data-price-api-prefix="{escape(settings.api_prefix)}/prices"
    >
      {body}
    </main>
    <footer class="site-footer">
      <div class="shell footer-shell">
        <p>Flashcard Planet is still in the diagnostics-first stage: data in, signals out, operator loop on top.</p>
        <p>No marketplace flow, listings, payments, or trading UX yet.</p>
      </div>
    </footer>
  </body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/", response_class=HTMLResponse)
def landing_page() -> HTMLResponse:
    body = """
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Public MVP</p>
        <h1>Track collectible pricing, surface signals, and stay close to the operator loop.</h1>
        <p class="lede">
          Flashcard Planet is currently a lightweight data-and-signal product. It turns repeated price history into
          lookup, movement, prediction, watchlist, alert, and diagnostics workflows without pretending the marketplace
          layer exists yet.
        </p>
        <div class="hero-actions">
          <a class="button button-primary" href="/dashboard">Open live dashboard</a>
          <a class="button button-secondary" href="/method">Read the method</a>
        </div>
        <div class="hero-chips">
          <span>data layer</span>
          <span>signal layer</span>
          <span>watchlists and alerts</span>
          <span>provider diagnostics</span>
        </div>
      </div>
      <div class="hero-panel">
        <div class="stat-stack">
          <article class="stat-card">
            <span class="stat-label">Current shape</span>
            <strong>Diagnostics-first</strong>
            <p>Live price history, top-value views, movers, and public proof that the provider-and-pool layer is real.</p>
          </article>
          <article class="stat-card">
            <span class="stat-label">Signal loop</span>
            <strong>Lookup to alert</strong>
            <p>Search prices, inspect short history, score directional signals, and wire watchlists into Discord alerts.</p>
          </article>
          <article class="stat-card">
            <span class="stat-label">Not yet</span>
            <strong>No marketplace flow</strong>
            <p>No checkout, no listings, no seller tools, and no trading workflow until the data-and-signal layer earns it.</p>
          </article>
        </div>
      </div>
    </section>

    <section class="section-grid">
      <article class="feature-card">
        <p class="card-kicker">Data layer</p>
        <h2>Provider-backed price history</h2>
        <p>Repeated ingestion, tracked pools, per-asset history depth, and low-coverage detection all stay visible.</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">Signal layer</p>
        <h2>Top value, movers, and directional reads</h2>
        <p>The MVP is built around what can be measured today: price lookup, short-horizon movement, and prediction cues.</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">Operator layer</p>
        <h2>Watchlists, alerts, and diagnostics</h2>
        <p>Users can already track assets and alerts while operators compare providers, pools, and signal quality in the open.</p>
      </article>
    </section>

    <section class="wide-panel">
      <div>
        <p class="eyebrow">Sitemap</p>
        <h2>Three pages, intentionally lightweight</h2>
      </div>
      <div class="sitemap-list">
        <a class="sitemap-item" href="/">
          <strong>Landing page</strong>
          <span>Product framing, current stage, and what Flashcard Planet is deliberately not yet.</span>
        </a>
        <a class="sitemap-item" href="/dashboard">
          <strong>Live dashboard</strong>
          <span>Price lookup, top value, movers, provider snapshot, and High-Activity v2 diagnostics.</span>
        </a>
        <a class="sitemap-item" href="/method">
          <strong>Method / roadmap</strong>
          <span>How ingestion becomes signal, how diagnostics shape decisions, and what comes next.</span>
        </a>
      </div>
    </section>
    """
    return _render_shell(
        title="Overview",
        current_path="/",
        body=body,
        page_key="landing",
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> HTMLResponse:
    body = """
    <section class="page-intro">
      <div>
        <p class="eyebrow">Live dashboard / demo</p>
        <h1>See the current data-and-signal layer working in public.</h1>
        <p class="lede">
          This page is deliberately small: price lookup, current provider health, top value, top movers, and the
          High-Activity v2 diagnostic that is guiding the next evaluation window.
        </p>
      </div>
      <div class="intro-note">
        <strong>Lightweight by design</strong>
        <p>Everything here supports the current product stage. No auth wall, no payments, and no marketplace scaffolding.</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">Price lookup</p>
          <h2>Search a tracked card and inspect the latest read</h2>
        </div>
        <form class="lookup-form" id="price-lookup-form">
          <label class="sr-only" for="price-query">Asset name</label>
          <input id="price-query" name="query" type="search" placeholder="Try Umbreon, Pikachu, or Charizard" />
          <button class="button button-primary" type="submit">Run lookup</button>
        </form>
        <div class="sample-actions" id="sample-actions"></div>
        <p class="status-line" id="lookup-status">Loading demo snapshot...</p>
        <div class="lookup-results" id="lookup-results"></div>
        <div class="lookup-history" id="lookup-history"></div>
      </article>

      <article class="module" id="provider-snapshot">
        <div class="module-head">
          <p class="card-kicker">Current provider snapshot</p>
          <h2>Loading live health...</h2>
        </div>
        <div class="metric-stack skeleton-stack">
          <span></span><span></span><span></span>
        </div>
      </article>

      <article class="module" id="signal-ops">
        <div class="module-head">
          <p class="card-kicker">Watchlists / alerts / diagnostics</p>
          <h2>Signal ops</h2>
        </div>
        <div class="metric-stack skeleton-stack">
          <span></span><span></span><span></span>
        </div>
      </article>

      <article class="module" id="top-value">
        <div class="module-head">
          <p class="card-kicker">Top value</p>
          <h2>Highest current prices</h2>
        </div>
        <div class="list-shell skeleton-stack"><span></span><span></span><span></span></div>
      </article>

      <article class="module" id="top-movers">
        <div class="module-head">
          <p class="card-kicker">Top movers</p>
          <h2>Largest recent step moves</h2>
        </div>
        <div class="list-shell skeleton-stack"><span></span><span></span><span></span></div>
      </article>

      <article class="module module-wide" id="high-activity-module">
        <div class="module-head">
          <p class="card-kicker">High-Activity v2 vs baseline</p>
          <h2>Loading diagnostic comparison...</h2>
        </div>
        <div class="explanation-grid">
          <div class="explanation-copy skeleton-stack"><span></span><span></span><span></span></div>
          <div class="pool-grid" id="pool-grid"></div>
        </div>
      </article>
    </section>
    """
    return _render_shell(
        title="Live Dashboard",
        current_path="/dashboard",
        body=body,
        page_key="dashboard",
    )


@router.get("/method", response_class=HTMLResponse)
def method_page() -> HTMLResponse:
    body = """
    <section class="page-intro">
      <div>
        <p class="eyebrow">Method / roadmap</p>
        <h1>Build the data layer first. Earn the signal layer. Delay everything else.</h1>
        <p class="lede">
          Flashcard Planet is intentionally sequencing the work: provider-backed ingestion, pool diagnostics,
          explainable signal outputs, and watchlist workflows first. The marketplace layer stays out until the
          data layer is trusted.
        </p>
      </div>
    </section>

    <section class="timeline-grid">
      <article class="timeline-card">
        <p class="card-kicker">Now</p>
        <h2>Data layer</h2>
        <ul class="clean-list">
          <li>Provider-backed price ingestion</li>
          <li>Tracked pool comparisons</li>
          <li>History depth and low-coverage diagnostics</li>
          <li>Public proof through a lightweight dashboard</li>
        </ul>
      </article>
      <article class="timeline-card">
        <p class="card-kicker">Now</p>
        <h2>Signal layer</h2>
        <ul class="clean-list">
          <li>Price lookup and recent history</li>
          <li>Top value and movers</li>
          <li>Directional prediction scoring</li>
          <li>Watchlists and alert rules</li>
        </ul>
      </article>
      <article class="timeline-card">
        <p class="card-kicker">Next</p>
        <h2>Operator roadmap</h2>
        <ul class="clean-list">
          <li>Keep testing High-Activity v2 against baseline pools</li>
          <li>Decide whether provider #2 is needed after more observation</li>
          <li>Broaden the public website only when diagnostics settle</li>
          <li>Refine alert UX before any commercial flow</li>
        </ul>
      </article>
    </section>

    <section class="method-grid">
      <article class="feature-card">
        <p class="card-kicker">Step 1</p>
        <h2>Ingest and normalize</h2>
        <p>Repeated provider fetches create asset-level price history without hiding which source is active.</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">Step 2</p>
        <h2>Diagnose the pool</h2>
        <p>Tracked pools, High-Activity v2, and low-coverage flags tell us whether weak signals come from selection or coverage.</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">Step 3</p>
        <h2>Surface the signal</h2>
        <p>Lookup, movers, top value, and lightweight prediction copy turn raw rows into something users can act on.</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">Step 4</p>
        <h2>Close the operator loop</h2>
        <p>Watchlists and alerts stay close to the current product stage while diagnostics guide the next provider decision.</p>
      </article>
    </section>

    <section class="wide-panel">
      <div>
        <p class="eyebrow">Deliberate exclusions</p>
        <h2>What this MVP does not include yet</h2>
      </div>
      <div class="sitemap-list">
        <div class="sitemap-item static">
          <strong>No marketplace</strong>
          <span>No listings, checkout, buyer flows, seller profiles, or payment rails.</span>
        </div>
        <div class="sitemap-item static">
          <strong>No heavy platform shell</strong>
          <span>No auth-first product maze, no onboarding funnels, and no dashboard bloat.</span>
        </div>
        <div class="sitemap-item static">
          <strong>No broad universe expansion</strong>
          <span>The current focus is still targeted diagnostics, not premature coverage sprawl.</span>
        </div>
      </div>
    </section>
    """
    return _render_shell(
        title="Method / Roadmap",
        current_path="/method",
        body=body,
        page_key="method",
    )


@router.get("/dashboard/snapshot")
def dashboard_snapshot(db: Session = Depends(get_database)) -> dict[str, object]:
    return build_dashboard_snapshot(db)
