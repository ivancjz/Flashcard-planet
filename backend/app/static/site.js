(function () {
  function formatTimestamp(value) {
    if (!value) {
      return "Unknown time";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }

    return parsed.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }

  function metricCard(label, value, detail) {
    return `
      <article class="metric-card">
        <span>${label}</span>
        <strong>${value}</strong>
        <p class="result-meta">${detail}</p>
      </article>
    `;
  }

  function listItem(title, lines) {
    return `
      <article class="list-item">
        <strong>${title}</strong>
        ${lines.map((line) => `<span class="list-meta">${line}</span>`).join("")}
      </article>
    `;
  }

  async function requestJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    let payload = null;

    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }

    if (!response.ok) {
      throw new Error(payload?.detail || "Request failed.");
    }

    return payload;
  }

  function renderSnapshot(snapshot) {
    const provider = document.getElementById("provider-snapshot");
    const signalOps = document.getElementById("signal-ops");
    const topValue = document.getElementById("top-value");
    const topMovers = document.getElementById("top-movers");
    const highActivity = document.getElementById("high-activity-module");
    const poolGrid = document.getElementById("pool-grid");
    const sampleActions = document.getElementById("sample-actions");
    const lookupStatus = document.getElementById("lookup-status");

    provider.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">Current provider snapshot</p>
        <h2>${snapshot.provider_snapshot.provider_label}</h2>
      </div>
      <div class="metric-stack">
        ${metricCard(
          "Tracked assets",
          snapshot.provider_snapshot.tracked_assets,
          `${snapshot.provider_snapshot.real_history_assets} with real history`
        )}
        ${metricCard(
          "Recent rows (24h)",
          snapshot.provider_snapshot.recent_real_rows_24h,
          `${snapshot.provider_snapshot.assets_changed_24h} assets changed`
        )}
        ${metricCard(
          "Row change rate (24h)",
          snapshot.provider_snapshot.row_change_pct_24h,
          `7d: ${snapshot.provider_snapshot.row_change_pct_7d}`
        )}
        ${metricCard(
          "Configured providers",
          snapshot.provider_snapshot.configured_provider_count,
          `Active source: ${snapshot.provider_snapshot.active_source}`
        )}
      </div>
    `;

    signalOps.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">Watchlists / alerts / diagnostics</p>
        <h2>Operator loop</h2>
      </div>
      <div class="metric-stack">
        ${metricCard("Watchlists", snapshot.signal_snapshot.watchlists, "User-saved tracked assets")}
        ${metricCard("Active alerts", snapshot.signal_snapshot.active_alerts, "Live rules currently armed or ready")}
        ${metricCard("Diagnostics", snapshot.signal_snapshot.diagnostics_label, "Pool and provider health stay visible")}
        ${metricCard("Current mode", snapshot.product_stage.headline, "Signals first, marketplace later")}
      </div>
      <p class="status-line">${snapshot.signal_snapshot.current_note}</p>
    `;

    topValue.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">Top value</p>
        <h2>Highest current prices</h2>
      </div>
      <div class="list-shell">
        ${snapshot.top_value
          .map((item) =>
            listItem(item.name, [
              item.latest_price,
              item.set_name || "Set name unavailable",
              `${item.source} · ${formatTimestamp(item.captured_at)}`,
            ])
          )
          .join("")}
      </div>
    `;

    topMovers.innerHTML = `
      <div class="module-head">
        <p class="card-kicker">Top movers</p>
        <h2>Largest recent step moves</h2>
      </div>
      <div class="list-shell">
        ${snapshot.top_movers
          .map((item) =>
            listItem(item.name, [
              item.latest_price,
              `Move: ${item.absolute_change}`,
              `<span class="${item.percent_change.startsWith("-") ? "negative" : "positive"}">${item.percent_change}</span>`,
            ])
          )
          .join("")}
      </div>
    `;

    highActivity.querySelector(".module-head").innerHTML = `
      <p class="card-kicker">High-Activity v2 vs baseline</p>
      <h2>${snapshot.high_activity_v2_vs_baseline.headline}</h2>
    `;
    highActivity.querySelector(".explanation-copy").innerHTML = `
      <p class="status-line">${snapshot.high_activity_v2_vs_baseline.summary}</p>
      <div class="list-shell">
        ${snapshot.high_activity_v2_vs_baseline.bullets
          .map((line) => `<article class="list-item"><span class="list-meta">${line}</span></article>`)
          .join("")}
      </div>
    `;
    poolGrid.innerHTML = snapshot.pools
      .map(
        (pool) => `
          <article class="pool-card">
            <strong>${pool.label}</strong>
            <span>History coverage: ${pool.assets_with_history}</span>
            <span>Average depth: ${pool.average_depth}</span>
            <span>Changed in 7d: ${pool.changed_assets_7d}</span>
            <span>7d row change: ${pool.row_change_pct_7d}</span>
            <span>No movement assets: ${pool.no_movement_assets}</span>
          </article>
        `
      )
      .join("");

    sampleActions.innerHTML = snapshot.lookup_examples
      .map((name) => `<button type="button" data-query="${name}">${name}</button>`)
      .join("");

    sampleActions.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        const input = document.getElementById("price-query");
        input.value = button.dataset.query;
        runLookup(button.dataset.query);
      });
    });

    lookupStatus.textContent = "Try a tracked card to see the current price, prediction, and short history.";
  }

  function renderLookupResults(prices, predictions, history) {
    const lookupResults = document.getElementById("lookup-results");
    const lookupHistory = document.getElementById("lookup-history");
    const predictionMap = new Map(predictions.map((item) => [item.asset_id, item]));

    lookupResults.innerHTML = prices
      .slice(0, 4)
      .map((item) => {
        const prediction = predictionMap.get(item.asset_id);
        return `
          <article class="result-card">
            <strong>${item.name}</strong>
            <span class="result-meta">${item.latest_price} ${item.currency}</span>
            <span class="result-meta">${item.set_name || "Set name unavailable"}</span>
            <span class="result-meta">Prediction: ${prediction?.prediction || "Unavailable"}</span>
            <span class="result-meta">Source: ${item.source}</span>
          </article>
        `;
      })
      .join("");

    if (!history) {
      lookupHistory.innerHTML = '<article class="history-card"><strong>No history returned</strong><span class="history-meta">Try another tracked asset.</span></article>';
      return;
    }

    lookupHistory.innerHTML = `
      <article class="history-card">
        <strong>${history.name} history</strong>
        <span class="history-meta">Current price: ${history.current_price} ${history.currency}</span>
        <div class="history-list">
          ${history.history
            .map(
              (point) => `
                <div class="list-item">
                  <strong>${point.price} ${point.currency}</strong>
                  <span class="list-meta">${formatTimestamp(point.captured_at)}</span>
                  <span class="list-meta">${point.source}</span>
                </div>
              `
            )
            .join("")}
        </div>
      </article>
    `;
  }

  async function runLookup(rawQuery) {
    const query = rawQuery.trim();
    const lookupStatus = document.getElementById("lookup-status");
    const apiPrefix = document.querySelector("[data-price-api-prefix]").dataset.priceApiPrefix;

    if (!query) {
      lookupStatus.textContent = "Enter a tracked asset name first.";
      return;
    }

    lookupStatus.textContent = `Looking up "${query}"...`;

    try {
      const prices = await requestJson(`${apiPrefix}/search?name=${encodeURIComponent(query)}`);
      const predictions = await requestJson(`${apiPrefix}/predict?name=${encodeURIComponent(query)}`).catch(() => []);
      const history = await requestJson(
        `${apiPrefix}/history?name=${encodeURIComponent(query)}&limit=5`
      ).catch(() => null);

      renderLookupResults(prices, predictions, history);
      lookupStatus.textContent = `Showing live results for "${query}".`;
    } catch (error) {
      document.getElementById("lookup-results").innerHTML = "";
      document.getElementById("lookup-history").innerHTML = "";
      lookupStatus.textContent = error.message;
    }
  }

  async function hydrateDashboard() {
    const shell = document.querySelector("[data-dashboard-snapshot-url]");
    const snapshotUrl = shell?.dataset.dashboardSnapshotUrl;

    if (!snapshotUrl) {
      return;
    }

    try {
      const snapshot = await requestJson(snapshotUrl);
      renderSnapshot(snapshot);
    } catch (error) {
      const lookupStatus = document.getElementById("lookup-status");
      if (lookupStatus) {
        lookupStatus.textContent = `Dashboard snapshot unavailable: ${error.message}`;
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const shell = document.querySelector("[data-page]");
    if (!shell) {
      return;
    }

    if (shell.dataset.page === "dashboard") {
      hydrateDashboard();

      const form = document.getElementById("price-lookup-form");
      form?.addEventListener("submit", (event) => {
        event.preventDefault();
        runLookup(document.getElementById("price-query").value);
      });
    }
  });
})();
