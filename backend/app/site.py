from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import Form

from backend.app.api.deps import get_database
from backend.app.core.config import get_settings
from backend.app.core.permissions import Feature, can, get_capabilities
from backend.app.core.price_queries import build_ranked_price_subquery
from backend.app.core.price_sources import (
    get_active_price_source_filter,
    get_configured_price_providers,
)
from backend.app.db.session import SessionLocal
from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.asset_signal_history import AssetSignalHistory
from backend.app.models.price_history import PriceHistory
from backend.app.models.user import User
from backend.app.models.watchlist import Watchlist
from backend.app.services.card_detail_service import build_card_detail
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.price_service import get_top_movers, get_top_value_assets
from backend.app.services.pro_insights_service import build_pro_insights
from backend.app.services.signal_service import get_all_signals, get_daily_snapshot_signals
from backend.app.services.smart_pool_service import get_smart_pool_candidates
from backend.app.services.upgrade_service import (
    cancel_upgrade_request,
    get_upgrade_status,
    submit_upgrade_request,
)

router = APIRouter(include_in_schema=False)
settings = get_settings()
logger = logging.getLogger(__name__)
CARDS_PER_PAGE = 50


def _template_ctx(request, user, **kwargs) -> dict:
    """Build a standard template context dict with user capabilities injected."""
    caps = get_capabilities(user.access_tier) if user else frozenset()
    return {
        "request": request,
        "user": user,
        "capabilities": caps,
        "Feature": Feature,
        **kwargs,
    }


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


def _build_cards_query_params(*, set_id: str | None, q: str | None, page: int | None = None) -> str:
    params: dict[str, str | int] = {}
    if set_id:
        params["set"] = set_id
    if q:
        params["q"] = q
    if page is not None:
        params["page"] = page
    return urlencode(params)


def _get_card_metadata(asset: Asset) -> dict:
    return asset.metadata_json if isinstance(asset.metadata_json, dict) else {}


def _get_metadata_image_small(asset: Asset) -> str | None:
    metadata = _get_card_metadata(asset)
    images = metadata.get("images")
    if isinstance(images, dict):
        value = images.get("small")
        if isinstance(value, str) and value:
            return value
    return None


def _get_metadata_tcgplayer_url(asset: Asset) -> str | None:
    metadata = _get_card_metadata(asset)
    value = metadata.get("tcgplayer_url")
    if isinstance(value, str) and value:
        return value
    return None


