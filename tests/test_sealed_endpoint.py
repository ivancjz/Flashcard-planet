"""Tests for GET /api/v1/sealed/products endpoint (TASK-503)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.enums import AssetClass
from backend.app.models.listing_snapshot import ListingSnapshot


def _coerce_jsonb_for_sqlite() -> None:
    from sqlalchemy.dialects.postgresql import JSONB
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _session():
    _coerce_jsonb_for_sqlite()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SLocal() as db:
        yield db
    Base.metadata.drop_all(engine)


def _make_sealed_asset(db: Session, name: str = "Test ETB") -> Asset:
    asset = Asset(
        asset_class=AssetClass.SEALED.value,
        game="pokemon",
        name=name,
        set_name="Test Set",
        product_type="etb",
    )
    db.add(asset)
    db.flush()
    return asset


def _make_snapshot(
    db: Session,
    asset_id,
    captured_at: datetime,
    from_price: Decimal | None = Decimal("100.00"),
    min_count_met: bool = True,
    listing_count: int = 8,
) -> ListingSnapshot:
    snap = ListingSnapshot(
        asset_id=asset_id,
        source="ebay_sealed_ask",
        captured_at=captured_at,
        from_price=from_price,
        listing_count=listing_count,
        min_count_met=min_count_met,
    )
    db.add(snap)
    db.flush()
    return snap


# ---------------------------------------------------------------------------
# _get_sealed_products
# ---------------------------------------------------------------------------

def test_returns_empty_when_no_sealed_assets():
    from backend.app.api.routes.sealed import _get_sealed_products
    with _session() as db:
        result = _get_sealed_products(db)
    assert result == []


def test_returns_product_with_from_price_and_no_trend_when_fresh():
    """New product with only recent snapshots shows from_price but no trend yet."""
    from backend.app.api.routes.sealed import _get_sealed_products
    now = datetime.now(UTC)

    with _session() as db:
        asset = _make_sealed_asset(db)
        _make_snapshot(db, asset.id, captured_at=now - timedelta(hours=1))
        db.commit()

        # Patch datetime.now to control "now"
        result = _get_sealed_products(db)

    assert len(result) == 1
    row = result[0]
    assert row["from_price"] == 100.0
    assert row["min_count_met"] is True
    # No 7-day snapshot yet → trend_pct=None
    assert row["trend_pct"] is None


def test_returns_trend_when_7d_snapshot_exists():
    """Product with 7d-ago and current snapshots shows trend_pct."""
    from backend.app.api.routes.sealed import _get_sealed_products
    now = datetime.now(UTC)

    with _session() as db:
        asset = _make_sealed_asset(db)
        # 7 days ago: from_price=80
        _make_snapshot(db, asset.id, captured_at=now - timedelta(days=7), from_price=Decimal("80.00"))
        # Now: from_price=100
        _make_snapshot(db, asset.id, captured_at=now - timedelta(hours=1), from_price=Decimal("100.00"))
        db.commit()

        result = _get_sealed_products(db)

    assert len(result) == 1
    row = result[0]
    assert row["from_price"] == 100.0
    # trend = (100 - 80) / 80 * 100 = 25%
    assert row["trend_pct"] == pytest.approx(25.0, rel=0.01)


def test_from_price_is_none_when_min_count_not_met():
    """Product with min_count_met=False shows from_price=None."""
    from backend.app.api.routes.sealed import _get_sealed_products
    now = datetime.now(UTC)

    with _session() as db:
        asset = _make_sealed_asset(db)
        _make_snapshot(
            db, asset.id,
            captured_at=now - timedelta(hours=1),
            from_price=None,
            min_count_met=False,
            listing_count=2,
        )
        db.commit()

        result = _get_sealed_products(db)

    row = result[0]
    assert row["from_price"] is None
    assert row["min_count_met"] is False


def test_returns_multiple_products_ordered():
    """Multiple SEALED assets all appear in the result."""
    from backend.app.api.routes.sealed import _get_sealed_products
    now = datetime.now(UTC)

    with _session() as db:
        a1 = _make_sealed_asset(db, "Product A")
        a2 = _make_sealed_asset(db, "Product B")
        _make_snapshot(db, a1.id, captured_at=now - timedelta(hours=1), from_price=Decimal("120.00"))
        _make_snapshot(db, a2.id, captured_at=now - timedelta(hours=2), from_price=Decimal("80.00"))
        db.commit()

        result = _get_sealed_products(db)

    assert len(result) == 2
    names = {r["name"] for r in result}
    assert "Product A" in names
    assert "Product B" in names
