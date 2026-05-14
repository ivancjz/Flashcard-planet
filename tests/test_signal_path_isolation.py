"""Regression tests: standard path and CardMarket path must be mutually exclusive.

These tests verify the isolation guarantee added in Task 7:
- Standard path (_compute_delta_batch) must never include EUR-denominated
  CardMarket rows (CM_ALL_SOURCES) in its baseline or current buckets.
- CardMarket path (compute_cardmarket_delta) must use only CardMarket rows,
  not pokemon_tcg_api or other standard-path sources.
"""
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.services.signal_service import (
    CM_ALL_SOURCES,
    _compute_delta_batch,
    compute_cardmarket_delta,
)


def _coerce():
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@contextmanager
def _db():
    _coerce()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def _make_asset(session, game="pokemon"):
    asset = Asset(
        id=uuid.uuid4(),
        asset_class="tcg",
        category=game,
        game=game,
        name="Test Card",
        set_name="TEST",
        card_number="001",
        language="EN",
        variant="holo",
        external_id=f"test-{uuid.uuid4()}",
        metadata_json={},
    )
    session.add(asset)
    session.commit()
    return asset


def _add_row(session, asset_id, source, price, captured_at, currency="USD"):
    row = PriceHistory(
        id=uuid.uuid4(),
        asset_id=asset_id,
        source=source,
        currency=currency,
        price=Decimal(str(price)),
        captured_at=captured_at,
        market_segment="raw",
    )
    session.add(row)
    session.commit()
    return row


def test_cm_all_sources_covers_all_four():
    """CM_ALL_SOURCES must contain all four CardMarket source strings."""
    assert "cardmarket_avg1" in CM_ALL_SOURCES
    assert "cardmarket_avg7" in CM_ALL_SOURCES
    assert "cardmarket_avg30" in CM_ALL_SOURCES
    assert "cardmarket_trend" in CM_ALL_SOURCES


def test_standard_path_excludes_cardmarket_sources():
    """An asset with both pokemon_tcg_api (baseline) and cardmarket_avg7 (current)
    rows must NOT have the cardmarket_avg7 row included in the standard path's
    current bucket.

    Setup: baseline row >7 days ago (pokemon_tcg_api), current-window row
    (cardmarket_avg7). Standard path must see baseline_n=1, current_n=0 (the CM
    row is excluded), returning no_current_data — not a delta from the CM price.
    """
    now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
    baseline_ts = now - timedelta(days=10)   # before baseline cutoff (7d)
    current_ts = now - timedelta(hours=1)    # inside current window (24h)

    with _db() as db:
        asset = _make_asset(db)

        # Standard-path baseline row (old, USD)
        _add_row(db, asset.id, "pokemon_tcg_api", "10.00", baseline_ts, currency="USD")

        # CardMarket current-window row (EUR) — must be excluded from standard path
        _add_row(db, asset.id, "cardmarket_avg7", "11.00", current_ts, currency="EUR")

        result = _compute_delta_batch(
            db,
            [asset.id],
            baseline_window_days=7,
            current_window_hours=24,
            source_weights={"pokemon_tcg_api": 1.0},
            now=now,
        )

    delta, ctx = result[asset.id]
    # Standard path sees 1 baseline row (pokemon) and 0 current rows (CM excluded)
    assert ctx["baseline_n"] == 1, f"Expected baseline_n=1, got {ctx['baseline_n']}"
    assert ctx["current_n"] == 0, (
        f"Expected current_n=0 (CM row excluded), got {ctx['current_n']}. "
        "CardMarket source leaked into standard path current bucket."
    )
    assert delta is None
    assert ctx.get("reason") == "no_current_data"


def test_standard_path_excludes_all_cm_source_variants():
    """Each CardMarket source variant must be excluded from the standard path
    baseline bucket when inserted as a baseline-age row.
    """
    now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
    baseline_ts = now - timedelta(days=10)

    cm_sources = list(CM_ALL_SOURCES)

    for cm_source in cm_sources:
        with _db() as db:
            asset = _make_asset(db)

            # Insert only a CM row at baseline age — standard path must see nothing
            _add_row(db, asset.id, cm_source, "10.00", baseline_ts, currency="EUR")

            result = _compute_delta_batch(
                db,
                [asset.id],
                baseline_window_days=7,
                current_window_hours=24,
                source_weights={"pokemon_tcg_api": 1.0},
                now=now,
            )

        delta, ctx = result[asset.id]
        assert ctx["baseline_n"] == 0, (
            f"Source '{cm_source}' leaked into standard path baseline bucket. "
            f"Expected baseline_n=0, got {ctx['baseline_n']}."
        )


def test_cardmarket_path_excludes_standard_sources():
    """compute_cardmarket_delta for an asset with both pokemon_tcg_api and
    cardmarket_avg7 + cardmarket_avg30 rows must use only the CM rows.

    If pokemon_tcg_api bled into the CM path, the avg7 and avg30 values would be
    mixed with USD prices, producing a wrong delta. We verify: (a) no crash,
    (b) delta is not None (CM rows are sufficient), (c) delta matches the ratio
    of avg7/avg30 derived from CM prices only.
    """
    now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)

    with _db() as db:
        asset = _make_asset(db, game="yugioh")

        # CM rows
        _add_row(db, asset.id, "cardmarket_avg7", "11.00", now, currency="EUR")
        _add_row(db, asset.id, "cardmarket_avg30", "10.00", now, currency="EUR")

        # Standard-path row — must be invisible to compute_cardmarket_delta
        _add_row(db, asset.id, "pokemon_tcg_api", "999.00", now, currency="USD")

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    # avg7=11, avg30=10 → delta = (11-10)/10 * 100 = 10.0%
    assert delta is not None, f"Expected a delta, got None. ctx={ctx}"
    assert delta == Decimal("10.00"), (
        f"Expected 10.00% (from CM rows only), got {delta}. "
        "pokemon_tcg_api may have contaminated the CM path."
    )
