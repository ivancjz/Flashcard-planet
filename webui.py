from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover - handled at runtime after dependency install
    raise SystemExit(
        "Streamlit is required for the Flashcard Planet web UI. Install requirements and run `streamlit run webui.py`."
    ) from exc

from sqlalchemy import func, select

from backend.app.core.config import get_settings
from backend.app.core.price_sources import SAMPLE_PRICE_SOURCE, get_active_price_source_filter
from backend.app.db.session import SessionLocal
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.models.watchlist import Watchlist
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.liquidity_service import get_asset_signal_snapshots
from backend.app.services.price_service import get_asset_prices_by_name, get_top_movers, get_top_value_assets

settings = get_settings()
st.set_page_config(page_title="Flashcard Planet", layout="wide")


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_decimal(value: object | None, *, suffix: str = "") -> str:
    if value in (None, ""):
        return "N/A"
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}{suffix}"


def _format_integer(value: object | None) -> str:
    if value in (None, ""):
        return "N/A"
    return f"{int(value)}"


def _format_price(value: object | None, currency: str | None = "USD") -> str:
    if value in (None, ""):
        return "N/A"
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))} {currency or 'USD'}"


def _format_timestamp(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    elif isinstance(value, datetime):
        parsed = value
    else:
        return str(value)

    parsed = _to_utc(parsed)
    if parsed is None:
        return "N/A"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def _format_relative_days(days_since_last_sale: int | None) -> str:
    if days_since_last_sale is None:
        return "No recent real observation"
    if days_since_last_sale == 0:
        return "Today"
    if days_since_last_sale == 1:
        return "1 day ago"
    return f"{days_since_last_sale} days ago"


def _badge(label: str | None, *, tone: str = "neutral") -> str:
    if not label:
        return "N/A"
    colors = {
        "positive": ("#0b6e4f", "#d7f5eb"),
        "warning": ("#8b5e00", "#fff3cd"),
        "danger": ("#8f1d21", "#fde2e4"),
        "neutral": ("#355070", "#e6eef8"),
    }
    foreground, background = colors.get(tone, colors["neutral"])
    return (
        f"<span style='display:inline-block;padding:0.2rem 0.6rem;border-radius:999px;"
        f"background:{background};color:{foreground};font-size:0.85rem;font-weight:600;'>{label}</span>"
    )


def _label_tone(label: str | None) -> str:
    if label is None:
        return "neutral"
    lowered = label.lower()
    if lowered.startswith("high"):
        return "positive"
    if lowered.startswith("medium"):
        return "warning"
    if lowered.startswith("low"):
        return "danger"
    return "neutral"


def _load_history_rows(session, asset_id, *, limit: int = 10) -> list[dict[str, object]]:
    source_filter = get_active_price_source_filter(session)
    rows = session.execute(
        select(
            PriceHistory.captured_at,
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.source,
        )
        .where(
            PriceHistory.asset_id == asset_id,
            source_filter,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(limit)
    ).all()

    # Current market rows are provider snapshots, so they are presented as derived points
    # until the schema can distinguish sales, listings, and other event types explicitly.
    return [
        {
            "Timestamp": _format_timestamp(row.captured_at),
            "Price": _format_price(row.price, row.currency),
            "Source": row.source,
            "Point Type": "derived",
            "Event Type": "derived",
            "Is Real Data": row.source != SAMPLE_PRICE_SOURCE,
        }
        for row in rows
    ]


def _load_latest_price_rows(session, asset_ids: list[object]) -> dict[object, dict[str, object]]:
    if not asset_ids:
        return {}

    source_filter = get_active_price_source_filter(session)
    ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.captured_at,
            func.row_number()
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.desc())
            .label("price_rank"),
        )
        .where(
            source_filter,
            PriceHistory.asset_id.in_(asset_ids),
        )
        .subquery()
    )
    rows = session.execute(
        select(
            ranked.c.asset_id,
            ranked.c.price,
            ranked.c.currency,
            ranked.c.captured_at,
        )
        .where(ranked.c.price_rank == 1)
    ).all()
    return {
        row.asset_id: {
            "latest_price": row.price,
            "currency": row.currency,
            "captured_at": row.captured_at,
        }
        for row in rows
    }