def _lang_pair(zh: str, en: str, sep: str = " · ") -> str:
    return (
        f"<span class='lang-zh'>{escape(zh)}</span>"
        f"<span class='lang-sep'>{escape(sep)}</span>"
        f"<span class='lang-en'>{escape(en)}</span>"
    )


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
    smart_pool_candidates = get_smart_pool_candidates(db, top_n=5)

    high_activity_summary = {
        "headline": smart_pool["headline"],
        "summary": smart_pool["summary"],
        "bullets": list(smart_pool["comparison_lines"]),
    }

    return {
        "generated_at": _to_iso(datetime.now(UTC)),
        "product_stage": {
            "headline": "数据层 + 信号层 MVP",
            "summary": (
                "Flashcard Planet 当前专注于数据采集质量、信号质量、关注列表工作流、"
                "预警闭环与运营诊断。它目前还不是一个交易市场。"
            ),
            "focus_areas": [
                "价格历史采集",
                "预测与涨跌信号",
                "关注列表与预警",
                "数据源诊断",
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
            "diagnostics_label": "标准化池 + 观测诊断",
            "current_note": smart_pool["recommendation"],
        },
        "top_value": [
            {
                "name": item.name,
                "set_name": item.set_name,
                "external_id": item.external_id,
                "latest_price": _format_currency(item.latest_price, item.currency),
                "source": item.source,
                "captured_at": _to_iso(item.captured_at),
            }
            for item in top_value_assets
        ],
        "top_movers": [
            {
                "name": item.name,
                "set_name": item.set_name,
                "external_id": item.external_id,
                "latest_price": _format_currency(item.latest_price),
                "absolute_change": _format_currency(item.absolute_change),
                "percent_change": _format_decimal(item.percent_change, suffix="%"),
                "percent_change_raw": float(item.percent_change),
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
        "smart_pool_candidates": [
            {
                "asset_id": item.asset_id,
                "external_id": item.external_id,
                "name": item.name,
                "set_name": item.set_name,
                "price_change_count_7d": item.price_change_count_7d,
                "price_range_pct": float(item.price_range_pct) if item.price_range_pct is not None else None,
                "latest_price": _format_currency(item.latest_price),
                "liquidity_score": item.liquidity_score,
                "composite_score": item.composite_score,
            }
            for item in smart_pool_candidates
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
        ("/", "概览", "Overview"),
        ("/dashboard", "实时仪表板", "Dashboard"),
        ("/cards", "卡牌浏览", "Cards"),
        ("/signals", "市场信号", "Signals"),
        ("/watchlists", "关注列表", "Watchlists"),
        ("/alerts", "预警管理", "Alerts"),
        ("/method", "方法论 / 路线图", "Method / Roadmap"),
    ]
    return "".join(
        (
            f'<a class="nav-link{" is-active" if href == current_path else ""}" '
            f'href="{href}">{_lang_pair(zh, en)}</a>'
        )
        for href, zh, en in items
    )


def _render_auth_widget(username: str | None) -> str:
    if username:
        return (
            f'<span class="auth-user">{escape(username)}</span>'
            f'<a class="auth-link" href="/auth/logout">{_lang_pair("退出", "Logout")}</a>'
        )
    return f'<a class="auth-link" href="/auth/login">{_lang_pair("登录", "Login with Discord")}</a>'


def _session_username(request: Request) -> str | None:
    session = request.scope.get("session")
    if isinstance(session, dict):
        return session.get("username")
    return None


def _render_shell(*, title: str, current_path: str, body: str, page_key: str,
                  username: str | None = None) -> HTMLResponse:
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
  <body data-lang="zh">
    <div class="background-orb background-orb-one"></div>
    <div class="background-orb background-orb-two"></div>
    <header class="site-header">
      <div class="shell shell-header">
        <a class="brand" href="/">
          <span class="brand-mark">FP</span>
          <span class="brand-copy">
            <strong>Flashcard Planet</strong>
            <small>{_lang_pair("收藏品数据与信号平台", "Collectibles data and signal platform")}</small>
          </span>
        </a>
        <nav class="site-nav">{_render_nav(current_path)}</nav>
        <div class="auth-widget">{_render_auth_widget(username)}</div>
        <button class="lang-toggle" id="lang-toggle" title="切换语言 / Toggle language">EN</button>
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
        <p>{_lang_pair("Flashcard Planet 目前处于诊断优先阶段：数据接入、信号输出、运营闭环。", "Flashcard Planet is currently in a diagnostics-first phase: data intake, signal output, and operational loops.")}</p>
        <p>{_lang_pair("暂无交易市场、挂单、支付或交易界面。", "There is currently no marketplace, listing flow, payments, or trading UI.")}</p>
      </div>
    </footer>
  </body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/", response_class=HTMLResponse)
def landing_page(request: Request) -> HTMLResponse:
    body = f"""
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">{_lang_pair("公测版", "Preview")}</p>
        <h1>{_lang_pair("追踪收藏品价格，捕捉市场信号，掌握第一手数据。", "Track collectible prices, catch market signals, and stay on top of the data.")}</h1>
        <p class="lede">
          {_lang_pair("Flashcard Planet 目前是一款轻量级的数据与信号产品。它将持续积累的价格历史转化为查询、涨跌观察、趋势判断、关注列表、预警与诊断工作流，同时明确当前尚未进入交易市场层。",
          "Flashcard Planet is currently a lightweight data-and-signal product. It turns collected price history into lookups, movers, trend cues, watchlists, alerts, and diagnostics while staying clearly outside the marketplace layer for now.")}
        </p>
        <div class="hero-actions">
          <a class="button button-primary" href="/dashboard">{_lang_pair("打开实时仪表板", "Open dashboard")}</a>
          <a class="button button-secondary" href="/method">{_lang_pair("查看方法论", "View method")}</a>
        </div>
        <div class="hero-chips">
          <span>{_lang_pair("数据层", "Data layer")}</span>
          <span>{_lang_pair("信号层", "Signal layer")}</span>
          <span>{_lang_pair("关注列表与预警", "Watchlists and alerts")}</span>
          <span>{_lang_pair("数据源诊断", "Source diagnostics")}</span>
        </div>
      </div>
      <div class="hero-panel">
        <div class="stat-stack">
          <article class="stat-card">
            <span class="stat-label">{_lang_pair("当前阶段", "Current stage")}</span>
            <strong>{_lang_pair("诊断优先", "Diagnostics first")}</strong>
            <p>{_lang_pair("实时价格历史、最高价值视图、涨跌榜，以及公开证明数据源与池层真实可用的展示。", "Live price history, top-value views, mover tables, and public proof that the source and pool layers are actually usable.")}</p>
          </article>
          <article class="stat-card">
            <span class="stat-label">{_lang_pair("信号循环", "Signal loop")}</span>
            <strong>{_lang_pair("查询到预警", "Lookup to alert")}</strong>
            <p>{_lang_pair("搜索价格、查看短期历史、评估方向性信号，并将关注列表接入 Discord 预警。", "Search prices, inspect recent history, evaluate directional signals, and connect watchlists to Discord alerts.")}</p>
          </article>
          <article class="stat-card">
            <span class="stat-label">{_lang_pair("尚未实现", "Not yet included")}</span>
            <strong>{_lang_pair("暂无交易市场", "No marketplace yet")}</strong>
            <p>{_lang_pair("在数据与信号层足够成熟之前，不提供结账、挂单、卖家工具或交易流程。", "Until the data and signal layers are mature enough, there is no checkout, listing flow, seller tooling, or trade flow.")}</p>
          </article>
        </div>
      </div>
    </section>

    <section class="section-grid">
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("数据层", "Data layer")}</p>
        <h2>{_lang_pair("数据源支持的价格历史", "Source-backed price history")}</h2>
        <p>{_lang_pair("重复采集、追踪池、单卡历史深度与低覆盖检测都保持公开可见。", "Repeated collection, tracked pools, per-card history depth, and low-coverage checks all stay publicly visible.")}</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("信号层", "Signal layer")}</p>
        <h2>{_lang_pair("最高价值、涨跌幅与方向性分析", "Top value, movers, and directional analysis")}</h2>
        <p>{_lang_pair("MVP 围绕当前可衡量的数据构建：价格查询、短周期涨跌与趋势判断线索。", "The MVP is built around measurable data today: price lookup, short-window movers, and trend-reading clues.")}</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("运营层", "Operations layer")}</p>
        <h2>{_lang_pair("关注列表、预警与诊断", "Watchlists, alerts, and diagnostics")}</h2>
        <p>{_lang_pair("用户已经可以追踪资产与预警，运营者也能公开比较数据源、池与信号质量。", "Users can already track assets and alerts, while operators can publicly compare source, pool, and signal quality.")}</p>
      </article>
    </section>

    <section class="wide-panel">
      <div>
        <p class="eyebrow">{_lang_pair("站点地图", "Site map")}</p>
        <h2>{_lang_pair("三个页面，刻意保持轻量", "Three pages, intentionally lightweight")}</h2>
      </div>
      <div class="sitemap-list">
        <a class="sitemap-item" href="/">
          <strong>{_lang_pair("首页", "Home")}</strong>
          <span>{_lang_pair("产品定位、当前阶段，以及 Flashcard Planet 刻意暂不提供的内容。", "Product positioning, current stage, and what Flashcard Planet is deliberately not offering yet.")}</span>
        </a>
        <a class="sitemap-item" href="/dashboard">
          <strong>{_lang_pair("实时仪表板", "Dashboard")}</strong>
          <span>{_lang_pair("价格查询、最高价值、涨跌榜、数据源快照，以及 High-Activity v2 诊断。", "Price lookup, top value, movers, source snapshots, and High-Activity v2 diagnostics.")}</span>
        </a>
        <a class="sitemap-item" href="/method">
          <strong>{_lang_pair("方法论 / 路线图", "Method / Roadmap")}</strong>
          <span>{_lang_pair("数据采集如何转化为信号，诊断如何影响决策，以及接下来的方向。", "How collection turns into signals, how diagnostics shape decisions, and where the product goes next.")}</span>
        </a>
      </div>
    </section>
    """
    return _render_shell(
        title="概览",
        current_path="/",
        body=body,
        page_key="landing",
        username=_session_username(request),
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("实时仪表板 / 演示", "Dashboard / Demo")}</p>
        <h1>{_lang_pair("公开展示当前数据与信号层的运行状态。", "Publicly show how the current data and signal layers are running.")}</h1>
        <p class="lede">
          {_lang_pair("这个页面刻意保持精简：价格查询、当前数据源健康度、最高价值、涨跌榜，以及正在指导下一轮评估的 High-Activity v2 诊断。",
          "This page stays intentionally tight: price lookup, current source health, top value, movers, and the High-Activity v2 diagnostics guiding the next evaluation cycle.")}
        </p>
      </div>
      <div class="intro-note">
        <strong>{_lang_pair("设计上刻意保持轻量", "Designed to stay light")}</strong>
        <p>{_lang_pair("这里的所有内容都服务于当前产品阶段。没有鉴权墙、没有支付，也没有交易市场脚手架。", "Everything here serves the current product phase. There is no auth wall, no payments, and no marketplace scaffolding.")}</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("价格查询", "Price lookup")}</p>
          <h2>{_lang_pair("搜索已追踪卡牌，查看最新价格", "Search tracked cards and view the latest price")}</h2>
        </div>
        <form class="lookup-form" id="price-lookup-form">
          <label class="sr-only" for="price-query">{_lang_pair("卡牌名称", "Card name")}</label>
          <input id="price-query" name="query" type="search" placeholder="试试 Umbreon、Pikachu 或 Charizard" />
          <button class="button button-primary" type="submit">{_lang_pair("查询", "Search")}</button>
        </form>
        <div class="sample-actions" id="sample-actions"></div>
        <p class="status-line" id="lookup-status">{_lang_pair("加载实时数据中...", "Loading live data...")}</p>
        <div class="lookup-results" id="lookup-results"></div>
        <div class="lookup-history" id="lookup-history"></div>
      </article>

      <article class="module" id="provider-snapshot">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("当前数据源快照", "Current provider snapshot")}</p>
          <h2>{_lang_pair("加载实时状态...", "Loading live status...")}</h2>
        </div>
        <div class="metric-stack skeleton-stack">
          <span></span><span></span><span></span>
        </div>
      </article>

      <article class="module" id="signal-ops">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("关注列表 / 预警 / 诊断", "Watchlists / Alerts / Diagnostics")}</p>
          <h2>{_lang_pair("信号操作", "Signal operations")}</h2>
        </div>
        <div class="metric-stack skeleton-stack">
          <span></span><span></span><span></span>
        </div>
      </article>

      <article class="module" id="top-value">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("最高价值", "Top value")}</p>
          <h2>{_lang_pair("当前最高价格卡牌", "Current highest-priced cards")}</h2>
        </div>
        <div class="list-shell skeleton-stack"><span></span><span></span><span></span></div>
      </article>

      <article class="module" id="top-movers">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("涨跌榜", "Movers")}</p>
          <h2>{_lang_pair("近期最大价格变动", "Largest recent price moves")}</h2>
        </div>
        <div class="list-shell skeleton-stack"><span></span><span></span><span></span></div>
      </article>

      <article class="module" id="smart-pool-module">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("智能池候选", "Smart Pool Candidates")}</p>
          <h2>{_lang_pair("智能池候选", "Smart Pool Candidates")}</h2>
        </div>
        <div class="list-shell skeleton-stack" id="smart-pool-list"><span></span><span></span><span></span></div>
      </article>

      <article class="module module-wide" id="high-activity-module">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("高活跃度 v2 对比基准", "High-Activity v2 vs baseline")}</p>
          <h2>{_lang_pair("加载诊断对比中...", "Loading diagnostic comparison...")}</h2>
        </div>
        <div class="explanation-grid">
          <div class="explanation-copy skeleton-stack"><span></span><span></span><span></span></div>
          <div class="pool-grid" id="pool-grid"></div>
        </div>
      </article>
    </section>
    """
    return _render_shell(
        title="实时仪表板",
        current_path="/dashboard",
        body=body,
        page_key="dashboard",
        username=_session_username(request),
    )


@router.get("/cards", response_class=HTMLResponse)
def cards_page(
    request: Request,
    set_id: str | None = Query(None, alias="set"),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    with SessionLocal() as db:
        source_filter = get_active_price_source_filter(db)
        ranked = build_ranked_price_subquery(source_filter)
        latest = select(ranked).where(ranked.c.price_rank == 1).subquery("latest_card_price")

        set_rows = db.execute(
            select(
                Asset.metadata_json["set_id"].astext.label("set_id"),
                Asset.set_name,
            )
            .where(
                Asset.category == "Pokemon",
                Asset.set_name.is_not(None),
                Asset.metadata_json["set_id"].astext.is_not(None),
            )
            .distinct()
            .order_by(Asset.set_name.asc())
        ).all()

        set_options = [
            (row.set_id, row.set_name)
            for row in set_rows
            if row.set_id and row.set_name
        ]

        filters = [Asset.category == "Pokemon", Asset.external_id.is_not(None)]
        if set_id:
            filters.append(Asset.metadata_json["set_id"].astext == set_id)
        if q:
            filters.append(Asset.name.ilike(f"%{q}%"))

        total_cards = int(
            db.scalar(
                select(func.count(Asset.id)).where(*filters)
            )
            or 0
        )
        total_pages = max(1, ceil(total_cards / CARDS_PER_PAGE)) if total_cards else 1
        current_page = min(page, total_pages)
        offset = (current_page - 1) * CARDS_PER_PAGE

        rows = db.execute(
            select(
                Asset.external_id,
                Asset.name,
                Asset.set_name,
                Asset.card_number,
                Asset.variant,
                latest.c.price.label("latest_price"),
                latest.c.currency.label("currency"),
                Asset.metadata_json["images"]["small"].astext.label("image_small"),
            )
            .outerjoin(latest, latest.c.asset_id == Asset.id)
            .where(*filters)
            .order_by(
                Asset.set_name.asc(),
                Asset.name.asc(),
                Asset.card_number.asc(),
                Asset.id.asc(),
            )
            .offset(offset)
            .limit(CARDS_PER_PAGE)
        ).all()

    selected_set_name = next((label for value, label in set_options if value == set_id), None)
    filters_summary_parts_zh: list[str] = []
    filters_summary_parts_en: list[str] = []
    if selected_set_name:
        filters_summary_parts_zh.append(f"系列 {escape(selected_set_name)}")
        filters_summary_parts_en.append(f"Set {escape(selected_set_name)}")
    if q:
        filters_summary_parts_zh.append(f"搜索 “{escape(q)}”")
        filters_summary_parts_en.append(f'Search "{escape(q)}"')
    filters_summary_zh = "，筛选条件：" + "，".join(filters_summary_parts_zh) if filters_summary_parts_zh else ""
    filters_summary_en = ", filters: " + ", ".join(filters_summary_parts_en) if filters_summary_parts_en else ""

    option_markup = [f'<option value="">{_lang_pair("全部系列", "All sets")}</option>']
    for option_set_id, option_set_name in set_options:
        selected_attr = ' selected="selected"' if option_set_id == set_id else ""
        option_markup.append(
            f'<option value="{escape(option_set_id)}"{selected_attr}>{escape(option_set_name)}</option>'
        )

    if rows:
        def _card_img_markup(image_small: str | None, name: str) -> str:
            if not image_small:
                return ""
            return f'<img class="card-list-thumb" src="{escape(image_small)}" alt="{escape(name)}" loading="lazy" />'

        row_markup = "".join(
            """
            <tr>
              <td><a class="table-link card-list-name-cell" href="/cards/{external_id}">{thumb}{name}</a></td>
              <td>{set_name}</td>
              <td>{card_number}</td>
              <td>{variant}</td>
              <td>{latest_price}</td>
            </tr>
            """.format(
                external_id=escape(row.external_id or ""),
                thumb=_card_img_markup(row.image_small, row.name),
                name=escape(row.name),
                set_name=escape(row.set_name or "未知系列"),
                card_number=escape(row.card_number or "N/A"),
                variant=escape(row.variant or "标准版"),
                latest_price=escape(
                    _format_currency(
                        Decimal(row.latest_price) if row.latest_price is not None else None,
                        row.currency or "USD",
                    )
                ),
            )
            for row in rows
        )
    else:
        row_markup = """
            <tr>
              <td colspan="5" class="empty-state-cell">{empty_text}</td>
            </tr>
        """.format(empty_text=_lang_pair("未找到卡牌。", "No cards found."))

    pager_links: list[str] = []
    if current_page > 1:
        prev_query = _build_cards_query_params(set_id=set_id, q=q, page=current_page - 1)
        pager_links.append(f'<a class="button button-secondary" href="/cards?{escape(prev_query)}">{_lang_pair("上一页", "Previous")}</a>')
    if current_page < total_pages:
        next_query = _build_cards_query_params(set_id=set_id, q=q, page=current_page + 1)
        pager_links.append(f'<a class="button button-secondary" href="/cards?{escape(next_query)}">{_lang_pair("下一页", "Next")}</a>')
    pager_markup = "".join(pager_links)
    reset_href = "/cards"

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("卡牌浏览", "Cards")}</p>
        <h1>{_lang_pair("浏览所有已追踪的宝可梦卡牌。", "Browse every tracked Pokemon card.")}</h1>
        <p class="lede">
          {_lang_pair("这个页面紧贴数据层：支持系列筛选、名称搜索、直达卡牌详情，以及查看每张已追踪卡牌当前数据源下的最新价格。",
          "This page stays close to the data layer: filter by set, search by name, jump into card details, and inspect the latest price for every tracked card under the current source.")}
        </p>
      </div>
      <div class="intro-note">
        <strong>{_lang_pair(f"共 {total_cards} 张已追踪卡牌", f"{total_cards} tracked cards")}</strong>
        <p>{_lang_pair(f"当前第 {current_page} / {total_pages} 页{filters_summary_zh}。", f"Page {current_page} / {total_pages}{filters_summary_en}.")}</p>
      </div>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">{_lang_pair("筛选条件", "Filters")}</p>
        <h2>{_lang_pair("按名称搜索或按系列筛选", "Search by name or filter by set")}</h2>
      </div>
      <form class="card-filter-form" method="get" action="/cards">
        <label>
          <span>{_lang_pair("按系列筛选", "Filter by set")}</span>
          <select name="set">
            {"".join(option_markup)}
          </select>
        </label>
        <label>
          <span>{_lang_pair("按名称搜索", "Search by name")}</span>
          <input type="search" name="q" value="{escape(q or '')}" placeholder="例如 Charizard" />
        </label>
        <input type="hidden" name="page" value="1" />
        <div class="card-filter-actions">
          <button class="button button-primary" type="submit">{_lang_pair("搜索", "Search")}</button>
          <a class="button button-secondary" href="{reset_href}">{_lang_pair("重置", "Reset")}</a>
        </div>
      </form>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">{_lang_pair("卡牌浏览", "Cards")}</p>
        <h2>{_lang_pair("每页 50 张卡牌", "50 cards per page")}</h2>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>{_lang_pair("名称", "Name")}</th>
              <th>{_lang_pair("系列", "Set")}</th>
              <th>{_lang_pair("编号", "Number")}</th>
              <th>{_lang_pair("版本", "Variant")}</th>
              <th>{_lang_pair("最新价格", "Latest price")}</th>
            </tr>
          </thead>
          <tbody>
            {row_markup}
          </tbody>
        </table>
      </div>
      <div class="pagination-bar">
        <p class="status-line">{_lang_pair(f"第 {current_page} / {total_pages} 页", f"Page {current_page} / {total_pages}")}</p>
        <div class="pagination-actions">{pager_markup}</div>
      </div>
    </section>
    """
    return _render_shell(
        title="卡牌浏览",
        current_path="/cards",
        body=body,
        page_key="cards",
        username=_session_username(request),
    )


