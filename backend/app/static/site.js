(function () {
  // Inject fadeIn keyframes for skeleton replacement animation
  const fadeStyle = document.createElement("style");
  fadeStyle.textContent = [
    "@keyframes fadeIn {",
    "  from { opacity: 0; transform: translateY(4px); }",
    "  to   { opacity: 1; transform: translateY(0); }",
    "}",
    ".fade-in { animation: fadeIn 0.3s ease forwards; }",
  ].join("\n");
  document.head.appendChild(fadeStyle);

  // Language toggle
  const LANG_KEY = "fp_lang";
  const LANG_MODES = ["zh", "en"];
  // Button shows the language you will SWITCH TO
  const LANG_NEXT_LABELS = { zh: "EN", en: "\u4e2d\u6587" };

  function getLang() {
    const saved = localStorage.getItem(LANG_KEY);
    return saved === "zh" || saved === "en" ? saved : "zh";
  }

  function setLang(mode) {
    localStorage.setItem(LANG_KEY, mode);
    document.body.dataset.lang = mode;
    const btn = document.getElementById("lang-toggle");
    if (btn) btn.textContent = LANG_NEXT_LABELS[mode];
  }

  function t(zh, en) {
    return getLang() === "en" ? en : zh;
  }

  // Helpers
  function formatTimestamp(value) {
    if (!value) return t("\u672a\u77e5\u65f6\u95f4", "Unknown time");
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function metricCard(zh, en, value, detailZh, detailEn, isTextLabel) {
    const valueClass = isTextLabel ? "metric-value text-label" : "metric-value";
    return `<article class="metric-card">
      <span class="metric-label">${t(zh, en)}</span>
      <strong class="${valueClass}">${value}</strong>
      <p class="result-meta">${t(detailZh, detailEn)}</p>
    </article>`;
  }

  function fadeInChildren(el) {
    if (!el) return;
    Array.from(el.children).forEach((child, i) => {
      child.style.animationDelay = `${i * 0.05}s`;
      child.classList.add("fade-in");
    });
  }

  // Snapshot rendering
  let _lastSnapshot = null;

  function renderSnapshot(snapshot) {
    _lastSnapshot = snapshot;
    const ps = snapshot.provider_snapshot || {};
    const ss = snapshot.signal_snapshot || {};

    // Provider snapshot module
    const providerModule = document.getElementById("provider-snapshot");
    if (providerModule) {
      providerModule.querySelector(".module-head").innerHTML = `
        <p class="card-kicker">${t("\u5f53\u524d\u6570\u636e\u6e90\u5feb\u7167", "Current provider snapshot")}</p>
        <h2>${ps.provider_label || ps.active_source || t("\u6570\u636e\u6e90", "Provider")}</h2>`;
      const stack = providerModule.querySelector(".metric-stack");
      if (stack) {
        stack.innerHTML = [
          metricCard("\u8ffd\u8e2a\u8d44\u4ea7", "Tracked assets",
            ps.tracked_assets ?? "\u2014",
            `${ps.recent_real_rows_24h ?? 0} \u884c / 24h`,
            `${ps.recent_real_rows_24h ?? 0} rows / 24h`),
          metricCard("24h \u884c\u6570", "Recent rows (24h)",
            ps.recent_real_rows_24h ?? "\u2014",
            t("\u6700\u8fd1\u6295\u9012\u884c\u6570", "Recently ingested rows"),
            t("\u6700\u8fd1\u6295\u9012\u884c\u6570", "Recently ingested rows")),
          metricCard("\u884c\u53d8\u5316\u7387 (24h)", "Row change rate",
            ps.row_change_pct_24h ?? "\u2014",
            t("\u53ef\u6bd4\u8f83\u884c\u53d1\u751f\u53d8\u5316\u7684\u6bd4\u4f8b", "% of comparable rows that changed"),
            t("\u53ef\u6bd4\u8f83\u884c\u53d1\u751f\u53d8\u5316\u7684\u6bd4\u4f8b", "% of comparable rows that changed")),
          metricCard("\u5df2\u914d\u7f6e\u6570\u636e\u6e90", "Configured providers",
            ps.configured_provider_count ?? "\u2014",
            t("\u6d3b\u8dc3\u63d2\u69fd\u6570", "Active provider slots"),
            t("\u6d3b\u8dc3\u63d2\u69fd\u6570", "Active provider slots")),
        ].join("");
        fadeInChildren(stack);
      }
    }

    // Signal ops module
    const signalOps = document.getElementById("signal-ops");
    if (signalOps) {
      const stack = signalOps.querySelector(".metric-stack");
      if (stack) {
        stack.innerHTML = [
          metricCard("\u5173\u6ce8\u5217\u8868", "Watchlists",
            ss.watchlists ?? "\u2014",
            t("\u7528\u6237\u4fdd\u5b58\u7684\u8ffd\u8e2a\u5361\u724c", "User-saved card watchlists"),
            t("\u7528\u6237\u4fdd\u5b58\u7684\u8ffd\u8e2a\u5361\u724c", "User-saved card watchlists")),
          metricCard("\u6d3b\u8dc3\u9884\u8b66", "Active alerts",
            ss.active_alerts ?? "\u2014",
            t("\u5f53\u524d\u5df2\u6fc0\u6d3b\u9884\u8b66\u6761\u6570", "Currently active alert rules"),
            t("\u5f53\u524d\u5df2\u6fc0\u6d3b\u9884\u8b66\u6761\u6570", "Currently active alert rules")),
        ].join("");
        fadeInChildren(stack);
      }
    }

    // Top value
    const topValue = document.getElementById("top-value");
    if (topValue && snapshot.top_value) {
      const list = topValue.querySelector(".list-shell");
      if (list) {
        list.innerHTML = snapshot.top_value.map((item) => `
          <div class="mover-row">
            <div>
              <a class="mover-name" href="/cards/${item.external_id}">${item.name}</a>
              <span class="list-meta">${item.set_name || t("\u7cfb\u5217\u672a\u77e5", "Set unknown")}</span>
            </div>
            <span class="badge-price">${item.latest_price}</span>
          </div>`).join("");
        fadeInChildren(list);
      }
    }

    // Top movers
    const topMovers = document.getElementById("top-movers");
    if (topMovers && snapshot.top_movers) {
      const list = topMovers.querySelector(".list-shell");
      if (list) {
        list.innerHTML = snapshot.top_movers.map((item) => {
          const up = (item.percent_change_raw ?? 0) >= 0;
          return `
          <div class="mover-row">
            <div>
              <a class="mover-name" href="/cards/${item.external_id}">${item.name}</a>
              <span class="list-meta">${t("\u53d8\u52a8", "Move")}: ${item.absolute_change}</span>
            </div>
            <span class="${up ? "badge-up" : "badge-down"}">${item.percent_change}</span>
          </div>`;
        }).join("");
        fadeInChildren(list);
      }
    }

    // Smart pool candidates
    const smartPoolList = document.getElementById("smart-pool-list");
    if (smartPoolList && snapshot.smart_pool_candidates) {
      smartPoolList.innerHTML = snapshot.smart_pool_candidates.map((item) => `
        <div class="mover-row">
          <div>
            <a class="mover-name" href="/cards/${item.external_id}">${item.name}</a>
            <span class="list-meta">Liquidity: ${Number(item.liquidity_score ?? 0).toFixed(1)}</span>
          </div>
          <span class="badge-up">${Number(item.composite_score ?? 0).toFixed(1)}</span>
        </div>`).join("");
      fadeInChildren(smartPoolList);
    }

    // High-activity comparison
    const ha = snapshot.high_activity_v2_vs_baseline;
    const highActivity = document.getElementById("high-activity-module");
    if (highActivity && ha) {
      highActivity.querySelector(".module-head").innerHTML = `
        <p class="card-kicker">${t("High-Activity v2 \u5bf9\u6bd4\u57fa\u51c6", "High-Activity v2 vs Baseline")}</p>
        <h2>${ha.headline || ""}</h2>`;
      const copy = highActivity.querySelector(".explanation-copy");
      if (copy) {
        copy.innerHTML = `<p>${ha.summary || ""}</p>` +
          (ha.bullets || []).map((b) => `<p class="result-meta">${b}</p>`).join("");
        fadeInChildren(copy);
      }
      const poolGrid = document.getElementById("pool-grid");
      if (poolGrid && snapshot.pools) {
        poolGrid.innerHTML = snapshot.pools.map((pool) => `
          <div class="pool-card">
            <strong>${pool.label}</strong>
            <span>${t("\u5386\u53f2\u8986\u76d6", "History coverage")}: ${pool.assets_with_history}/${pool.total_assets}</span>
            <span>${t("\u5e73\u5747\u6df1\u5ea6", "Avg depth")}: ${pool.average_depth}</span>
            <span>${t("7\u5929\u53d8\u52a8", "Changed in 7d")}: ${pool.changed_assets_7d}</span>
            <span>${t("7\u5929\u884c\u53d8\u5316\u7387", "7d row change")}: ${pool.row_change_pct_7d}</span>
            <span>${t("\u65e0\u4ef7\u683c\u53d8\u52a8", "No movement")}: ${pool.no_movement_assets}</span>
          </div>`).join("");
        fadeInChildren(poolGrid);
      }
    }

    // Sample buttons
    const sampleActions = document.getElementById("sample-actions");
    if (sampleActions && snapshot.lookup_examples) {
      sampleActions.innerHTML = snapshot.lookup_examples.map((name) =>
        `<button class="btn btn-secondary btn-sm sample-btn" type="button">${name}</button>`
      ).join("");
      sampleActions.querySelectorAll(".sample-btn").forEach((btn) => {
        btn.addEventListener("click", () => runLookup(btn.textContent));
      });
    }
  }

  // Lookup rendering
  function renderLookupResult(item) {
    const pred = item.prediction;
    return `
      <div class="result-card">
        <a class="result-name" href="/cards/${item.external_id}">${item.name}</a>
        <span class="price-tag">${item.latest_price}</span>
        <span class="result-meta">${item.set_name || t("\u7cfb\u5217\u672a\u77e5", "Set name unavailable")}</span>
        <span class="result-meta">${t("\u9884\u6d4b", "Prediction")}: ${pred?.prediction_label ?? "\u2014"}</span>
        <span class="result-meta">${t("\u6765\u6e90", "Source")}: ${item.source}</span>
      </div>`;
  }

  function renderHistory(history) {
    if (!history || !history.history || history.history.length === 0) {
      return `<div class="lookup-history-empty">
        <strong>${t("\u672a\u8fd4\u56de\u5386\u53f2\u6570\u636e", "No history returned")}</strong>
        <span class="history-meta">${t("\u8be5\u5361\u724c\u5df2\u8ffd\u8e2a\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5", "Try another tracked card")}</span>
      </div>`;
    }
    return `
      <div class="lookup-history-block">
        <strong>${history.name} ${t("\u4ef7\u683c\u5386\u53f2", "Price History")}</strong>
        <span class="history-meta">${t("\u5f53\u524d\u4ef7\u683c", "Current price")}: ${history.latest_price}</span>
        <table class="data-table history-table">
          <thead><tr>
            <th>${t("\u65e5\u671f", "Date")}</th>
            <th>${t("\u4ef7\u683c", "Price")}</th>
            <th>${t("\u6765\u6e90", "Source")}</th>
          </tr></thead>
          <tbody>${history.history.map((row) => `<tr>
            <td>${formatTimestamp(row.captured_at)}</td>
            <td>${row.price}</td>
            <td>${row.source}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  }

  async function runLookup(query) {
    const apiPrefix = document.querySelector("[data-price-api-prefix]")?.dataset?.priceApiPrefix;
    const resultsEl = document.getElementById("lookup-results");
    const historyEl = document.getElementById("lookup-history");
    const statusEl = document.getElementById("lookup-status");
    if (!resultsEl || !statusEl || !apiPrefix) return;

    if (!query || !query.trim()) {
      statusEl.textContent = t("\u8bf7\u5148\u8f93\u5165\u5361\u724c\u540d\u79f0\u67e5\u8be2\u4ef7\u683c\u3002", "Enter a tracked asset name to look up a price.");
      return;
    }
    statusEl.textContent = t(`\u67e5\u8be2\u4e2d\u201c${query}\u201d\u2026`, `Looking up "${query}"...`);
    resultsEl.innerHTML = "";
    if (historyEl) historyEl.innerHTML = "";

    try {
      const res = await fetch(`${apiPrefix}/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      const items = Array.isArray(data) ? data : (data.results || []);
      if (items.length === 0) {
        statusEl.textContent = t(`\u672a\u627e\u5230\u201c${query}\u201d`, `No results for "${query}"`);
        return;
      }
      statusEl.textContent = t(`\u201c${query}\u201d \u5b9e\u65f6\u67e5\u8be2\u7ed3\u679c`, `Live results for "${query}"`);
      resultsEl.innerHTML = items.map(renderLookupResult).join("");

      if (historyEl && items[0]?.external_id) {
        const hRes = await fetch(`${apiPrefix}/history/${encodeURIComponent(items[0].external_id)}`);
        const hData = await hRes.json();
        historyEl.innerHTML = renderHistory(hData);
      }
    } catch (error) {
      statusEl.textContent = t(
        `\u4ed3\u8868\u677f\u6570\u636e\u52a0\u8f7d\u5931\u8d25: ${error.message}`,
        `Dashboard data load failed: ${error.message}`
      );
    }
  }

  // Dashboard hydration
  async function hydrateDashboard() {
    const snapshotUrl = document.querySelector("[data-dashboard-snapshot-url]")?.dataset?.dashboardSnapshotUrl;
    if (!snapshotUrl) return;
    try {
      const res = await fetch(snapshotUrl);
      const snapshot = await res.json();
      renderSnapshot(snapshot);
    } catch (error) {
      console.error("Dashboard snapshot failed:", error);
    }
  }

  // Boot
  document.addEventListener("DOMContentLoaded", () => {
    setLang(getLang());

    const toggleBtn = document.getElementById("lang-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const current = getLang();
        const next = LANG_MODES[(LANG_MODES.indexOf(current) + 1) % LANG_MODES.length];
        setLang(next);
        if (_lastSnapshot) renderSnapshot(_lastSnapshot);
      });
    }

    const shell = document.querySelector("[data-page]");
    if (!shell) return;

    if (shell.dataset.page === "dashboard") {
      hydrateDashboard();
      document.getElementById("price-lookup-form")?.addEventListener("submit", (e) => {
        e.preventDefault();
        runLookup(document.getElementById("price-query").value.trim());
      });
    }
  });
})();