def _load_monitoring_preview(session, *, limit: int = 8) -> tuple[str, list[dict[str, object]]]:
    watchlist_rows = session.execute(
        select(
            Watchlist.asset_id,
            Watchlist.created_at,
            Asset.name,
            Asset.set_name,
        )
        .join(Asset, Asset.id == Watchlist.asset_id)
        .order_by(Watchlist.created_at.desc())
        .limit(limit)
    ).all()

    if watchlist_rows:
        asset_ids = [row.asset_id for row in watchlist_rows]
        latest_by_asset = _load_latest_price_rows(session, asset_ids)
        signal_snapshots = get_asset_signal_snapshots(session, asset_ids)
        rows = []
        for row in watchlist_rows:
            latest = latest_by_asset.get(row.asset_id, {})
            signal = signal_snapshots.get(row.asset_id)
            rows.append(
                {
                    "Asset": row.name,
                    "Set": row.set_name or "N/A",
                    "Latest Price": _format_price(latest.get("latest_price"), latest.get("currency")),
                    "Liquidity": (
                        f"{signal.liquidity_label} ({signal.liquidity_score}/100)"
                        if signal is not None
                        else "N/A"
                    ),
                    "Last Real": _format_relative_days(
                        signal.days_since_last_sale if signal is not None else None
                    ),
                    "Added": _format_timestamp(row.created_at),
                }
            )
        return ("Active watchlist preview", rows)

    placeholder_rows = []
    for item in get_top_value_assets(session, limit=limit):
        placeholder_rows.append(
            {
                "Asset": item.name,
                "Set": item.set_name or "N/A",
                "Latest Price": _format_price(item.latest_price, item.currency),
                "Liquidity": "Use /watchlist to pin this card",
                "Last Real": _format_timestamp(item.captured_at),
                "Added": "Placeholder monitoring set",
            }
        )
    return ("No saved watchlist yet. Showing top-value cards as a monitoring placeholder.", placeholder_rows)


def _render_header(snapshot: dict[str, object]) -> None:
    title_col, action_col = st.columns([6, 1])
    with title_col:
        st.title("Flashcard Planet")
        st.caption("Card Data, Signals, and Monitoring")
        st.caption(
            f"Environment: {settings.environment} | Source: {snapshot['provider']['label']} | "
            f"Snapshot: {_format_timestamp(snapshot['generated_at'])}"
        )
    with action_col:
        st.write("")
        st.write("")
        if st.button("Refresh", use_container_width=True):
            st.rerun()


def _render_metric_row(snapshot: dict[str, object]) -> None:
    health = snapshot["health"]
    provider = snapshot["provider"]
    metric_columns = st.columns(5)
    metric_columns[0].metric("Tracked Assets", _format_integer(health["total_assets"]))
    metric_columns[1].metric("Assets With Real History", _format_integer(health["assets_with_real_history"]))
    metric_columns[2].metric("Avg History Depth", str(health["average_real_history_points_per_asset"]))
    metric_columns[3].metric("Changed Assets (24h)", _format_integer(health["assets_with_price_change_last_24h"]))
    metric_columns[4].metric("Changed Assets (7d)", _format_integer(health["assets_with_price_change_last_7d"]))
    st.caption(
        f"Current provider: {provider['label']} ({provider['source']}) | "
        f"Observation stage: {snapshot['observation_stage']['observations_logged']} logged in the last 24h"
    )