@router.get("/cards/{external_id}", response_class=HTMLResponse)
def card_detail_page(request: Request, external_id: str) -> HTMLResponse:
    import uuid as _uuid

    username = _session_username(request)
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None

    with SessionLocal() as db:
        # Resolve current user to determine access tier
        current_user = None
        if user_id:
            try:
                current_user = db.get(User, _uuid.UUID(user_id))
            except Exception:
                current_user = None
        access_tier = current_user.access_tier if current_user else "free"

        # Look up asset by external_id (needed for tcgplayer URL + 404 check)
        asset = db.scalars(
            select(Asset).where(Asset.category == "Pokemon", Asset.external_id == external_id)
        ).first()
        if asset is None:
            raise HTTPException(status_code=404, detail="卡牌不存在。")

        vm = build_card_detail(db, asset.id, access_tier=access_tier)

    if vm is None:
        raise HTTPException(status_code=404, detail="卡牌不存在。")

    tcgplayer_url = _get_metadata_tcgplayer_url(asset)
    image_small = vm.image_url
    latest_price = vm.latest_price
    currency = vm.currency or "USD"
    latest_captured_at = (
        vm.price_history[0].captured_at.strftime("%Y-%m-%d %H:%M UTC")
        if vm.price_history
        else "N/A"
    )

    price_labels = [pt.captured_at.strftime("%Y-%m-%d") for pt in reversed(vm.price_history)]
    price_values = [float(pt.price) for pt in reversed(vm.price_history)]
    chart_script_tag = ""
    chart_markup = f"<p>{_lang_pair('暂无足够数据生成走势图。', 'Not enough data to render a chart yet.')}</p>"
    chart_inline_script = ""
    if len(vm.price_history) >= 2:
        chart_script_tag = (
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>'
        )
        chart_markup = "<canvas id='price-chart'></canvas>"
        chart_inline_script = f"""
        <script>
          (() => {{
            const chartCanvas = document.getElementById("price-chart");
            if (!chartCanvas || typeof Chart === "undefined") {{
              return;
            }}
            new Chart(chartCanvas, {{
              type: "line",
              data: {{
                labels: {json.dumps(price_labels)},
                datasets: [{{
                  label: "价格走势 (USD)",
                  data: {json.dumps(price_values)},
                  borderColor: "#00e5c8",
                  pointBackgroundColor: "#00e5c8",
                  pointBorderColor: "#00e5c8",
                  backgroundColor: "rgba(0,229,200,0.07)",
                  fill: true,
                  tension: 0.3,
                }}],
              }},
              options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                  x: {{
                    grid: {{
                      color: "rgba(255,255,255,0.06)",
                    }},
                    ticks: {{
                      color: "#3d4f66",
                    }},
                  }},
                  y: {{
                    grid: {{
                      color: "rgba(255,255,255,0.06)",
                    }},
                    ticks: {{
                      color: "#3d4f66",
                    }},
                  }},
                }},
              }},
            }});
          }})();
        </script>
        """

    history_markup = "".join(
        """
        <tr>
          <td>{captured_at}</td>
          <td>{price}</td>
          <td>{source}</td>
        </tr>
        """.format(
            captured_at=escape(pt.captured_at.strftime("%Y-%m-%d %H:%M UTC")),
            price=escape(_format_currency(pt.price, currency)),
            source=escape(pt.source),
        )
        for pt in reversed(vm.price_history)
    )
    if not history_markup:
        history_markup = """
        <tr>
          <td colspan="3" class="empty-state-cell">{empty_text}</td>
        </tr>
        """.format(empty_text=_lang_pair("暂无价格历史数据。", "No price history available."))

    truncated_banner = ""
    if vm.history_truncated:
        truncated_banner = f"""
        <div class="progate-banner">
          <p>
            {_lang_pair(
                "免费账户仅显示最近 7 天价格记录。",
                "Free accounts show the last 7 days of price history only."
            )}
            <a href="/upgrade">{_lang_pair("升级至 Pro 解锁完整历史数据 →", "Upgrade to Pro for full history →")}</a>
          </p>
        </div>
        """

    image_markup = (
        f'<div class="card-image-panel"><img src="{escape(image_small)}" alt="{escape(asset.name)}" /></div>'
        if image_small
        else f'<div class="card-image-panel card-image-empty"><p class="status-line">{_lang_pair("暂无卡牌图片。", "No card image available.")}</p></div>'
    )
    tcgplayer_markup = (
        f'<a class="button button-secondary" href="{escape(tcgplayer_url)}" target="_blank" rel="noreferrer">{_lang_pair("在 TCGPlayer 上查看", "View on TCGPlayer")}</a>'
        if tcgplayer_url
        else ""
    )

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("卡牌详情", "Card detail")}</p>
        <h1>{escape(asset.name)}</h1>
        <p class="lede">
          {_lang_pair(f"{asset.set_name or '未知系列'} #{asset.card_number or 'N/A'} 已收录于当前追踪卡牌目录，下方展示该卡牌当前数据源下的最新价格记录与近期价格历史。",
          f"{asset.set_name or 'Unknown set'} #{asset.card_number or 'N/A'} is part of the tracked card catalog, and the latest source price plus recent history are shown below.")}
        </p>
      </div>
      <div class="intro-note">
        <strong>{escape(_format_currency(latest_price, currency))}</strong>
        <p>{_lang_pair(f"最新价格采集时间：{latest_captured_at}。", f"Latest price captured at: {latest_captured_at}.")}</p>
      </div>
    </section>

    <section class="card-detail-grid">
      {image_markup}
      <article class="module">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("卡牌信息", "Card info")}</p>
          <h2>{_lang_pair("卡牌详情", "Card detail")}</h2>
        </div>
        <dl class="detail-list">
          <div><dt>{_lang_pair("名称", "Name")}</dt><dd>{escape(asset.name)}</dd></div>
          <div><dt>{_lang_pair("系列", "Set")}</dt><dd>{escape(asset.set_name or "未知系列")}</dd></div>
          <div><dt>{_lang_pair("编号", "Number")}</dt><dd>{escape(asset.card_number or "N/A")}</dd></div>
          <div><dt>{_lang_pair("年份", "Year")}</dt><dd>{escape(str(asset.year) if asset.year is not None else "N/A")}</dd></div>
          <div><dt>{_lang_pair("版本", "Variant")}</dt><dd>{escape(asset.variant or "标准版")}</dd></div>
          <div><dt>{_lang_pair("卡牌ID", "Card ID")}</dt><dd>{escape(asset.external_id or "N/A")}</dd></div>
          <div><dt>{_lang_pair("最新价格", "Latest price")}</dt><dd>{escape(_format_currency(latest_price, currency))}</dd></div>
        </dl>
        <div class="detail-actions">
          <a class="button button-primary" href="/cards">{_lang_pair("返回卡牌浏览", "Back to cards")}</a>
          {tcgplayer_markup}
        </div>
      </article>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">{_lang_pair("价格历史", "Price history")}</p>
        <h2>{_lang_pair("价格记录", "Price records")}</h2>
      </div>
      {truncated_banner}
      {chart_markup}
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>{_lang_pair("日期", "Date")}</th>
              <th>{_lang_pair("价格", "Price")}</th>
              <th>{_lang_pair("数据源", "Source")}</th>
            </tr>
          </thead>
          <tbody>
            {history_markup}
          </tbody>
        </table>
      </div>
    </section>
    {chart_script_tag}
    {chart_inline_script}
    """
    return _render_shell(
        title=asset.name,
        current_path="/cards",
        body=body,
        page_key="card-detail",
        username=username,
    )


@router.get("/signals", response_class=HTMLResponse)
def signals_page(
    request: Request,
    label: str | None = Query(None),
) -> HTMLResponse:
    username = _session_username(request)
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None

    with SessionLocal() as db:
        current_user = None
        if user_id:
            from backend.app.models.user import User
            import uuid as _uuid

            try:
                current_user = db.get(User, _uuid.UUID(user_id))
            except Exception:
                current_user = None

        is_pro = can(current_user.access_tier, Feature.PRICE_HISTORY_FULL) if current_user else False

        label_filter = label.upper() if label else None
        valid_labels = {"BREAKOUT", "MOVE", "WATCH", "IDLE"}
        if label_filter and label_filter not in valid_labels:
            label_filter = None

        try:
            snapshots = get_daily_snapshot_signals(db, label=label_filter)
        except Exception as exc:
            logger.exception("signals_page: get_daily_snapshot_signals failed: %s", exc)
            snapshots = []

        asset_ids = [snap.asset_id for snap in snapshots]
        asset_rows = (
            db.execute(
                select(Asset.id, Asset.name, Asset.set_name, Asset.variant)
                .where(Asset.id.in_(asset_ids))
            ).all()
            if asset_ids
            else []
        )
        asset_map = {row.id: row for row in asset_rows}

        live_map = {}
        if is_pro:
            try:
                live_signals = get_all_signals(db, limit=500)
                if label_filter:
                    live_signals = [s for s in live_signals if s.label == label_filter]
                live_map = {s.asset_id: s for s in live_signals}
            except Exception as exc:
                logger.exception("signals_page: get_all_signals failed: %s", exc)
                live_map = {}

    filter_links = ""
    for lbl, zh, en in [
        (None, "全部", "All"),
        ("BREAKOUT", "BREAKOUT", "BREAKOUT"),
        ("MOVE", "MOVE", "MOVE"),
        ("WATCH", "WATCH", "WATCH"),
        ("IDLE", "IDLE", "IDLE"),
    ]:
        href = "/signals" if lbl is None else f"/signals?label={lbl}"
        active = " is-active" if label_filter == lbl else ""
        filter_links += (
            f'<a class="signal-filter-link{active}" href="{href}">'
            f"{_lang_pair(zh, en)}"
            "</a>"
        )

    rows_html = ""
    if not snapshots:
        rows_html = (
            f'<p class="empty-state">'
            f'{_lang_pair("尚无每日快照，请在积累满第一天数据后回来查看。", "No daily snapshot available yet - check back after the first full day of data.")}'
            "</p>"
        )
    else:
        for snap in snapshots:
            asset = asset_map.get(snap.asset_id)
            if asset is None:
                logger.warning("signals_page: unresolvable asset_id=%s, skipping", snap.asset_id)
                continue

            asset_name = escape(asset.name)
            asset_details: list[str] = []
            if asset.set_name:
                asset_details.append(escape(asset.set_name))
            if asset.variant:
                asset_details.append(escape(asset.variant))
            if asset_details:
                asset_name += f' <span class="asset-set">{" · ".join(asset_details)}</span>'

            left_card = _render_snapshot_card(snap, asset_name)
            live_signal = live_map.get(snap.asset_id) if is_pro else None
            right_card = _render_live_card(live_signal, is_pro)

            rows_html += f"""
            <div class="signal-row">
              {left_card}
              {right_card}
            </div>"""

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("市场信号", "Signals")}</p>
        <h1>{_lang_pair("每日快照与实时信号层", "Daily snapshots and live signal layer")}</h1>
        <p class="lede">
          {_lang_pair("免费用户可查看每日快照信号。升级到 Pro 解锁实时信号与 AI 解读。", "Free users see daily snapshot signals. Upgrade to Pro for live signals and AI explanations.")}
        </p>
      </div>
    </section>

    <section class="signal-page">
      <div class="signal-filter-bar">
        {filter_links}
      </div>
      <div class="signal-rows">
        {rows_html}
      </div>
    </section>
    """

    return _render_shell(
        title="Signals",
        current_path="/signals",
        body=body,
        page_key="signals",
        username=username,
    )


