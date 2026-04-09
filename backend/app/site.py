from __future__ import annotations

import json
from datetime import datetime
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
        ("/", "概览"),
        ("/dashboard", "实时仪表板"),
        ("/cards", "卡牌浏览"),
        ("/watchlists", "关注列表"),
        ("/alerts", "预警管理"),
        ("/method", "方法论 / 路线图"),
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
            <small>收藏品数据与信号平台</small>
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
        <p>Flashcard Planet 目前处于诊断优先阶段：数据接入、信号输出、运营闭环。</p>
        <p>暂无交易市场、挂单、支付或交易界面。</p>
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
        <p class="eyebrow">公测版</p>
        <h1>追踪收藏品价格，捕捉市场信号，掌握第一手数据。</h1>
        <p class="lede">
          Flashcard Planet 目前是一款轻量级的数据与信号产品。它将持续积累的价格历史转化为查询、涨跌观察、
          趋势判断、关注列表、预警与诊断工作流，同时明确当前尚未进入交易市场层。
        </p>
        <div class="hero-actions">
          <a class="button button-primary" href="/dashboard">打开实时仪表板</a>
          <a class="button button-secondary" href="/method">查看方法论</a>
        </div>
        <div class="hero-chips">
          <span>数据层</span>
          <span>信号层</span>
          <span>关注列表与预警</span>
          <span>数据源诊断</span>
        </div>
      </div>
      <div class="hero-panel">
        <div class="stat-stack">
          <article class="stat-card">
            <span class="stat-label">当前阶段</span>
            <strong>诊断优先</strong>
            <p>实时价格历史、最高价值视图、涨跌榜，以及公开证明数据源与池层真实可用的展示。</p>
          </article>
          <article class="stat-card">
            <span class="stat-label">信号循环</span>
            <strong>查询到预警</strong>
            <p>搜索价格、查看短期历史、评估方向性信号，并将关注列表接入 Discord 预警。</p>
          </article>
          <article class="stat-card">
            <span class="stat-label">尚未实现</span>
            <strong>暂无交易市场</strong>
            <p>在数据与信号层足够成熟之前，不提供结账、挂单、卖家工具或交易流程。</p>
          </article>
        </div>
      </div>
    </section>

    <section class="section-grid">
      <article class="feature-card">
        <p class="card-kicker">数据层</p>
        <h2>数据源支持的价格历史</h2>
        <p>重复采集、追踪池、单卡历史深度与低覆盖检测都保持公开可见。</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">信号层</p>
        <h2>最高价值、涨跌幅与方向性分析</h2>
        <p>MVP 围绕当前可衡量的数据构建：价格查询、短周期涨跌与趋势判断线索。</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">运营层</p>
        <h2>关注列表、预警与诊断</h2>
        <p>用户已经可以追踪资产与预警，运营者也能公开比较数据源、池与信号质量。</p>
      </article>
    </section>

    <section class="wide-panel">
      <div>
        <p class="eyebrow">站点地图</p>
        <h2>三个页面，刻意保持轻量</h2>
      </div>
      <div class="sitemap-list">
        <a class="sitemap-item" href="/">
          <strong>首页</strong>
          <span>产品定位、当前阶段，以及 Flashcard Planet 刻意暂不提供的内容。</span>
        </a>
        <a class="sitemap-item" href="/dashboard">
          <strong>实时仪表板</strong>
          <span>价格查询、最高价值、涨跌榜、数据源快照，以及 High-Activity v2 诊断。</span>
        </a>
        <a class="sitemap-item" href="/method">
          <strong>方法论 / 路线图</strong>
          <span>数据采集如何转化为信号，诊断如何影响决策，以及接下来的方向。</span>
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
    body = """
    <section class="page-intro">
      <div>
        <p class="eyebrow">实时仪表板 / 演示</p>
        <h1>公开展示当前数据与信号层的运行状态。</h1>
        <p class="lede">
          这个页面刻意保持精简：价格查询、当前数据源健康度、最高价值、涨跌榜，以及正在指导下一轮评估的
          High-Activity v2 诊断。
        </p>
      </div>
      <div class="intro-note">
        <strong>设计上刻意保持轻量</strong>
        <p>这里的所有内容都服务于当前产品阶段。没有鉴权墙、没有支付，也没有交易市场脚手架。</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">价格查询</p>
          <h2>搜索已追踪卡牌，查看最新价格</h2>
        </div>
        <form class="lookup-form" id="price-lookup-form">
          <label class="sr-only" for="price-query">卡牌名称</label>
          <input id="price-query" name="query" type="search" placeholder="试试 Umbreon、Pikachu 或 Charizard" />
          <button class="button button-primary" type="submit">查询</button>
        </form>
        <div class="sample-actions" id="sample-actions"></div>
        <p class="status-line" id="lookup-status">加载演示数据中...</p>
        <div class="lookup-results" id="lookup-results"></div>
        <div class="lookup-history" id="lookup-history"></div>
      </article>

      <article class="module" id="provider-snapshot">
        <div class="module-head">
          <p class="card-kicker">当前数据源快照</p>
          <h2>加载实时状态...</h2>
        </div>
        <div class="metric-stack skeleton-stack">
          <span></span><span></span><span></span>
        </div>
      </article>

      <article class="module" id="signal-ops">
        <div class="module-head">
          <p class="card-kicker">关注列表 / 预警 / 诊断</p>
          <h2>信号操作</h2>
        </div>
        <div class="metric-stack skeleton-stack">
          <span></span><span></span><span></span>
        </div>
      </article>

      <article class="module" id="top-value">
        <div class="module-head">
          <p class="card-kicker">最高价值</p>
          <h2>当前最高价格卡牌</h2>
        </div>
        <div class="list-shell skeleton-stack"><span></span><span></span><span></span></div>
      </article>

      <article class="module" id="top-movers">
        <div class="module-head">
          <p class="card-kicker">涨跌榜</p>
          <h2>近期最大价格变动</h2>
        </div>
        <div class="list-shell skeleton-stack"><span></span><span></span><span></span></div>
      </article>

      <article class="module module-wide" id="high-activity-module">
        <div class="module-head">
          <p class="card-kicker">高活跃度 v2 对比基准</p>
          <h2>加载诊断对比中...</h2>
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
    filters_summary_parts: list[str] = []
    if selected_set_name:
        filters_summary_parts.append(f"系列 {escape(selected_set_name)}")
    if q:
        filters_summary_parts.append(f"搜索 “{escape(q)}”")
    filters_summary = "，筛选条件：" + "，".join(filters_summary_parts) if filters_summary_parts else ""

    option_markup = ['<option value="">全部系列</option>']
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
              <td colspan="5" class="empty-state-cell">未找到卡牌。</td>
            </tr>
        """

    pager_links: list[str] = []
    if current_page > 1:
        prev_query = _build_cards_query_params(set_id=set_id, q=q, page=current_page - 1)
        pager_links.append(f'<a class="button button-secondary" href="/cards?{escape(prev_query)}">上一页</a>')
    if current_page < total_pages:
        next_query = _build_cards_query_params(set_id=set_id, q=q, page=current_page + 1)
        pager_links.append(f'<a class="button button-secondary" href="/cards?{escape(next_query)}">下一页</a>')
    pager_markup = "".join(pager_links)
    reset_href = "/cards"

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">卡牌浏览</p>
        <h1>浏览所有已追踪的宝可梦卡牌。</h1>
        <p class="lede">
          这个页面紧贴数据层：支持系列筛选、名称搜索、直达卡牌详情，以及查看每张已追踪卡牌当前数据源下的最新价格。
        </p>
      </div>
      <div class="intro-note">
        <strong>共 {total_cards} 张已追踪卡牌</strong>
        <p>当前第 {current_page} / {total_pages} 页{filters_summary}。</p>
      </div>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">筛选条件</p>
        <h2>按名称搜索或按系列筛选</h2>
      </div>
      <form class="card-filter-form" method="get" action="/cards">
        <label>
          <span>按系列筛选</span>
          <select name="set">
            {"".join(option_markup)}
          </select>
        </label>
        <label>
          <span>按名称搜索</span>
          <input type="search" name="q" value="{escape(q or '')}" placeholder="例如 Charizard" />
        </label>
        <input type="hidden" name="page" value="1" />
        <div class="card-filter-actions">
          <button class="button button-primary" type="submit">搜索</button>
          <a class="button button-secondary" href="{reset_href}">重置</a>
        </div>
      </form>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">卡牌浏览</p>
        <h2>每页 50 张卡牌</h2>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>系列</th>
              <th>编号</th>
              <th>版本</th>
              <th>最新价格</th>
            </tr>
          </thead>
          <tbody>
            {row_markup}
          </tbody>
        </table>
      </div>
      <div class="pagination-bar">
        <p class="status-line">第 {current_page} / {total_pages} 页</p>
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
    chart_markup = "<p>暂无足够数据生成走势图。</p>"
    chart_inline_script = ""
    if len(price_history) >= 2:
        chart_script_tag = (
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>'
        )
        chart_markup = (
            "<canvas id='price-chart' style='max-height:260px;margin-bottom:1.5rem;'></canvas>"
        )
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
                  borderColor: "#6366f1",
                  fill: false,
                  tension: 0.3,
                }}],
              }},
              options: {{
                responsive: true,
                maintainAspectRatio: false,
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
          <td colspan="3" class="empty-state-cell">暂无价格历史数据。</td>
        </tr>
        """

    image_markup = (
        f'<div class="card-image-panel"><img src="{escape(image_small)}" alt="{escape(asset.name)}" /></div>'
        if image_small
        else '<div class="card-image-panel card-image-empty"><p class="status-line">暂无卡牌图片。</p></div>'
    )
    tcgplayer_markup = (
        f'<a class="button button-secondary" href="{escape(tcgplayer_url)}" target="_blank" rel="noreferrer">在 TCGPlayer 上查看</a>'
        if tcgplayer_url
        else ""
    )

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">卡牌详情</p>
        <h1>{escape(asset.name)}</h1>
        <p class="lede">
          {escape(asset.set_name or "未知系列")} #{escape(asset.card_number or "N/A")} 已收录于当前追踪卡牌目录，
          下方展示该卡牌当前数据源下的最新价格记录与近期价格历史。
        </p>
      </div>
      <div class="intro-note">
        <strong>{escape(_format_currency(latest_price, row.currency or "USD"))}</strong>
        <p>最新价格采集时间：{escape(latest_captured_at)}。</p>
      </div>
    </section>

    <section class="card-detail-grid">
      {image_markup}
      <article class="module">
        <div class="module-head">
          <p class="card-kicker">卡牌信息</p>
          <h2>卡牌详情</h2>
        </div>
        <dl class="detail-list">
          <div><dt>名称</dt><dd>{escape(asset.name)}</dd></div>
          <div><dt>系列</dt><dd>{escape(asset.set_name or "未知系列")}</dd></div>
          <div><dt>编号</dt><dd>{escape(asset.card_number or "N/A")}</dd></div>
          <div><dt>年份</dt><dd>{escape(str(asset.year) if asset.year is not None else "N/A")}</dd></div>
          <div><dt>版本</dt><dd>{escape(asset.variant or "标准版")}</dd></div>
          <div><dt>卡牌ID</dt><dd>{escape(asset.external_id or "N/A")}</dd></div>
          <div><dt>最新价格</dt><dd>{escape(_format_currency(latest_price, row.currency or "USD"))}</dd></div>
        </dl>
        <div class="detail-actions">
          <a class="button button-primary" href="/cards">返回卡牌浏览</a>
          {tcgplayer_markup}
        </div>
      </article>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">价格历史</p>
        <h2>最近 10 条价格记录</h2>
      </div>
      {chart_markup}
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>价格</th>
              <th>数据源</th>
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
    body = """
    <section class="page-intro">
      <div>
        <p class="eyebrow">方法论 / 路线图</p>
        <h1>先建数据层，再做信号层，其余一切推后。</h1>
        <p class="lede">
          Flashcard Planet 有意按顺序推进：先做数据源支持的数据采集、池诊断、可解释的信号输出与关注列表工作流。
          在数据层值得信任之前，交易市场层暂不介入。
        </p>
      </div>
    </section>

    <section class="timeline-grid">
      <article class="timeline-card">
        <p class="card-kicker">当前</p>
        <h2>数据层</h2>
        <ul class="clean-list">
          <li>数据源支持的价格采集</li>
          <li>追踪池对比分析</li>
          <li>历史深度与低覆盖率诊断</li>
          <li>通过轻量仪表板进行公开验证</li>
        </ul>
      </article>
      <article class="timeline-card">
        <p class="card-kicker">当前</p>
        <h2>信号层</h2>
        <ul class="clean-list">
          <li>价格查询与近期历史</li>
          <li>最高价值与涨跌榜</li>
          <li>方向性预测评分</li>
          <li>关注列表与预警规则</li>
        </ul>
      </article>
      <article class="timeline-card">
        <p class="card-kicker">下一步</p>
        <h2>运营路线图</h2>
        <ul class="clean-list">
          <li>继续测试 High-Activity v2 与基准池的表现差异</li>
          <li>在积累更多观察后决定是否需要引入第二个数据源</li>
          <li>仅在诊断结果稳定后再扩展公开网站</li>
          <li>在任何商业化流程之前先完善预警体验</li>
        </ul>
      </article>
    </section>

    <section class="method-grid">
      <article class="feature-card">
        <p class="card-kicker">第 1 步</p>
        <h2>采集并标准化</h2>
        <p>持续从数据源抓取数据，形成单卡级别的价格历史，同时明确展示当前启用的是哪个数据源。</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">第 2 步</p>
        <h2>诊断数据池</h2>
        <p>通过追踪池、High-Activity v2 与低覆盖标记，判断弱信号究竟来自样本选择还是覆盖不足。</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">第 3 步</p>
        <h2>呈现信号</h2>
        <p>价格查询、涨跌榜、最高价值与轻量预测文案，把原始数据转化为用户可执行的信息。</p>
      </article>
      <article class="feature-card">
        <p class="card-kicker">第 4 步</p>
        <h2>闭环运营流程</h2>
        <p>关注列表与预警紧贴当前产品阶段，同时由诊断结果指导下一步的数据源决策。</p>
      </article>
    </section>

    <section class="wide-panel">
      <div>
        <p class="eyebrow">刻意排除的功能</p>
        <h2>当前 MVP 尚未包含的内容</h2>
      </div>
      <div class="sitemap-list">
        <div class="sitemap-item static">
          <strong>无交易市场</strong>
          <span>不提供挂单、结账、买家流程、卖家主页或支付能力。</span>
        </div>
        <div class="sitemap-item static">
          <strong>无臃肿平台框架</strong>
          <span>不做以鉴权为先的复杂产品迷宫，不做引导漏斗，也不堆砌臃肿仪表板。</span>
        </div>
        <div class="sitemap-item static">
          <strong>不盲目扩展覆盖范围</strong>
          <span>当前重点仍是有针对性的诊断，而不是过早地大范围铺开覆盖。</span>
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
        <p class="eyebrow">关注列表</p>
        <h1>在网页端管理你的关注列表。</h1>
        <p class="lede">
          输入 Discord 用户 ID 与卡牌名称，即可创建、查看或删除关注条目。所有操作直接调用现有 API。
        </p>
      </div>
      <div class="intro-note">
        <strong>API 驱动</strong>
        <p>通过 JavaScript fetch 直接调用 watchlist API，无需刷新页面。</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module">
        <div class="module-head">
          <p class="card-kicker">添加关注</p>
          <h2>创建关注条目</h2>
        </div>
        <form class="card-filter-form" id="watchlist-create-form">
          <label>
            <span>Discord 用户 ID</span>
            <input id="create-discord-user-id" name="discord_user_id" type="text" required />
          </label>
          <label>
            <span>卡牌名称</span>
            <input id="create-asset-name" name="asset_name" type="text" required />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" type="submit">添加</button>
          </div>
        </form>
        <p class="status-line" id="watchlist-create-status">就绪。</p>
      </article>

      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">查询</p>
          <h2>查看并删除已保存的关注条目</h2>
        </div>
        <div class="card-filter-form">
          <label>
            <span>Discord 用户 ID</span>
            <input id="lookup-discord-user-id" name="lookup_discord_user_id" type="text" />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" id="watchlist-view-button" type="button">查询</button>
          </div>
        </div>
        <p class="status-line" id="watchlist-lookup-status">输入 Discord 用户 ID 以加载关注列表。</p>
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
        <p class="eyebrow">预警管理</p>
        <h1>创建、查询并维护价格预警</h1>
        <p class="lede">
          使用现有的 <code>/api/v1/alerts</code> 接口创建预警、按 Discord 用户 ID 查询当前预警，并在表格里执行删除或停用操作。
        </p>
      </div>
      <div class="intro-note">
        <strong>API 联动</strong>
        <p>页面通过浏览器端 <code>fetch()</code> 直接请求预警接口，交互方式与关注列表页面保持一致。</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="module">
        <div class="module-head">
          <p class="card-kicker">创建预警</p>
          <h2>新增预警规则</h2>
        </div>
        <form class="card-filter-form" id="alert-create-form">
          <label>
            <span>Discord 用户 ID</span>
            <input id="alert-create-user-id" name="discord_user_id" type="text" required />
          </label>
          <label>
            <span>卡牌名称</span>
            <input id="alert-create-asset-name" name="asset_name" type="text" required />
          </label>
          <label>
            <span>预警类型</span>
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
            <span>阈值</span>
            <input id="alert-create-threshold" name="threshold" type="number" step="0.01" required />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" type="submit">创建</button>
          </div>
        </form>
        <p class="status-line" id="alert-create-status">请填写完整信息后提交。</p>
      </article>

      <article class="module module-wide">
        <div class="module-head">
          <p class="card-kicker">查询预警</p>
          <h2>查看当前预警</h2>
        </div>
        <div class="card-filter-form">
          <label>
            <span>Discord 用户 ID</span>
            <input id="alert-lookup-user-id" name="lookup_discord_user_id" type="text" />
          </label>
          <div class="card-filter-actions">
            <button class="button button-primary" id="alert-query-button" type="button">查询</button>
          </div>
        </div>
        <p class="status-line" id="alert-lookup-status">请输入 Discord 用户 ID 后查询。</p>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>卡牌</th>
                <th>类型</th>
                <th>阈值</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="alert-results-body">
              <tr>
                <td colspan="5" class="empty-state-cell">暂无查询结果。</td>
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