def _render_lookup_panel(session) -> None:
    st.subheader("Search / Lookup")
    st.caption("Search tracked cards and inspect price, liquidity, confidence, and recent history.")
    st.session_state.setdefault("lookup_name", "")
    st.session_state.setdefault("lookup_set_name", "")
    with st.form("lookup-form"):
        query_name = st.text_input(
            "Card name",
            value=st.session_state["lookup_name"],
            placeholder="Umbreon, Pikachu, Charizard",
        )
        query_set = st.text_input(
            "Set name (optional)",
            value=st.session_state["lookup_set_name"],
            placeholder="Prismatic Evolutions",
        )
        submitted = st.form_submit_button("Search", use_container_width=True)

    if submitted:
        st.session_state["lookup_name"] = query_name.strip()
        st.session_state["lookup_set_name"] = query_set.strip()

    persisted_query_name = st.session_state["lookup_name"]
    persisted_query_set = st.session_state["lookup_set_name"]

    if not persisted_query_name:
        st.info("Enter a tracked card name to inspect the current signal layer.")
        return

    results = get_asset_prices_by_name(session, persisted_query_name)
    if persisted_query_set:
        lowered_set = persisted_query_set.lower()
        results = [item for item in results if lowered_set in (item.set_name or "").lower()]

    if not results:
        st.info("No matching asset found.")
        return

    if len(results) > 1:
        selected_index = st.selectbox(
            "Matching assets",
            options=list(range(len(results))),
            format_func=lambda index: (
                f"{results[index].name} | {results[index].set_name or 'Unknown set'} | "
                f"{results[index].variant or 'Default variant'}"
            ),
        )
        selected = results[selected_index]
    else:
        selected = results[0]

    st.markdown(f"#### {selected.name}")
    if selected.set_name:
        st.caption(f"Set: {selected.set_name}")

    info_columns = st.columns(4)
    info_columns[0].metric("Current Price", _format_price(selected.latest_price, selected.currency))
    info_columns[1].metric("Last Real Activity", _format_relative_days(selected.days_since_last_sale))
    info_columns[2].metric("7d Activity", _format_integer(selected.sales_count_7d))
    info_columns[3].metric("30d Activity", _format_integer(selected.sales_count_30d))

    st.markdown(
        f"Liquidity: {_badge(selected.liquidity_label, tone=_label_tone(selected.liquidity_label))} &nbsp;&nbsp; "
        f"Score: {_format_integer(selected.liquidity_score)} &nbsp;&nbsp; "
        f"Sources: {_format_integer(selected.source_count)}",
        unsafe_allow_html=True,
    )
    if selected.alert_confidence is not None:
        st.markdown(
            f"Alert Confidence: {_badge(selected.alert_confidence_label, tone=_label_tone(selected.alert_confidence_label))} "
            f"&nbsp;&nbsp; Score: {_format_integer(selected.alert_confidence)}",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Alert confidence is not available because there is no recent non-zero comparison move for this asset.")

    history_rows = _load_history_rows(session, selected.asset_id, limit=10)
    if history_rows:
        st.dataframe(history_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No recent history available for this asset.")

    if len(results) > 1:
        with st.expander("Other matching assets"):
            st.dataframe(
                [
                    {
                        "Asset": item.name,
                        "Set": item.set_name or "N/A",
                        "Current Price": _format_price(item.latest_price, item.currency),
                        "Liquidity": f"{item.liquidity_label or 'N/A'} ({_format_integer(item.liquidity_score)})",
                        "Last Real": _format_relative_days(item.days_since_last_sale),
                    }
                    for item in results
                ],
                use_container_width=True,
                hide_index=True,
            )


def _render_provider_panel(snapshot: dict[str, object]) -> None:
    st.subheader("Provider / Ingestion Snapshot")
    health = snapshot["health"]
    observation_stage = snapshot["observation_stage"]
    st.write(f"Provider: **{snapshot['provider']['label']}**")
    st.write(f"Active source: `{snapshot['active_price_source']}`")
    st.write(f"Configured providers: **{snapshot['provider']['configured_provider_count']}**")
    st.write(f"Average history depth: **{health['average_real_history_points_per_asset']}**")
    st.write(f"Changed assets (24h): **{health['assets_with_price_change_last_24h']}**")
    st.write(f"Changed assets (7d): **{health['assets_with_price_change_last_7d']}**")
    st.write(f"Observation logs (24h): **{observation_stage['observations_logged']}**")
    st.write(f"Requires review (24h): **{observation_stage['observations_require_review']}**")
    if snapshot["smart_pool"]["comparison_lines"]:
        with st.expander("Smart pool note", expanded=False):
            st.write(snapshot["smart_pool"]["headline"])
            st.write(snapshot["smart_pool"]["summary"])
            for line in snapshot["smart_pool"]["comparison_lines"]:
                st.write(f"- {line}")


def _render_top_movers(session) -> None:
    st.subheader("Top Movers")
    st.caption("Main movers only. Illiquid assets are excluded from this ranking.")
    movers = get_top_movers(session, limit=20)
    if not movers:
        st.info("No data available. The current mover list is empty after applying liquidity eligibility rules.")
        return

    table_rows = [
        {
            "Asset": item.name,
            "Set": item.set_name or "N/A",
            "Current Price": _format_price(item.latest_price),
            "Percent Change": f"{item.percent_change:+.2f}%",
            "Liquidity Score": item.liquidity_score,
            "Liquidity Label": item.liquidity_label,
            "Alert Confidence": item.alert_confidence,
            "Confidence Label": item.alert_confidence_label,
            "7d Sales": item.sales_count_7d,
            "30d Sales": item.sales_count_30d,
            "Days Since Last Real": item.days_since_last_sale,
        }
        for item in movers
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def _render_monitoring_preview(session) -> None:
    st.subheader("Watchlist / Monitoring Preview")
    note, rows = _load_monitoring_preview(session, limit=8)
    st.caption(note)
    if not rows:
        st.info("No data available.")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    with SessionLocal() as session:
        snapshot = build_standardized_diagnostics_summary(session)
        _render_header(snapshot)
        _render_metric_row(snapshot)

        left_col, right_col = st.columns([2, 1])
        with left_col:
            _render_lookup_panel(session)
        with right_col:
            _render_provider_panel(snapshot)

        st.divider()
        _render_top_movers(session)

        st.divider()
        _render_monitoring_preview(session)


if __name__ == "__main__":
    main()