_LABEL_COLOURS = {
    "BREAKOUT": "signal-breakout",
    "MOVE": "signal-move",
    "WATCH": "signal-watch",
    "IDLE": "signal-idle",
}


def _render_snapshot_card(snap: AssetSignalHistory, asset_name_html: str) -> str:
    colour = _LABEL_COLOURS.get(snap.label, "signal-idle")
    delta = f"{snap.price_delta_pct:+.2f}%" if snap.price_delta_pct is not None else "N/A"
    conf = str(snap.confidence) if snap.confidence is not None else "N/A"
    liq = str(snap.liquidity_score) if snap.liquidity_score is not None else "N/A"
    pred = escape(snap.prediction) if snap.prediction else "N/A"
    ts = snap.computed_at.strftime("%d %b %Y, %I:%M %p UTC") if snap.computed_at else "N/A"

    return f"""
    <div class="signal-card signal-card-snapshot">
      <p class="signal-card-header">{_lang_pair("每日快照", "Daily Snapshot")}</p>
      <p class="signal-asset-name">{asset_name_html}</p>
      <span class="signal-badge {colour}">{escape(snap.label)}</span>
      <dl class="signal-metrics">
        <dt>{_lang_pair("置信度", "Confidence")}</dt><dd>{conf}</dd>
        <dt>{_lang_pair("价格变化", "Price Delta")}</dt><dd>{delta}</dd>
        <dt>{_lang_pair("流动性", "Liquidity")}</dt><dd>{liq}</dd>
        <dt>{_lang_pair("预测", "Prediction")}</dt><dd>{pred}</dd>
      </dl>
      <p class="signal-timestamp">{_lang_pair("截至", "As of")} {ts}</p>
    </div>"""


def _render_live_card(live_signal, is_pro: bool) -> str:
    if not is_pro:
        return f"""
    <div class="signal-card signal-card-locked">
      <p class="signal-card-header">{_lang_pair("实时信号", "Live Signal")} <span class="pro-badge">PRO</span></p>
      <div class="signal-locked-shell">
        <span class="skeleton-line"></span>
        <span class="skeleton-line skeleton-line-short"></span>
        <span class="skeleton-line"></span>
        <span class="skeleton-line skeleton-line-short"></span>
      </div>
      <p class="signal-locked-copy">{_lang_pair("解锁实时标签、置信度、涨跌幅与 AI 解读", "Unlock live label, confidence, delta, and AI explanation")}</p>
      <a class="button button-primary signal-pro-cta" href="/pro">Go Pro</a>
    </div>"""

    if live_signal is None:
        return f"""
    <div class="signal-card signal-card-live signal-card-awaiting">
      <p class="signal-card-header">{_lang_pair("实时信号", "Live Signal")}</p>
      <p class="signal-awaiting">{_lang_pair("等待下一次扫描", "Awaiting next sweep")}</p>
    </div>"""

    colour = _LABEL_COLOURS.get(live_signal.label, "signal-idle")
    delta = f"{live_signal.price_delta_pct:+.2f}%" if live_signal.price_delta_pct is not None else "N/A"
    conf = str(live_signal.confidence) if live_signal.confidence is not None else "N/A"
    liq = str(live_signal.liquidity_score) if live_signal.liquidity_score is not None else "N/A"
    pred = escape(live_signal.prediction) if live_signal.prediction else "N/A"
    ts = live_signal.computed_at.strftime("%d %b %Y, %I:%M %p UTC") if live_signal.computed_at else "N/A"

    return f"""
    <div class="signal-card signal-card-live">
      <p class="signal-card-header">{_lang_pair("实时信号", "Live Signal")}</p>
      <span class="signal-badge {colour}">{escape(live_signal.label)}</span>
      <dl class="signal-metrics">
        <dt>{_lang_pair("置信度", "Confidence")}</dt><dd>{conf}</dd>
        <dt>{_lang_pair("价格变化", "Price Delta")}</dt><dd>{delta}</dd>
        <dt>{_lang_pair("流动性", "Liquidity")}</dt><dd>{liq}</dd>
        <dt>{_lang_pair("预测", "Prediction")}</dt><dd>{pred}</dd>
      </dl>
      <p class="signal-timestamp">{_lang_pair("更新于", "Updated")} {ts}</p>
    </div>"""


