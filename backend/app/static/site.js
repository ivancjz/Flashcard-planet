(function () {
  const fadeStyle = document.createElement("style");
  fadeStyle.textContent = `
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .fade-in {
      animation: fadeIn 0.3s ease forwards;
    }
  `;
  document.head.appendChild(fadeStyle);

  // ?Ä?Ä Language toggle ?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä
  const LANG_KEY = "fp_lang";
  const LANG_MODES = ["zh", "en"];
  const LANG_LABELS = { zh: "‰∏≠Ê?", en: "EN" };

  function getLang() {
    const saved = localStorage.getItem(LANG_KEY);
    return saved === "zh" || saved === "en" ? saved : "zh";
  }

  function setLang(mode) {
    localStorage.setItem(LANG_KEY, mode);
    document.body.dataset.lang = mode;
    const btn = document.getElementById("lang-toggle");
    if (btn) btn.textContent = LANG_LABELS[mode];
  }

  // Returns string based on current mode
  function t(zh, en) {
    return getLang() === "en" ? en : zh;
  }

  // ?Ä?Ä Helpers ?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä
  function formatTimestamp(value) {
    if (!value) return t("?™Áü•?∂Èó¥", "Unknown time");
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function metricCard(zh, en, value, detailZh, detailEn) {
    return `<article class="metric-card">
      <span>${t(zh, en)}</span>
      <strong>${value}</strong>
      <p class="result-meta">${t(detailZh, detailEn)}</p>
    </article>`;
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

  function fadeInChildren(container) {
    if (!container) return;
    container.querySelectorAll(":scope > *").forEach((element) => {
      element.classList.add("fade-in");
    });
  }

  // ?Ä?Ä Snapshot rendering ?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä
  let _lastSnapshot = null;

  function renderSnapshot(snapshot) {
    _lastSnapshot = snapshot;
    const provider     = document.getElementById("provider-snapshot");
    const signalOps    = document.getElementById("signal-ops");
    const topValue     = document.getElementById("top-value");
    const topMovers    = document.getElementById("top-movers");
    const highActivity = document.getElementById("high-activity-module");
    const poolGrid     = document.getElementById("pool-grid");
    const sampleActions = document.getElementById("sample-actions");
    const lookupStatus  = document.getElementById("lookup-status");

    if (!provider) return;

    const ps = snapshot.provider_snapshot;
    provider.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">${t("ÂΩìÂ??∞ÊçÆÊ∫êÂø´??, "Current Provider Snapshot")}</p>
        <h2>${ps.provider_label}</h2>
      </div>
      <div class="metric-stack">
        ${metricCard("ËøΩË∏™?°Á?", "Tracked assets", ps.tracked_assets, `${ps.real_history_assets} ?°Á?ÂÆûÂ??≤`, `${ps.real_history_assets} with real history`)}
        ${metricCard("Ëø?4Â∞èÊó∂?∞Â?", "Recent rows (24h)", ps.recent_real_rows_24h, `${ps.assets_changed_24h} Âº†‰ª∑?ºÂ??®`, `${ps.assets_changed_24h} assets changed`)}
        ${metricCard("Ë°åÂ??ñÁ?(24h)", "Row change rate", ps.row_change_pct_24h, `7Â§? ${ps.row_change_pct_7d}`, `7d: ${ps.row_change_pct_7d}`)}
        ${metricCard("Â∑≤È?ÁΩÆÊï∞?ÆÊ?", "Configured providers", ps.configured_provider_count, `ÂΩìÂ??•Ê?: ${ps.active_source}`, `Active: ${ps.active_source}`)}
      </div>`;

    fadeInChildren(provider);

    const ss = snapshot.signal_snapshot;
    signalOps.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">${t("?≥Ê≥®?óË°® / È¢ÑË≠¶ / ËØäÊñ≠", "Watchlists / Alerts / Diagnostics")}</p>
        <h2>${t("ËøêËê•Âæ™ÁéØ", "Operator Loop")}</h2>
      </div>
      <div class="metric-stack">
        ${metricCard("?≥Ê≥®?óË°®", "Watchlists", ss.watchlists, "?®Êà∑‰øùÂ??ÑËøΩË∏™Âç°??, "User-saved tracked assets")}
        ${metricCard("Ê¥ªË?È¢ÑË≠¶", "Active alerts", ss.active_alerts, "ÂΩìÂ?Â∑≤Ê?Ê¥ªÁ?È¢ÑË≠¶ËßÑÂ?", "Live rules currently armed or ready")}
        ${metricCard("ËØäÊñ≠", "Diagnostics", ss.diagnostics_label, "Ê±†‰??∞ÊçÆÊ∫êÂÅ•Â∫∑Áä∂?ÅÊ?Áª≠ÂèØËß?, "Pool and provider health stay visible")}
        ${metricCard("ÂΩìÂ?Ê®°Â?", "Current mode", snapshot.product_stage.headline, "‰ø°Âè∑‰ºòÂ?Ôºå‰∫§?ìÂ??∫È???, "Signals first, marketplace later")}
      </div>
      <p class="status-line">${ss.current_note}</p>`;

    fadeInChildren(signalOps);

    topValue.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">${t("?ÄÈ´ò‰ª∑??, "Top Value")}</p>
        <h2>${t("ÂΩìÂ??ÄÈ´ò‰ª∑?ºÂç°??, "Highest Current Prices")}</h2>
      </div>
      <div class="list-shell">
        ${snapshot.top_value.map((item) => listItem(item.name, [
          item.latest_price,
          item.set_name || t("Á≥ªÂ??™Áü•", "Set name unavailable"),
          `${item.source} ¬∑ ${formatTimestamp(item.captured_at)}`,
        ])).join("")}
      </div>`;

    fadeInChildren(topValue);

    topMovers.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">${t("Ê∂®Ë?Ê¶?, "Top Movers")}</p>
        <h2>${t("ËøëÊ??ÄÂ§ß‰ª∑?ºÂ???, "Largest Recent Step Moves")}</h2>
      </div>
      <div class="list-shell">
        ${snapshot.top_movers.map((item) => listItem(item.name, [
          item.latest_price,
          `${t("?òÂä®", "Move")}: ${item.absolute_change}`,
          `<span class="${item.percent_change.startsWith("-") ? "negative" : "positive"}">${item.percent_change}</span>`,
        ])).join("")}
      </div>`;

    fadeInChildren(topMovers);

    const ha = snapshot.high_activity_v2_vs_baseline;
    highActivity.querySelector(".module-head").innerHTML = `
      <p class="card-kicker">${t("È´òÊ¥ªË∑ÉÂ∫¶ v2 ÂØπÊ??∫Â?", "High-Activity v2 vs Baseline")}</p>
      <h2>${ha.headline}</h2>`;
    highActivity.querySelector(".explanation-copy").innerHTML = `
      <p class="status-line">${ha.summary}</p>
      <div class="list-shell">
        ${ha.bullets.map((l) => `<article class="list-item"><span class="list-meta">${l}</span></article>`).join("")}
      </div>`;

    fadeInChildren(highActivity.querySelector(".module-head"));
    fadeInChildren(highActivity.querySelector(".explanation-copy"));

    poolGrid.innerHTML = snapshot.pools.map((pool) => `
      <article class="pool-card">
        <strong>${pool.label}</strong>
        <span>${t("?ÜÂè≤Ë¶ÜÁ???, "History coverage")}: ${pool.assets_with_history}</span>
        <span>${t("Âπ≥Â?Ê∑±Â∫¶", "Avg depth")}: ${pool.average_depth}</span>
        <span>${t("7Â§©Â???, "Changed in 7d")}: ${pool.changed_assets_7d}</span>
        <span>${t("7Â§©Ë??òÂ???, "7d row change")}: ${pool.row_change_pct_7d}</span>
        <span>${t("?†Â??®Âç°??, "No movement")}: ${pool.no_movement_assets}</span>
      </article>`).join("");

    fadeInChildren(poolGrid);

    sampleActions.innerHTML = snapshot.lookup_examples
      .map((name) => `<button type="button" data-query="${name}">${name}</button>`)
      .join("");
    fadeInChildren(sampleActions);

    sampleActions.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.getElementById("price-query").value = btn.dataset.query;
        runLookup(btn.dataset.query);
      });
    });

    lookupStatus.textContent = t(
      "ËæìÂÖ•?°Á??çÁß∞?•ËØ¢‰ª∑Ê†º?ÅÈ?Êµã‰??ÜÂè≤ËÆ∞Â???,
      "Try a tracked card to see price, prediction, and history."
    );
  }

  // ?Ä?Ä Lookup rendering ?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä
  function renderLookupResults(prices, predictions, history) {
    const lookupResults = document.getElementById("lookup-results");
    const lookupHistory = document.getElementById("lookup-history");
    const predictionMap = new Map(predictions.map((item) => [item.asset_id, item]));

    lookupResults.innerHTML = prices.slice(0, 4).map((item) => {
      const pred = predictionMap.get(item.asset_id);
      return `<article class="result-card">
        <strong>${item.name}</strong>
        <span class="result-meta">${item.latest_price} ${item.currency}</span>
        <span class="result-meta">${item.set_name || t("Á≥ªÂ??™Áü•", "Set name unavailable")}</span>
        <span class="result-meta">${t("È¢ÑÊ?", "Prediction")}: ${pred?.prediction || t("?ÇÊ?", "Unavailable")}</span>
        <span class="result-meta">${t("?•Ê?", "Source")}: ${item.source}</span>
      </article>`;
    }).join("");

    fadeInChildren(lookupResults);

    if (!history) {
      lookupHistory.innerHTML = `<article class="history-card">
        <strong>${t("?ÇÊ??ÜÂè≤?∞ÊçÆ", "No history returned")}</strong>
        <span class="history-meta">${t("?¢‰?Âº†Â∑≤ËøΩË∏™?°Á?ËØïË???, "Try another tracked asset.")}</span>
      </article>`;
      fadeInChildren(lookupHistory);
      return;
    }

    lookupHistory.innerHTML = `<article class="history-card">
      <strong>${history.name} ${t("‰ª∑Ê†º?ÜÂè≤", "Price History")}</strong>
      <span class="history-meta">${t("ÂΩìÂ?‰ª∑Ê†º", "Current price")}: ${history.current_price} ${history.currency}</span>
      <div class="history-list">
        ${history.history.map((point) => `
          <div class="list-item">
            <strong>${point.price} ${point.currency}</strong>
            <span class="list-meta">${formatTimestamp(point.captured_at)}</span>
            <span class="list-meta">${point.source}</span>
          </div>`).join("")}
      </div>
    </article>`;
    fadeInChildren(lookupHistory);
  }

  async function runLookup(rawQuery) {
    const query = rawQuery.trim();
    const lookupStatus = document.getElementById("lookup-status");
    const apiPrefix = document.querySelector("[data-price-api-prefix]").dataset.priceApiPrefix;

    if (!query) {
      lookupStatus.textContent = t("ËØ∑Â?ËæìÂÖ•?°Á??çÁß∞??, "Enter a tracked asset name first.");
      return;
    }
    lookupStatus.textContent = t(`?•ËØ¢‰∏?"${query}"...`, `Looking up "${query}"...`);
    try {
      const prices = await requestJson(`${apiPrefix}/search?name=${encodeURIComponent(query)}`);
      const predictions = await requestJson(`${apiPrefix}/predict?name=${encodeURIComponent(query)}`).catch(() => []);
      const history = await requestJson(`${apiPrefix}/history?name=${encodeURIComponent(query)}&limit=5`).catch(() => null);
      renderLookupResults(prices, predictions, history);
      lookupStatus.textContent = t(`"${query}" ÂÆûÊó∂?•ËØ¢ÁªìÊ?`, `Live results for "${query}"`);
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
      if (lookupStatus) lookupStatus.textContent = t(
        `‰ª™Ë°®?øÊï∞?ÆÂ?ËΩΩÂ§±Ë¥? ${error.message}`,
        `Dashboard snapshot unavailable: ${error.message}`
      );
    }
  }

  // ?Ä?Ä Boot ?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä?Ä
  document.addEventListener("DOMContentLoaded", () => {
    // Apply saved lang mode
    setLang(getLang());

    // Wire lang toggle button
    const toggleBtn = document.getElementById("lang-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const current = getLang();
        const next = LANG_MODES[(LANG_MODES.indexOf(current) + 1) % LANG_MODES.length];
        setLang(next);
        // Re-render dynamic content with new language
        if (_lastSnapshot) renderSnapshot(_lastSnapshot);
      });
    }

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

