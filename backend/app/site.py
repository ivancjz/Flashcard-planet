from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.core.config import get_settings
from backend.app.core.price_sources import (
    get_active_price_source_filter,
    get_configured_price_providers,
)
from backend.app.db.session import SessionLocal
from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.models.watchlist import Watchlist
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.price_service import get_top_movers, get_top_value_assets
from backend.app.services.smart_pool_service import get_smart_pool_candidates

router = APIRouter(include_in_schema=False)
settings = get_settings()
CARDS_PER_PAGE = 50


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


def _build_ranked_price_subquery(source_filter):
    return (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.source,
            PriceHistory.captured_at,
            func.row_number()
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.desc())
            .label("price_rank"),
        )
        .where(source_filter)
        .subquery()
    )


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
def landing_page() -> HTMLResponse:
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
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> HTMLResponse:
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
        <p class="status-line" id="lookup-status">{_lang_pair("加载演示数据中...", "Loading demo data...")}</p>
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
    )


@router.get("/cards", response_class=HTMLResponse)
def cards_page(
    set_id: str | None = Query(None, alias="set"),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    with SessionLocal() as db:
        source_filter = get_active_price_source_filter(db)
        ranked = _build_ranked_price_subquery(source_filter)
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
        row_markup = "".join(
            """
            <tr>
              <td><a class="table-link" href="/cards/{external_id}">{name}</a></td>
              <td>{set_name}</td>
              <td>{card_number}</td>
              <td>{variant}</td>
              <td>{latest_price}</td>
            </tr>
            """.format(
                external_id=escape(row.external_id or ""),
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
    )


@router.get("/cards/{external_id}", response_class=HTMLResponse)
def card_detail_page(external_id: str) -> HTMLResponse:
    with SessionLocal() as db:
        source_filter = get_active_price_source_filter(db)
        ranked = _build_ranked_price_subquery(source_filter)
        latest = select(ranked).where(ranked.c.price_rank == 1).subquery("latest_card_price")

        row = db.execute(
            select(
                Asset,
                latest.c.price.label("latest_price"),
                latest.c.currency.label("currency"),
                latest.c.captured_at.label("captured_at"),
            )
            .outerjoin(latest, latest.c.asset_id == Asset.id)
            .where(
                Asset.category == "Pokemon",
                Asset.external_id == external_id,
            )
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="卡牌不存在。")

        asset = row.Asset
        history_rows = db.execute(
            select(
                PriceHistory.price,
                PriceHistory.currency,
                PriceHistory.source,
                PriceHistory.captured_at,
            )
            .where(
                PriceHistory.asset_id == asset.id,
                source_filter,
            )
            .order_by(PriceHistory.captured_at.desc())
            .limit(10)
        ).all()

    price_history = list(reversed(history_rows))
    image_small = _get_metadata_image_small(asset)
    tcgplayer_url = _get_metadata_tcgplayer_url(asset)
    latest_price = Decimal(row.latest_price) if row.latest_price is not None else None
    latest_captured_at = row.captured_at.strftime("%Y-%m-%d %H:%M UTC") if row.captured_at else "N/A"
    price_labels = [history_row.captured_at.strftime("%Y-%m-%d") for history_row in price_history]
    price_values = [float(history_row.price) for history_row in price_history]
    chart_script_tag = ""
    chart_markup = f"<p>{_lang_pair('暂无足够数据生成走势图。', 'Not enough data to render a chart yet.')}</p>"
    chart_inline_script = ""
    if len(price_history) >= 2:
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
            captured_at=escape(history_row.captured_at.strftime("%Y-%m-%d %H:%M UTC")),
            price=escape(_format_currency(Decimal(history_row.price), history_row.currency)),
            source=escape(history_row.source),
        )
        for history_row in price_history
    )
    if not history_markup:
        history_markup = """
        <tr>
          <td colspan="3" class="empty-state-cell">{empty_text}</td>
        </tr>
        """.format(empty_text=_lang_pair("暂无价格历史数据。", "No price history available."))

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
        <strong>{escape(_format_currency(latest_price, row.currency or "USD"))}</strong>
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
          <div><dt>{_lang_pair("最新价格", "Latest price")}</dt><dd>{escape(_format_currency(latest_price, row.currency or "USD"))}</dd></div>
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
        <h2>{_lang_pair("最近 10 条价格记录", "Latest 10 price records")}</h2>
      </div>
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
    )


@router.get("/method", response_class=HTMLResponse)
def method_page() -> HTMLResponse:
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
    )


@router.get("/watchlists", response_class=HTMLResponse)
def watchlists_page() -> HTMLResponse:
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
    )


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page() -> HTMLResponse:
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
    )


@router.get("/dashboard/snapshot")
def dashboard_snapshot(db: Session = Depends(get_database)) -> dict[str, object]:
    return build_dashboard_snapshot(db)