@router.get("/method", response_class=HTMLResponse)
def method_page(request: Request) -> HTMLResponse:
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("方法论 / 路线图", "Method / Roadmap")}</p>
        <h1>{_lang_pair("先建数据层，再做信号层，其余一切推后。", "Build the data layer first, then the signal layer, and defer everything else.")}</h1>
        <p class="lede">
          {_lang_pair("Flashcard Planet 有意按顺序推进：先做数据源支持的数据采集、池诊断、可解释的信号输出与关注列表工作流。在数据层值得信任之前，交易市场层暂不介入。",
          "Flashcard Planet is advancing in order on purpose: source-backed collection, pool diagnostics, explainable signal output, and watchlist workflows first. The marketplace layer stays out until the data layer is trustworthy.")}
        </p>
      </div>
    </section>

    <section class="timeline-grid">
      <article class="timeline-card">
        <p class="card-kicker">{_lang_pair("当前", "Current")}</p>
        <h2>{_lang_pair("数据层", "Data layer")}</h2>
        <ul class="clean-list">
          <li>{_lang_pair("数据源支持的价格采集", "Source-backed price collection")}</li>
          <li>{_lang_pair("追踪池对比分析", "Tracked-pool comparison")}</li>
          <li>{_lang_pair("历史深度与低覆盖率诊断", "History-depth and low-coverage diagnostics")}</li>
          <li>{_lang_pair("通过轻量仪表板进行公开验证", "Public validation through a lightweight dashboard")}</li>
        </ul>
      </article>
      <article class="timeline-card">
        <p class="card-kicker">{_lang_pair("当前", "Current")}</p>
        <h2>{_lang_pair("信号层", "Signal layer")}</h2>
        <ul class="clean-list">
          <li>{_lang_pair("价格查询与近期历史", "Price lookup and recent history")}</li>
          <li>{_lang_pair("最高价值与涨跌榜", "Top value and movers")}</li>
          <li>{_lang_pair("方向性预测评分", "Directional prediction scoring")}</li>
          <li>{_lang_pair("关注列表与预警规则", "Watchlists and alert rules")}</li>
        </ul>
      </article>
      <article class="timeline-card">
        <p class="card-kicker">{_lang_pair("下一步", "Next")}</p>
        <h2>{_lang_pair("运营路线图", "Operations roadmap")}</h2>
        <ul class="clean-list">
          <li>{_lang_pair("继续测试 High-Activity v2 与基准池的表现差异", "Keep testing the performance gap between High-Activity v2 and the baseline pool")}</li>
          <li>{_lang_pair("在积累更多观察后决定是否需要引入第二个数据源", "Decide on a second data source only after more observation is collected")}</li>
          <li>{_lang_pair("仅在诊断结果稳定后再扩展公开网站", "Expand the public site only after diagnostics stabilize")}</li>
          <li>{_lang_pair("在任何商业化流程之前先完善预警体验", "Improve the alert experience before any commercialization flow")}</li>
        </ul>
      </article>
    </section>

    <section class="method-grid">
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("第 1 步", "Step 1")}</p>
        <h2>{_lang_pair("采集并标准化", "Collect and normalize")}</h2>
        <p>{_lang_pair("持续从数据源抓取数据，形成单卡级别的价格历史，同时明确展示当前启用的是哪个数据源。", "Continuously fetch from the source, build per-card price history, and clearly show which source is currently active.")}</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("第 2 步", "Step 2")}</p>
        <h2>{_lang_pair("诊断数据池", "Diagnose pools")}</h2>
        <p>{_lang_pair("通过追踪池、High-Activity v2 与低覆盖标记，判断弱信号究竟来自样本选择还是覆盖不足。", "Use tracked pools, High-Activity v2, and low-coverage markers to tell whether weak signals come from sample choice or missing coverage.")}</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("第 3 步", "Step 3")}</p>
        <h2>{_lang_pair("呈现信号", "Present signals")}</h2>
        <p>{_lang_pair("价格查询、涨跌榜、最高价值与轻量预测文案，把原始数据转化为用户可执行的信息。", "Price lookup, movers, top value, and lightweight prediction copy turn raw data into actionable information.")}</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">{_lang_pair("第 4 步", "Step 4")}</p>
        <h2>{_lang_pair("闭环运营流程", "Close the loop")}</h2>
        <p>{_lang_pair("关注列表与预警紧贴当前产品阶段，同时由诊断结果指导下一步的数据源决策。", "Watchlists and alerts stay aligned with the current phase, while diagnostic results guide the next source decision.")}</p>
      </article>
    </section>

    <section class="wide-panel">
      <div>
        <p class="eyebrow">{_lang_pair("刻意排除的功能", "Deliberately excluded")}</p>
        <h2>{_lang_pair("当前 MVP 尚未包含的内容", "What the current MVP does not include")}</h2>
      </div>
      <div class="sitemap-list">
        <div class="sitemap-item static">
          <strong>{_lang_pair("无交易市场", "No marketplace")}</strong>
          <span>{_lang_pair("不提供挂单、结账、买家流程、卖家主页或支付能力。", "There are no listings, checkout, buyer flows, seller pages, or payment capability.")}</span>
        </div>
        <div class="sitemap-item static">
          <strong>{_lang_pair("无臃肿平台框架", "No bloated platform shell")}</strong>
          <span>{_lang_pair("不做以鉴权为先的复杂产品迷宫，不做引导漏斗，也不堆砌臃肿仪表板。", "No auth-first product maze, no funnel theater, and no bloated dashboard stack.")}</span>
        </div>
        <div class="sitemap-item static">
          <strong>{_lang_pair("不盲目扩展覆盖范围", "No blind expansion")}</strong>
          <span>{_lang_pair("当前重点仍是有针对性的诊断，而不是过早地大范围铺开覆盖。", "The focus is still targeted diagnostics, not expanding coverage too broadly too early.")}</span>
        </div>
      </div>
    </section>
    """
    return _render_shell(
        title="方法论 / 路线图",
        current_path="/method",
        body=body,
        page_key="method",
        username=_session_username(request),
    )


@router.get("/watchlists", response_class=HTMLResponse)
def watchlists_page(request: Request) -> HTMLResponse:
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None
    if not user_id and get_settings().discord_client_id:
        return RedirectResponse("/auth/login", status_code=302)
    api_base = f"{settings.api_prefix}/watchlists"
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("关注列表", "Watchlists")}</p>
        <h1>{_lang_pair("在网页端管理你的关注列表。", "Manage your watchlists on the web.")}</h1>
        <p class="lede">
          {_lang_pair("输入 Discord 用户 ID 与卡牌名称，即可创建、查看或删除关注条目。所有操作直接调用现有 API。",
          "Enter a Discord user ID and card name to create, view, or delete watchlist entries. All actions call the existing API directly.")}
        </p>
      </div>
      <div class="intro-note">
        <strong>{_lang_pair("API 驱动", "API-driven")}</strong>
        <p>{_lang_pair("通过 JavaScript fetch 直接调用 watchlist API，无需刷新页面。", "The page calls the watchlist API directly through JavaScript fetch with no page reload.")}</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("添加关注", "Add watchlist item")}</p>
          <h2>{_lang_pair("创建关注条目", "Create watchlist entry")}</h2>
        </div>
        <form class="card-filter-form" id="watchlist-create-form">
          <label>
            <span>{_lang_pair("Discord 用户 ID", "Discord user ID")}</span>
            <input id="create-discord-user-id" name="discord_user_id" type="text" required />
          </label>
          <label>
            <span>{_lang_pair("卡牌名称", "Card name")}</span>
            <input id="create-asset-name" name="asset_name" type="text" required />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" type="submit">{_lang_pair("添加", "Add")}</button>
          </div>
        </form>
        <p class="status-line" id="watchlist-create-status">{_lang_pair("就绪。", "Ready.")}</p>
      </article>

      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("查询", "Lookup")}</p>
          <h2>{_lang_pair("查看并删除已保存的关注条目", "View and delete saved watchlist entries")}</h2>
        </div>
        <div class="card-filter-form">
          <label>
            <span>{_lang_pair("Discord 用户 ID", "Discord user ID")}</span>
            <input id="lookup-discord-user-id" name="lookup_discord_user_id" type="text" />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" id="watchlist-view-button" type="button">{_lang_pair("查询", "Search")}</button>
          </div>
        </div>
        <p class="status-line" id="watchlist-lookup-status">{_lang_pair("输入 Discord 用户 ID 以加载关注列表。", "Enter a Discord user ID to load watchlists.")}</p>
        <ul class="clean-list" id="watchlist-results"></ul>
      </article>
    </section>

    <script>
      (() => {{
        const apiBase = {api_base!r};
        const createForm = document.getElementById("watchlist-create-form");
        const createStatus = document.getElementById("watchlist-create-status");
        const lookupInput = document.getElementById("lookup-discord-user-id");
        const viewButton = document.getElementById("watchlist-view-button");
        const lookupStatus = document.getElementById("watchlist-lookup-status");
        const results = document.getElementById("watchlist-results");

        const escapeHtml = (value) => {{
          const span = document.createElement("span");
          span.textContent = value ?? "";
          return span.innerHTML;
        }};

        const loadWatchlist = async (userId) => {{
          if (!userId) {{ lookupStatus.textContent = "请输入 Discord 用户 ID。"; return; }}
          lookupStatus.textContent = "加载中...";
          results.innerHTML = "";
          try {{
            const res = await fetch(`${{apiBase}}/${{encodeURIComponent(userId)}}`);
            if (!res.ok) {{ lookupStatus.textContent = `出错了：HTTP ${{res.status}}`; return; }}
            const items = await res.json();
            if (!items.length) {{ lookupStatus.textContent = "该用户暂无关注条目。"; return; }}
            lookupStatus.textContent = `共 ${{items.length}} 条关注。`;
            items.forEach(item => {{
              const li = document.createElement("li");
              li.innerHTML = `<span>${{escapeHtml(item.asset_name ?? item.name ?? JSON.stringify(item))}}</span>
                <button class="button button-secondary" data-user="${{escapeHtml(userId)}}" data-name="${{escapeHtml(item.asset_name ?? item.name ?? "")}}">删除</button>`;
              li.querySelector("button").addEventListener("click", async (e) => {{
                const btn = e.currentTarget;
                btn.disabled = true;
                const delRes = await fetch(`${{apiBase}}?discord_user_id=${{encodeURIComponent(btn.dataset.user)}}&asset_name=${{encodeURIComponent(btn.dataset.name)}}`, {{method: "DELETE"}});
                if (delRes.ok) {{ li.remove(); lookupStatus.textContent = "已删除。"; }}
                else {{ btn.disabled = false; lookupStatus.textContent = "删除失败。"; }}
              }});
              results.appendChild(li);
            }});
          }} catch (err) {{ lookupStatus.textContent = `出错了：${{err.message}}`; }}
        }};

        viewButton.addEventListener("click", () => loadWatchlist(lookupInput.value.trim()));
        lookupInput.addEventListener("keydown", (e) => {{ if (e.key === "Enter") loadWatchlist(lookupInput.value.trim()); }});

        createForm.addEventListener("submit", async (e) => {{
          e.preventDefault();
          const userId = document.getElementById("create-discord-user-id").value.trim();
          const assetName = document.getElementById("create-asset-name").value.trim();
          if (!userId || !assetName) {{ createStatus.textContent = "请填写所有字段。"; return; }}
          createStatus.textContent = "提交中...";
          try {{
            const res = await fetch(apiBase, {{
              method: "POST",
              headers: {{"Content-Type": "application/json"}},
              body: JSON.stringify({{discord_user_id: userId, asset_name: assetName}}),
            }});
            const data = await res.json();
            createStatus.textContent = res.ok ? (data.message ?? "已添加。") : (data.detail ?? "出错了。");
          }} catch (err) {{ createStatus.textContent = `出错了：${{err.message}}`; }}
        }});
      }})();
    </script>
    """
    return _render_shell(
        title="关注列表",
        current_path="/watchlists",
        body=body,
        page_key="watchlists",
        username=_session_username(request),
    )


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request) -> HTMLResponse:
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None
    if not user_id and get_settings().discord_client_id:
        return RedirectResponse("/auth/login", status_code=302)
    api_base = f"{settings.api_prefix}/alerts"
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("预警管理", "Alerts")}</p>
        <h1>{_lang_pair("创建、查询并维护价格预警", "Create, query, and maintain price alerts")}</h1>
        <p class="lede">
          {_lang_pair("使用现有的 /api/v1/alerts 接口创建预警、按 Discord 用户 ID 查询当前预警，并在表格里执行删除或停用操作。",
          "Use the existing /api/v1/alerts endpoint to create alerts, query current alerts by Discord user ID, and delete or disable them from the table.")}
        </p>
      </div>
      <div class="intro-note">
        <strong>{_lang_pair("API 联动", "API-connected")}</strong>
        <p>{_lang_pair("页面通过浏览器端 fetch() 直接请求预警接口，交互方式与关注列表页面保持一致。", "The page calls the alerts endpoint directly with browser-side fetch() and uses the same interaction pattern as the watchlists page.")}</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("创建预警", "Create alert")}</p>
          <h2>{_lang_pair("新增预警规则", "Add a new alert rule")}</h2>
        </div>
        <form class="card-filter-form" id="alert-create-form">
          <label>
            <span>{_lang_pair("Discord 用户 ID", "Discord user ID")}</span>
            <input id="alert-create-user-id" name="discord_user_id" type="text" required />
          </label>
          <label>
            <span>{_lang_pair("卡牌名称", "Card name")}</span>
            <input id="alert-create-asset-name" name="asset_name" type="text" required />
          </label>
          <label>
            <span>{_lang_pair("预警类型", "Alert type")}</span>
            <select id="alert-create-type" name="alert_type">
              <option value="PRICE_UP_THRESHOLD">PRICE_UP_THRESHOLD</option>
              <option value="PRICE_DOWN_THRESHOLD">PRICE_DOWN_THRESHOLD</option>
              <option value="TARGET_PRICE_HIT">TARGET_PRICE_HIT</option>
              <option value="PREDICT_SIGNAL_CHANGE">PREDICT_SIGNAL_CHANGE</option>
              <option value="PREDICT_UP_PROBABILITY_ABOVE">PREDICT_UP_PROBABILITY_ABOVE</option>
              <option value="PREDICT_DOWN_PROBABILITY_ABOVE">PREDICT_DOWN_PROBABILITY_ABOVE</option>
            </select>
          </label>
          <label>
            <span>{_lang_pair("阈值", "Threshold")}</span>
            <input id="alert-create-threshold" name="threshold" type="number" step="0.01" required />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" type="submit">{_lang_pair("创建", "Create")}</button>
          </div>
        </form>
        <p class="status-line" id="alert-create-status">{_lang_pair("请填写完整信息后提交。", "Fill in the full form before submitting.")}</p>
      </article>

      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">{_lang_pair("查询预警", "Lookup alerts")}</p>
          <h2>{_lang_pair("查看当前预警", "View current alerts")}</h2>
        </div>
        <div class="card-filter-form">
          <label>
            <span>{_lang_pair("Discord 用户 ID", "Discord user ID")}</span>
            <input id="alert-lookup-user-id" name="lookup_discord_user_id" type="text" />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" id="alert-query-button" type="button">{_lang_pair("查询", "Search")}</button>
          </div>
        </div>
        <p class="status-line" id="alert-lookup-status">{_lang_pair("请输入 Discord 用户 ID 后查询。", "Enter a Discord user ID and search.")}</p>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>{_lang_pair("卡牌", "Card")}</th>
                <th>{_lang_pair("类型", "Type")}</th>
                <th>{_lang_pair("阈值", "Threshold")}</th>
                <th>{_lang_pair("状态", "Status")}</th>
                <th>{_lang_pair("操作", "Actions")}</th>
              </tr>
            </thead>
            <tbody id="alert-results-body">
              <tr>
                <td colspan="5" class="empty-state-cell">{_lang_pair("暂无查询结果。", "No results yet.")}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <script>
      (() => {{
        const apiBase = {api_base!r};
        const createForm = document.getElementById("alert-create-form");
        const createStatus = document.getElementById("alert-create-status");
        const lookupInput = document.getElementById("alert-lookup-user-id");
        const lookupStatus = document.getElementById("alert-lookup-status");
        const queryButton = document.getElementById("alert-query-button");
        const resultsBody = document.getElementById("alert-results-body");

        const escapeHtml = (value) => {{
          const span = document.createElement("span");
          span.textContent = value ?? "";
          return span.innerHTML;
        }};

        const renderEmpty = (message) => {{
          resultsBody.innerHTML = `<tr><td colspan="5" class="empty-state-cell">${{escapeHtml(message)}}</td></tr>`;
        }};

        const formatThreshold = (item) => {{
          if (item.target_price !== null && item.target_price !== undefined) {{
            return item.target_price;
          }}
          if (item.threshold_percent !== null && item.threshold_percent !== undefined) {{
            return item.threshold_percent;
          }}
          return "-";
        }};

        const formatStatus = (item) => {{
          if (!item.is_active) {{
            return "已停用";
          }}
          return item.is_armed ? "已启用" : "等待重置";
        }};

        const loadAlerts = async (userId) => {{
          if (!userId) {{
            lookupStatus.textContent = "请输入 Discord 用户 ID。";
            return;
          }}
          lookupStatus.textContent = "查询中...";
          renderEmpty("正在加载...");
          try {{
            const res = await fetch(`${{apiBase}}/${{encodeURIComponent(userId)}}`);
            if (!res.ok) {{
              lookupStatus.textContent = "出错了。";
              renderEmpty("出错了。");
              return;
            }}
            const items = await res.json();
            if (!items.length) {{
              lookupStatus.textContent = "未找到预警。";
              renderEmpty("未找到预警。");
              return;
            }}
            lookupStatus.textContent = `共找到 ${{items.length}} 条预警。`;
            resultsBody.innerHTML = "";
            items.forEach((item) => {{
              const row = document.createElement("tr");
              row.innerHTML = `
                <td>${{escapeHtml(item.asset_name ?? "-")}}</td>
                <td>${{escapeHtml(item.alert_type ?? "-")}}</td>
                <td>${{escapeHtml(String(formatThreshold(item)))}}</td>
                <td>${{escapeHtml(formatStatus(item))}}</td>
                <td>
                  <button class="button button-secondary" type="button" data-action="delete">删除</button>
                  <button class="button button-secondary" type="button" data-action="disable">停用</button>
                </td>
              `;

              const deleteButton = row.querySelector('[data-action="delete"]');
              const disableButton = row.querySelector('[data-action="disable"]');

              deleteButton.addEventListener("click", async () => {{
                deleteButton.disabled = true;
                disableButton.disabled = true;
                try {{
                  const res = await fetch(`${{apiBase}}/${{encodeURIComponent(item.alert_id)}}`, {{
                    method: "DELETE",
                  }});
                  if (!res.ok) {{
                    deleteButton.disabled = false;
                    disableButton.disabled = false;
                    lookupStatus.textContent = "出错了。";
                    return;
                  }}
                  row.remove();
                  lookupStatus.textContent = "已删除。";
                  if (!resultsBody.children.length) {{
                    renderEmpty("暂无查询结果。");
                  }}
                }} catch (err) {{
                  deleteButton.disabled = false;
                  disableButton.disabled = false;
                  lookupStatus.textContent = "出错了。";
                }}
              }});

              disableButton.addEventListener("click", async () => {{
                deleteButton.disabled = true;
                disableButton.disabled = true;
                try {{
                  const res = await fetch(`${{apiBase}}/${{encodeURIComponent(item.alert_id)}}/disable`, {{
                    method: "POST",
                  }});
                  if (!res.ok) {{
                    deleteButton.disabled = false;
                    disableButton.disabled = false;
                    lookupStatus.textContent = "出错了。";
                    return;
                  }}
                  row.children[3].textContent = "已停用";
                  disableButton.textContent = "已停用";
                }} catch (err) {{
                  deleteButton.disabled = false;
                  disableButton.disabled = false;
                  lookupStatus.textContent = "出错了。";
                }}
              }});

              resultsBody.appendChild(row);
            }});
          }} catch (err) {{
            lookupStatus.textContent = "出错了。";
            renderEmpty("出错了。");
          }}
        }};

        queryButton.addEventListener("click", () => loadAlerts(lookupInput.value.trim()));
        lookupInput.addEventListener("keydown", (event) => {{
          if (event.key === "Enter") {{
            loadAlerts(lookupInput.value.trim());
          }}
        }});

        createForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const discordUserId = document.getElementById("alert-create-user-id").value.trim();
          const assetName = document.getElementById("alert-create-asset-name").value.trim();
          const alertType = document.getElementById("alert-create-type").value;
          const thresholdValue = document.getElementById("alert-create-threshold").value.trim();

          if (!discordUserId || !assetName || !alertType || !thresholdValue) {{
            createStatus.textContent = "出错了。";
            return;
          }}

          createStatus.textContent = "提交中...";
          try {{
            const res = await fetch(apiBase, {{
              method: "POST",
              headers: {{"Content-Type": "application/json"}},
              body: JSON.stringify({{
                discord_user_id: discordUserId,
                asset_name: assetName,
                alert_type: alertType,
                threshold: Number(thresholdValue),
              }}),
            }});
            createStatus.textContent = res.ok ? "已创建。" : "出错了。";
            if (res.ok && lookupInput.value.trim() === discordUserId) {{
              loadAlerts(discordUserId);
            }}
          }} catch (err) {{
            createStatus.textContent = "出错了。";
          }}
        }});
      }})();
    </script>
    """
    return _render_shell(
        title="预警管理",
        current_path="/alerts",
        body=body,
        page_key="alerts",
        username=_session_username(request),
    )


@router.get("/backstage/review", response_class=HTMLResponse)
def backstage_review_page(request: Request) -> HTMLResponse:
    username = _session_username(request)
    api_base = f"{settings.api_prefix}/admin/review"
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">Backstage Review</p>
        <h1>Human Review Queue</h1>
        <p class="lede">Resolve low-confidence ingestion matches with Accept, Override, or Dismiss.</p>
      </div>
      <div class="intro-note">
        <strong>Admin-only flow</strong>
        <p>The page stores the admin key in <code>sessionStorage</code> for the current tab and calls the admin review API directly.</p>
      </div>
    </section>

    <section class="review-page" id="review-page">
      <div class="review-key-prompt" id="review-key-prompt">
        <div class="review-key-card">
          <h2>Enter admin key</h2>
          <p>Your key stays in this tab only and is never written into the page markup.</p>
          <form class="review-key-form" id="review-key-form">
            <input
              id="review-admin-key"
              type="password"
              placeholder="Admin key"
              autocomplete="off"
            />
            <button class="button button-primary" type="submit">Unlock</button>
          </form>
          <p class="review-error" id="review-key-error"></p>
        </div>
      </div>

      <div class="review-queue-view" id="review-queue-view" hidden>
        <div class="review-queue-header">
          <div>
            <p class="eyebrow">Pending Queue</p>
            <h2 id="review-queue-heading">Pending reviews</h2>
          </div>
          <button class="button button-secondary" id="review-refresh" type="button">Refresh</button>
        </div>
        <div class="review-queue-list" id="review-queue-list"></div>
      </div>

      <div class="review-modal-backdrop" id="review-modal-backdrop" hidden>
        <div class="review-modal" id="review-modal" role="dialog" aria-modal="true" aria-labelledby="review-modal-title">
          <button class="review-modal-close" id="review-modal-close" type="button" aria-label="Close review modal">Close</button>
          <p class="review-modal-label">Raw listing title</p>
          <p class="review-modal-title" id="review-modal-title"></p>
          <div class="review-modal-meta" id="review-modal-meta"></div>
          <div class="review-modal-actions" id="review-modal-actions"></div>
          <div class="review-override-search" id="review-override-search" hidden>
            <input
              id="review-override-input"
              type="search"
              placeholder="Search assets (min 3 chars)..."
              autocomplete="off"
            />
            <ul class="review-search-results" id="review-search-results"></ul>
          </div>
          <p class="review-error" id="review-modal-error"></p>
        </div>
      </div>
    </section>

    <script>
      (() => {{
        const apiBase = {json.dumps(api_base)};
        const storageKey = "flashcard-planet-admin-key";
        let adminKey = window.sessionStorage.getItem(storageKey) || "";
        let currentItem = null;
        let searchTimer = null;

        const elements = {{
          keyPrompt: document.getElementById("review-key-prompt"),
          keyForm: document.getElementById("review-key-form"),
          keyInput: document.getElementById("review-admin-key"),
          keyError: document.getElementById("review-key-error"),
          queueView: document.getElementById("review-queue-view"),
          queueHeading: document.getElementById("review-queue-heading"),
          queueList: document.getElementById("review-queue-list"),
          refresh: document.getElementById("review-refresh"),
          modalBackdrop: document.getElementById("review-modal-backdrop"),
          modalClose: document.getElementById("review-modal-close"),
          modalTitle: document.getElementById("review-modal-title"),
          modalMeta: document.getElementById("review-modal-meta"),
          modalActions: document.getElementById("review-modal-actions"),
          modalError: document.getElementById("review-modal-error"),
          overrideSearch: document.getElementById("review-override-search"),
          overrideInput: document.getElementById("review-override-input"),
          searchResults: document.getElementById("review-search-results"),
        }};

        const escapeHtml = (value) => {{
          const span = document.createElement("span");
          span.textContent = value ?? "";
          return span.innerHTML;
        }};

        const authHeaders = () => ({{
          "X-Admin-Key": adminKey,
          "Content-Type": "application/json",
        }});

        const formatConfidence = (value) => {{
          if (value === null || value === undefined) {{
            return "N/A";
          }}
          const numeric = Number(value);
          if (!Number.isFinite(numeric)) {{
            return "N/A";
          }}
          return `${{Math.round(numeric * 100)}}%`;
        }};

        const showKeyPrompt = (message = "") => {{
          elements.keyPrompt.hidden = false;
          elements.queueView.hidden = true;
          elements.keyError.textContent = message;
        }};

        const showQueueView = () => {{
          elements.keyPrompt.hidden = true;
          elements.queueView.hidden = false;
          elements.keyError.textContent = "";
        }};

        const closeModal = () => {{
          currentItem = null;
          elements.modalBackdrop.hidden = true;
          elements.modalError.textContent = "";
          elements.overrideSearch.hidden = true;
          elements.overrideInput.value = "";
          elements.searchResults.innerHTML = "";
        }};

        const setActionDisabled = (disabled) => {{
          elements.modalActions.querySelectorAll("button").forEach((button) => {{
            button.disabled = disabled;
          }});
        }};

        const renderQueue = (items) => {{
          if (!items.length) {{
            elements.queueList.innerHTML = '<p class="review-empty">No pending reviews.</p>';
            return;
          }}

          elements.queueList.innerHTML = items.map((item) => {{
            return `
              <article class="review-queue-row" data-review-id="${{item.id}}">
                <div class="review-row-title">${{escapeHtml(item.raw_title)}}</div>
                <div class="review-row-meta">
                  <span class="review-row-chip">${{escapeHtml(item.best_guess_asset_name || "No AI guess")}}</span>
                  <span class="review-row-chip">${{formatConfidence(item.best_guess_confidence)}}</span>
                  <span class="review-row-chip">${{escapeHtml(item.reason || "No reason provided")}}</span>
                </div>
              </article>
            `;
          }}).join("");

          elements.queueList.querySelectorAll(".review-queue-row").forEach((row, index) => {{
            row.addEventListener("click", () => openReviewModal(items[index]));
          }});
        }};

        const loadQueue = async () => {{
          if (!adminKey) {{
            showKeyPrompt();
            return;
          }}

          const response = await fetch(apiBase, {{
            headers: authHeaders(),
          }});

          if (response.status === 401 || response.status === 403) {{
            adminKey = "";
            window.sessionStorage.removeItem(storageKey);
            showKeyPrompt("Session expired. Re-enter admin key.");
            return;
          }}

          if (!response.ok) {{
            elements.queueHeading.textContent = "Pending reviews";
            elements.queueList.innerHTML = '<p class="review-error">Unable to load review queue.</p>';
            return;
          }}

          const payload = await response.json();
          elements.queueHeading.textContent = `Pending reviews (${{payload.total_pending}})`;
          renderQueue(payload.items || []);
        }};

        const requestResolution = async (path, options = {{}}) => {{
          const response = await fetch(`${{apiBase}}/${{currentItem.id}}/${{path}}`, {{
            method: "POST",
            headers: authHeaders(),
            ...options,
          }});

          if (response.ok) {{
            closeModal();
            await loadQueue();
            return;
          }}

          let detail = "Request failed.";
          try {{
            const payload = await response.json();
            if (payload && payload.detail) {{
              detail = payload.detail;
            }}
          }} catch (error) {{
            detail = "Request failed.";
          }}
          elements.modalError.textContent = detail;
          setActionDisabled(false);
        }};

        const renderSearchResults = (results) => {{
          if (!results.length) {{
            elements.searchResults.innerHTML = '<li class="search-result-empty">No results.</li>';
            return;
          }}

          elements.searchResults.innerHTML = results.map((item) => {{
            const meta = [item.set_name, item.variant].filter(Boolean).join(" | ");
            return `
              <li class="search-result-item" data-asset-id="${{item.id}}">
                <strong>${{escapeHtml(item.name)}}</strong>
                <span>${{escapeHtml(meta)}}</span>
              </li>
            `;
          }}).join("");

          elements.searchResults.querySelectorAll(".search-result-item").forEach((row, index) => {{
            row.addEventListener("click", () => window.resolveOverride(results[index].id));
          }});
        }};

        const searchAssets = async (query) => {{
          const response = await fetch(
            `${{apiBase}}/assets/search?q=${{encodeURIComponent(query)}}`,
            {{ headers: authHeaders() }}
          );

          if (response.status === 401 || response.status === 403) {{
            adminKey = "";
            window.sessionStorage.removeItem(storageKey);
            closeModal();
            showKeyPrompt("Session expired. Re-enter admin key.");
            return;
          }}

          if (!response.ok) {{
            elements.searchResults.innerHTML = '<li class="search-result-empty">Search failed.</li>';
            return;
          }}

          const results = await response.json();
          renderSearchResults(results);
        }};

        const openReviewModal = (item) => {{
          currentItem = item;
          elements.modalTitle.textContent = item.raw_title || "";
          elements.modalError.textContent = "";
          elements.overrideSearch.hidden = true;
          elements.overrideInput.value = "";
          elements.searchResults.innerHTML = "";
          elements.modalMeta.innerHTML = `
            <dl class="review-meta-dl">
              <dt>AI guess</dt>
              <dd>${{escapeHtml(item.best_guess_asset_name || "No AI guess")}}</dd>
              <dt>Confidence</dt>
              <dd>${{formatConfidence(item.best_guess_confidence)}}</dd>
              <dt>Reason</dt>
              <dd>${{escapeHtml(item.reason || "No reason provided")}}</dd>
            </dl>
          `;

          elements.modalActions.innerHTML = `
            <button class="button button-success" id="review-accept-btn" type="button">Accept</button>
            <button class="button button-primary" id="review-override-btn" type="button">Override</button>
            <button class="button button-danger" id="review-dismiss-btn" type="button">Dismiss</button>
          `;

          const acceptButton = document.getElementById("review-accept-btn");
          const overrideButton = document.getElementById("review-override-btn");
          const dismissButton = document.getElementById("review-dismiss-btn");

          acceptButton.disabled = !item.best_guess_asset_id;
          acceptButton.addEventListener("click", async () => {{
            setActionDisabled(true);
            await resolveAccept();
          }});
          overrideButton.addEventListener("click", () => {{
            elements.overrideSearch.hidden = false;
            elements.overrideInput.focus();
          }});
          dismissButton.addEventListener("click", async () => {{
            setActionDisabled(true);
            await window.resolveDismiss();
          }});

          elements.modalBackdrop.hidden = false;
        }};

        const resolveAccept = async () => {{
          await requestResolution("accept");
        }};

        window.resolveOverride = async function resolveOverride(assetId) {{
          setActionDisabled(true);
          await requestResolution("override", {{
            body: JSON.stringify({{ asset_id: assetId }}),
          }});
        }};

        window.resolveDismiss = async function resolveDismiss() {{
          await requestResolution("dismiss");
        }};

        elements.keyForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const nextKey = elements.keyInput.value.trim();
          if (!nextKey) {{
            elements.keyError.textContent = "Enter an admin key.";
            return;
          }}

          adminKey = nextKey;
          window.sessionStorage.setItem(storageKey, adminKey);
          showQueueView();
          await loadQueue();
        }});

        elements.refresh.addEventListener("click", loadQueue);
        elements.modalClose.addEventListener("click", closeModal);
        elements.modalBackdrop.addEventListener("click", (event) => {{
          if (event.target === elements.modalBackdrop) {{
            closeModal();
          }}
        }});
        elements.overrideInput.addEventListener("input", (event) => {{
          const query = event.target.value.trim();
          window.clearTimeout(searchTimer);
          if (query.length < 3) {{
            elements.searchResults.innerHTML = "";
            return;
          }}
          searchTimer = window.setTimeout(() => {{
            searchAssets(query);
          }}, 250);
        }});

        if (adminKey) {{
          showQueueView();
          loadQueue();
        }} else {{
          showKeyPrompt();
        }}
      }})();
    </script>
    """
    return _render_shell(
        title="Human Review Queue",
        current_path="/backstage/review",
        body=body,
        page_key="backstage_review",
        username=username,
    )


