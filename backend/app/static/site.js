(function () {
  function formatTimestamp(value) {
    if (!value) return "未知时间 · Unknown time";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function metricCard(label, value, detail) {
    return `<article class="metric-card"><span>${label}</span><strong>${value}</strong><p class="result-meta">${detail}</p></article>`;
  }

  function listItem(title, lines) {
    return `<article class="list-item"><strong>${title}</strong>${lines.map((l) => `<span class="list-meta">${l}</span>`).join("")}</article>`;
  }

  async function requestJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (!response.ok) throw new Error(payload?.detail || "Request failed.");
    return payload;
  }

  function renderSnapshot(snapshot) {
    const provider    = document.getElementById("provider-snapshot");
    const signalOps   = document.getElementById("signal-ops");
    const topValue    = document.getElementById("top-value");
    const topMovers   = document.getElementById("top-movers");
    const highActivity = document.getElementById("high-activity-module");
    const poolGrid    = document.getElementById("pool-grid");
    const sampleActions = document.getElementById("sample-actions");
    const lookupStatus  = document.getElementById("lookup-status");

    const ps = snapshot.provider_snapshot;
    provider.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">当前数据源快照 · Current Provider Snapshot</p>
        <h2>${ps.provider_label}</h2>
      </div>
      <div class="metric-stack">
        ${metricCard("追踪卡牌 · Tracked assets", ps.tracked_assets, `${ps.real_history_assets} 条真实历史 · with real history`)}
        ${metricCard("近24小时新增 · Recent rows (24h)", ps.recent_real_rows_24h, `${ps.assets_changed_24h} 张价格变动 · assets changed`)}
        ${metricCard("行变化率(24h) · Row change rate", ps.row_change_pct_24h, `7天 · 7d: ${ps.row_change_pct_7d}`)}
        ${metricCard("已配置数据源 · Configured providers", ps.configured_provider_count, `当前来源 · Active: ${ps.active_source}`)}
      </div>`;

    const ss = snapshot.signal_snapshot;
    signalOps.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">关注列表 / 预警 / 诊断 · Watchlists / Alerts / Diagnostics</p>
        <h2>运营循环 · Operator Loop</h2>
      </div>
      <div class="metric-stack">
        ${metricCard("关注列表 · Watchlists", ss.watchlists, "用户保存的追踪卡牌 · User-saved tracked assets")}
        ${metricCard("活跃预警 · Active alerts", ss.active_alerts, "当前已激活的预警规则 · Live rules currently armed or ready")}
        ${metricCard("诊断 · Diagnostics", ss.diagnostics_label, "池与数据源健康状态持续可见 · Pool and provider health stay visible")}
        ${metricCard("当前模式 · Current mode", snapshot.product_stage.headline, "信号优先，交易市场靠后 · Signals first, marketplace later")}
      </div>
      <p class="status-line">${ss.current_note}</p>`;

    topValue.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">最高价值 · Top Value</p>
        <h2>当前最高价格卡牌 · Highest Current Prices</h2>
      </div>
      <div class="list-shell">
        ${snapshot.top_value.map((item) => listItem(item.name, [
          item.latest_price,
          item.set_name || "系列未知 · Set name unavailable",
          `${item.source} · ${formatTimestamp(item.captured_at)}`,
        ])).join("")}
      </div>`;

    topMovers.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">涨跌榜 · Top Movers</p>
        <h2>近期最大价格变动 · Largest Recent Step Moves</h2>
      </div>
      <div class="list-shell">
        ${snapshot.top_movers.map((item) => listItem(item.name, [
          item.latest_price,
          `变动 · Move: ${item.absolute_change}`,
          `<span class="${item.percent_change.startsWith("-") ? "negative" : "positive"}">${item.percent_change}</span>`,
        ])).join("")}
      </div>`;

    const ha = snapshot.high_activity_v2_vs_baseline;
    highActivity.querySelector(".module-head").innerHTML = `
      <p class="card-kicker">高活跃度 v2 对比基准 · High-Activity v2 vs Baseline</p>
      <h2>${ha.headline}</h2>`;
    highActivity.querySelector(".explanation-copy").innerHTML = `
      <p class="status-line">${ha.summary}</p>
      <div class="list-shell">
        ${ha.bullets.map((l) => `<article class="list-item"><span class="list-meta">${l}</span></article>`).join("")}
      </div>`;

    poolGrid.innerHTML = snapshot.pools.map((pool) => `
      <article class="pool-card">
        <strong>${pool.label}</strong>
        <span>历史覆盖率 · History coverage: ${pool.assets_with_history}</span>
        <span>平均深度 · Avg depth: ${pool.average_depth}</span>
        <span>7天变动 · Changed in 7d: ${pool.changed_assets_7d}</span>
        <span>7天行变化率 · 7d row change: ${pool.row_change_pct_7d}</span>
        <span>无变动卡牌 · No movement: ${pool.no_movement_assets}</span>
      </article>`).join("");

    sampleActions.innerHTML = snapshot.lookup_examples
      .map((name) => `<button type="button" data-query="${name}">${name}</button>`)
      .join("");
    sampleActions.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.getElementById("price-query").value = btn.dataset.query;
        runLookup(btn.dataset.query);
      });
    });

    lookupStatus.textContent = "输入卡牌名称查询价格、预测与历史。Try a tracked card to see price, prediction, and history.";
  }

  function renderLookupResults(prices, predictions, history) {
    const lookupResults = document.getElementById("lookup-results");
    const lookupHistory = document.getElementById("lookup-history");
    const predictionMap = new Map(predictions.map((item) => [item.asset_id, item]));

    lookupResults.innerHTML = prices.slice(0, 4).map((item) => {
      const pred = predictionMap.get(item.asset_id);
      return `<article class="result-card">
        <strong>${item.name}</strong>
        <span class="result-meta">${item.latest_price} ${item.currency}</span>
        <span class="result-meta">${item.set_name || "系列未知 · Set name unavailable"}</span>
        <span class="result-meta">预测 · Prediction: ${pred?.prediction || "暂无 · Unavailable"}</span>
        <span class="result-meta">来源 · Source: ${item.source}</span>
      </article>`;
    }).join("");

    if (!history) {
      lookupHistory.innerHTML = `<article class="history-card"><strong>暂无历史数据 · No history returned</strong><span class="history-meta">换一张已追踪卡牌试试。Try another tracked asset.</span></article>`;
      return;
    }

    lookupHistory.innerHTML = `<article class="history-card">
      <strong>${history.name} 价格历史 · Price History</strong>
      <span class="history-meta">当前价格 · Current price: ${history.current_price} ${history.currency}</span>
      <div class="history-list">
        ${history.history.map((point) => `
          <div class="list-item">
            <strong>${point.price} ${point.currency}</strong>
            <span class="list-meta">${formatTimestamp(point.captured_at)}</span>
            <span class="list-meta">${point.source}</span>
          </div>`).join("")}
      </div>
    </article>`;
  }

  async function runLookup(rawQuery) {
    const query = rawQuery.trim();
    const lookupStatus = document.getElementById("lookup-status");
    const apiPrefix = document.querySelector("[data-price-api-prefix]").dataset.priceApiPrefix;

    if (!query) {
      lookupStatus.textContent = "请先输入卡牌名称。Enter a tracked asset name first.";
      return;
    }

    lookupStatus.textContent = `查询中 "${query}"... Looking up...`;

    try {
      const prices = await requestJson(`${apiPrefix}/search?name=${encodeURIComponent(query)}`);
      const predictions = await requestJson(`${apiPrefix}/predict?name=${encodeURIComponent(query)}`).catch(() => []);
      const history = await requestJson(`${apiPrefix}/history?name=${encodeURIComponent(query)}&limit=5`).catch(() => null);
      renderLookupResults(prices, predictions, history);
      lookupStatus.textContent = `"${query}" 实时查询结果 · Live results`;
    } catch (error) {
      document.getElementById("lookup-results").innerHTML = "";
      document.getElementById("lookup-history").innerHTML = "";
      lookupStatus.textContent = error.message;
    }
  }

  async function hydrateDashboard() {
    const shell = document.querySelector("[data-dashboard-snapshot-url]");
    const snapshotUrl = shell?.dataset.dashboardSnapshotUrl;
    if (!snapshotUrl) return;
    try {
      const snapshot = await requestJson(snapshotUrl);
      renderSnapshot(snapshot);
    } catch (error) {
      const lookupStatus = document.getElementById("lookup-status");
      if (lookupStatus) lookupStatus.textContent = `仪表板数据加载失败 · Dashboard snapshot unavailable: ${error.message}`;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const shell = document.querySelector("[data-page]");
    if (!shell) return;
    if (shell.dataset.page === "dashboard") {
      hydrateDashboard();
      document.getElementById("price-lookup-form")?.addEventListener("submit", (e) => {
        e.preventDefault();
        runLookup(document.getElementById("price-query").value);
      });
    }
  });
})();
