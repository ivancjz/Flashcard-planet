from __future__ import annotations

from sqlalchemy import func, select

from backend.app.models.price_history import PriceHistory


def build_ranked_price_subquery(source_filter):
    """Build a subquery ranking PriceHistory rows by captured_at desc per asset."""
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