@router.get("/dashboard/snapshot")
def dashboard_snapshot(db: Session = Depends(get_database)) -> dict[str, object]:
    return build_dashboard_snapshot(db)


@router.get("/upgrade", response_class=HTMLResponse)
def upgrade_page(request: Request) -> HTMLResponse:
    username = _session_username(request)
    body = """
<div class="page-hero">
  <h1 class="page-hero__title">
    Flashcard Planet <span style="background:#2563eb;color:white;padding:2px 10px;border-radius:4px;font-size:0.75em;vertical-align:middle;">Pro</span>
  </h1>
  <p class="page-hero__subtitle">
    <span data-zh="更深入的数据。更精准的信号。完整的历史记录。">Deeper data. Sharper signals. Full history.</span>
  </p>
</div>

<section class="shell" style="max-width:760px;margin:0 auto;padding-bottom:48px;">

  <!-- Comparison table -->
  <div style="overflow-x:auto;margin-bottom:32px;">
    <table style="width:100%;border-collapse:collapse;font-size:0.95em;">
      <thead>
        <tr>
          <th style="text-align:left;padding:10px 12px;border-bottom:2px solid #e5e7eb;" data-zh="功能">Feature</th>
          <th style="text-align:center;padding:10px 12px;border-bottom:2px solid #e5e7eb;" data-zh="免费">Free</th>
          <th style="text-align:center;padding:10px 12px;border-bottom:2px solid #e5e7eb;color:#2563eb;" data-zh="Pro">Pro</th>
        </tr>
      </thead>
      <tbody>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="价格历史">Price history</td>
          <td style="text-align:center;padding:10px 12px;" data-zh="7 天">7 days</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="180 天">180 days</td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="信号动态">Signals feed</td>
          <td style="text-align:center;padding:10px 12px;" data-zh="前 5 条，无置信度分数">Top 5, no scores</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="完整动态 + 置信度分数">Full feed + confidence scores</td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="AI 信号解读">AI signal explanation</td>
          <td style="text-align:center;padding:10px 12px;">&#10005;</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;">&#10003;</td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="来源对比">Source breakdown</td>
          <td style="text-align:center;padding:10px 12px;">&#10005;</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="eBay vs TCG 拆分">eBay vs TCG split</td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="价格提醒">Alerts</td>
          <td style="text-align:center;padding:10px 12px;" data-zh="最多 5 条">Up to 5</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="无限 + 百分比触发">Unlimited + % triggers</td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="观察列表">Watchlist</td>
          <td style="text-align:center;padding:10px 12px;" data-zh="最多 10 张卡牌">Up to 10 cards</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="无限">Unlimited</td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:10px 12px;" data-zh="涨跌榜详情">Top Movers detail</td>
          <td style="text-align:center;padding:10px 12px;" data-zh="基本列表">Basic list</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="流动性 + 成交量趋势">Liquidity + volume trend</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;" data-zh="Pro 洞察">Pro Insights</td>
          <td style="text-align:center;padding:10px 12px;">&#10005;</td>
          <td style="text-align:center;padding:10px 12px;font-weight:600;color:#2563eb;" data-zh="数据质量面板">Data quality panel</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- Request form -->
  <div style="border:1px solid #e5e7eb;border-radius:12px;padding:32px;margin-bottom:24px;">
    <h2 style="margin:0 0 8px 0;" data-zh="申请 Pro 访问权限">Request Pro Access</h2>
    <p style="color:#6b7280;margin:0 0 20px 0;" data-zh="目前处于封闭测试阶段，免费开放。提交申请后我们会通过 Discord 在 24 小时内确认。">
      Early access is free while we're in beta. We'll confirm by Discord within 24&nbsp;hours.
    </p>
    <form method="POST" action="/upgrade/request">
      <textarea
        name="note"
        placeholder="Anything you'd like to share? (optional)"
        rows="3"
        maxlength="500"
        style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #d1d5db;border-radius:6px;margin-bottom:16px;font-family:inherit;font-size:0.9em;"
      ></textarea>
      <button type="submit"
        style="background:#2563eb;color:white;border:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:1em;cursor:pointer;"
        data-zh="申请 Pro 访问"
      >Request Pro Access</button>
    </form>
  </div>

  <!-- FAQ -->
  <div>
    <h2 style="margin-bottom:12px;" data-zh="常见问题">Common questions</h2>
    <details style="margin-bottom:12px;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;">
      <summary style="cursor:pointer;font-weight:600;" data-zh="现在的访问权限是如何运作的？">How does access work right now?</summary>
      <p style="margin:8px 0 0 0;color:#6b7280;" data-zh="我们处于人工审核测试阶段。提交申请后我们会直接升级您的账户，暂不需要付款。">
        We're in a manual-approval beta. Submit a request and we'll upgrade your account directly — no payment needed yet.
      </p>
    </details>
    <details style="margin-bottom:12px;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;">
      <summary style="cursor:pointer;font-weight:600;" data-zh="Pro 会一直免费吗？">Will Pro always be free?</summary>
      <p style="margin:8px 0 0 0;color:#6b7280;" data-zh="不会。平台功能完善后我们计划推出付费方案。早期测试用户将获得宽限期。">
        No. We plan to introduce a paid tier once the platform is more complete. Early beta users will get a grace period.
      </p>
    </details>
    <details style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;">
      <summary style="cursor:pointer;font-weight:600;" data-zh="降级后我的数据会怎样？">What happens to my data if I downgrade?</summary>
      <p style="margin:8px 0 0 0;color:#6b7280;" data-zh="您的卡牌、提醒和观察列表永远不会被删除。您只是暂时失去对扩展视图的访问权限。">
        Your cards, alerts, and watchlist are never deleted. You'd simply lose access to extended views until you're on Pro again.
      </p>
    </details>
  </div>
</section>
"""
    return _render_shell(
        title="Upgrade to Pro",
        current_path="/upgrade",
        body=body,
        page_key="upgrade",
        username=username,
    )


@router.post("/upgrade/request")
def post_upgrade_request(
    request: Request,
    note: str = Form(default=""),
    db: Session = Depends(get_database),
):
    import uuid as _uuid

    session = request.scope.get("session")
    user_id_str = session.get("user_id") if isinstance(session, dict) else None
    if not user_id_str:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/upgrade", status_code=303)

    try:
        user_id = _uuid.UUID(user_id_str)
    except ValueError:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/upgrade", status_code=303)

    result = submit_upgrade_request(db, user_id=user_id, note=note)
    db.commit()
    from fastapi.responses import RedirectResponse
    if not result.ok:
        return RedirectResponse(url=f"/upgrade/status?msg={escape(result.error or '')}", status_code=303)
    return RedirectResponse(url="/upgrade/status", status_code=303)


@router.get("/upgrade/status", response_class=HTMLResponse)
def upgrade_status_page(request: Request, msg: str | None = None) -> HTMLResponse:
    import uuid as _uuid

    username = _session_username(request)
    session = request.scope.get("session")
    user_id_str = session.get("user_id") if isinstance(session, dict) else None

    if not user_id_str:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/upgrade", status_code=303)

    with SessionLocal() as db:
        try:
            user_id = _uuid.UUID(user_id_str)
        except ValueError:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/upgrade", status_code=303)
        status = get_upgrade_status(db, user_id=user_id)

    tier = status["tier"]
    req_status = status.get("request_status")

    if tier == "pro":
        body = """
        <div style="max-width:540px;margin:48px auto;text-align:center;">
          <p style="font-size:2em;margin:0 0 12px 0;">&#10003;</p>
          <h2 data-zh="您已升级至 Pro">You're on Pro</h2>
          <p style="color:#6b7280;" data-zh="所有 Pro 功能已在您的账户上激活。">All Pro features are active on your account.</p>
          <a href="/signals" style="display:inline-block;margin-top:16px;background:#2563eb;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;" data-zh="查看信号">View Signals</a>
        </div>
        """
    elif req_status == "pending":
        body = """
        <div style="max-width:540px;margin:48px auto;text-align:center;">
          <h2 data-zh="申请已收到">Request received</h2>
          <p style="color:#6b7280;" data-zh="我们将审核您的申请并在 24 小时内通过 Discord 确认。">We'll review your request and confirm by Discord within 24&nbsp;hours.</p>
          <form method="POST" action="/upgrade/cancel" style="margin-top:20px;">
            <button type="submit"
              style="background:transparent;border:1px solid #d1d5db;padding:8px 20px;border-radius:6px;cursor:pointer;color:#6b7280;"
              data-zh="撤销申请"
            >Cancel request</button>
          </form>
        </div>
        """
    elif req_status == "rejected":
        body = f"""
        <div style="max-width:540px;margin:48px auto;text-align:center;">
          <h2 data-zh="申请未获批准">Request not approved</h2>
          <p style="color:#6b7280;" data-zh="我们暂时无法批准此申请。如有疑问请通过电子邮件联系我们。">
            We couldn't approve this request right now.
            Reach out at <a href="mailto:hello@flashcardplanet.com">hello@flashcardplanet.com</a> if you think this is a mistake.
          </p>
        </div>
        """
    else:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/upgrade", status_code=303)

    if msg:
        body = f'<p style="text-align:center;color:#dc2626;">{escape(msg)}</p>' + body

    return _render_shell(
        title="Upgrade Status",
        current_path="/upgrade",
        body=body,
        page_key="upgrade-status",
        username=username,
    )


@router.post("/upgrade/cancel")
def cancel_upgrade(request: Request, db: Session = Depends(get_database)):
    import uuid as _uuid
    from fastapi.responses import RedirectResponse

    session = request.scope.get("session")
    user_id_str = session.get("user_id") if isinstance(session, dict) else None
    if not user_id_str:
        return RedirectResponse(url="/upgrade", status_code=303)

    try:
        user_id = _uuid.UUID(user_id_str)
    except ValueError:
        return RedirectResponse(url="/upgrade", status_code=303)

    cancel_upgrade_request(db, user_id=user_id)
    db.commit()
    return RedirectResponse(url="/upgrade", status_code=303)


@router.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request) -> HTMLResponse:
    import uuid as _uuid

    username = _session_username(request)
    session = request.scope.get("session")
    user_id_str = session.get("user_id") if isinstance(session, dict) else None

    # Resolve access tier
    access_tier = "free"
    if user_id_str:
        with SessionLocal() as db:
            try:
                user = db.get(User, _uuid.UUID(user_id_str))
                access_tier = user.access_tier if user else "free"
            except Exception:
                pass

    if not can(access_tier, Feature.PRO_INSIGHTS):
        body = f"""
<div class="page-hero">
  <h1 class="page-hero__title" data-zh="Pro 洞察">Pro Insights</h1>
</div>
<div class="progate" style="position:relative;overflow:hidden;border-radius:12px;max-width:760px;margin:0 auto;">
  <div style="filter:blur(4px);pointer-events:none;padding:32px;">
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;">
      {"".join(f'<div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;"><p style="margin:0;color:#9ca3af;font-size:0.85em;">Metric</p><p style="margin:4px 0 0 0;font-size:1.5em;font-weight:700;">———</p></div>' for _ in range(4))}
    </div>
  </div>
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(255,255,255,0.75);">
    <p style="margin:0 0 12px 0;font-weight:600;" data-zh="Pro 功能">Pro feature</p>
    <a href="/upgrade" style="background:#2563eb;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;" data-zh="解锁 Pro 洞察">Unlock Pro Insights</a>
  </div>
</div>
"""
        return _render_shell(
            title="Pro Insights",
            current_path="/insights",
            body=body,
            page_key="insights",
            username=username,
        )

    with SessionLocal() as db:
        result = build_pro_insights(db)

    metric_cards = "".join(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;">
          <p style="margin:0 0 4px 0;color:#6b7280;font-size:0.85em;">{escape(m.label)}</p>
          <p style="margin:0 0 4px 0;font-size:1.5em;font-weight:700;">{escape(m.value)}</p>
          <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.8em;{'background:#16a34a;color:white' if m.status == 'green' else 'background:#ca8a04;color:white' if m.status == 'yellow' else 'background:#dc2626;color:white'};">{m.status.upper()}</span>
          <p style="margin:8px 0 0 0;font-size:0.85em;color:#6b7280;">{escape(m.description)}</p>
        </div>
        """
        for m in result.metrics
    )

    body = f"""
<div class="page-hero">
  <h1 class="page-hero__title" data-zh="Pro 洞察">Pro Insights</h1>
  <p class="page-hero__subtitle" style="color:#6b7280;">Generated {result.generated_at.strftime("%Y-%m-%d %H:%M UTC")}</p>
</div>
<section class="shell" style="max-width:760px;margin:0 auto;padding-bottom:48px;">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:32px;">
    {metric_cards}
  </div>
  <div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;">
    <h2 style="margin:0 0 12px 0;font-size:1em;" data-zh="过去 7 天每日观测量">Daily Observations — Last 7 Days</h2>
    <p style="font-family:monospace;font-size:0.9em;color:#6b7280;">{" | ".join(str(v) for v in result.daily_observations)}</p>
    <h2 style="margin:16px 0 12px 0;font-size:1em;" data-zh="过去 7 天每日信号数">Daily Signals — Last 7 Days</h2>
    <p style="font-family:monospace;font-size:0.9em;color:#6b7280;">{" | ".join(str(v) for v in result.daily_signals)}</p>
  </div>
</section>
"""
    return _render_shell(
        title="Pro Insights",
        current_path="/insights",
        body=body,
        page_key="insights",
        username=username,
    )
