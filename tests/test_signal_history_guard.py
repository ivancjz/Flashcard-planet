"""
tests/test_signal_history_guard.py

Tests for the transition guard in _append_history (Issue D fix).

The guard in _append_history prevents writing when label == previous_label.
Tests cover the four specified scenarios:
  1. First-time write (previous_label=None) — guard passes
  2. Label change (BREAKOUT→IDLE) — guard passes
  3. Label repeat (BREAKOUT→BREAKOUT) — guard blocks
  4. End-to-end: 3 assets with mixed sequences; alert query returns only
     true transitions, not repeats
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import JSON, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models
from backend.app.db.base import Base
from backend.app.models.asset_signal_history import AssetSignalHistory
from backend.app.services.signal_service import SignalRow, _append_history
from backend.app.models.enums import SignalLabel


# ── SQLite in-memory setup ──────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _db():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)


def _signal(asset_id: uuid.UUID, label: SignalLabel, t: datetime) -> SignalRow:
    return SignalRow(
        asset_id=asset_id,
        label=label,
        confidence=70,
        price_delta_pct=Decimal("5.0"),
        liquidity_score=50,
        prediction=None,
        computed_at=t,
        signal_context={},
    )


# ── Unit tests: guard logic ─────────────────────────────────────────────────

def test_first_write_proceeds_when_prev_label_none():
    """Guard must pass when previous_label is None (first-ever write for asset)."""
    asset_id = uuid.uuid4()
    now = datetime.now(UTC)

    with _db() as db:
        _append_history(db, signal=_signal(asset_id, SignalLabel.INSUFFICIENT_DATA, now), previous_label=None)
        db.flush()
        count = db.query(AssetSignalHistory).filter_by(asset_id=asset_id).count()

    assert count == 1, "First-time write (prev=None) must write exactly 1 row"


def test_label_change_writes_row():
    """Guard must pass when label changes (BREAKOUT → IDLE)."""
    asset_id = uuid.uuid4()
    now = datetime.now(UTC)

    with _db() as db:
        _append_history(db, signal=_signal(asset_id, SignalLabel.IDLE, now), previous_label="BREAKOUT")
        db.flush()
        count = db.query(AssetSignalHistory).filter_by(asset_id=asset_id).count()

    assert count == 1, "Label change (BREAKOUT→IDLE) must write 1 row"


def test_label_repeat_skips_write():
    """Guard must block when label is unchanged (BREAKOUT → BREAKOUT)."""
    asset_id = uuid.uuid4()
    now = datetime.now(UTC)

    with _db() as db:
        _append_history(db, signal=_signal(asset_id, SignalLabel.BREAKOUT, now), previous_label="BREAKOUT")
        db.flush()
        count = db.query(AssetSignalHistory).filter_by(asset_id=asset_id).count()

    assert count == 0, "Label repeat (BREAKOUT→BREAKOUT) must write 0 rows"


def test_alert_query_returns_only_transitions():
    """End-to-end: 3 assets, mixed sequences.

    Asset A: None→INSUFFICIENT_DATA→INSUFFICIENT_DATA→BREAKOUT
      Written rows: 2 (first write + transition to BREAKOUT)
      Alert-visible rows: 1 (only INSUFFICIENT_DATA→BREAKOUT has prev≠label)

    Asset B: None→BREAKOUT→BREAKOUT→BREAKOUT
      Written rows: 1 (first write only)
      Alert-visible rows: 0 (no transition)

    Asset C: None→IDLE→MOVE
      Written rows: 2 (first write + IDLE→MOVE transition)
      Alert-visible rows: 1 (IDLE→MOVE)

    Total rows in table: 5
    Alert query (prev IS NOT NULL AND label IS DISTINCT FROM prev): 2 rows (A and C transitions)
    """
    a = uuid.uuid4()
    b = uuid.uuid4()
    c = uuid.uuid4()
    t = datetime.now(UTC)

    with _db() as db:
        # Asset A sequence
        _append_history(db, signal=_signal(a, SignalLabel.INSUFFICIENT_DATA, t), previous_label=None)
        _append_history(db, signal=_signal(a, SignalLabel.INSUFFICIENT_DATA, t + timedelta(minutes=15)), previous_label="INSUFFICIENT_DATA")
        _append_history(db, signal=_signal(a, SignalLabel.BREAKOUT, t + timedelta(minutes=30)), previous_label="INSUFFICIENT_DATA")

        # Asset B sequence
        _append_history(db, signal=_signal(b, SignalLabel.BREAKOUT, t), previous_label=None)
        _append_history(db, signal=_signal(b, SignalLabel.BREAKOUT, t + timedelta(minutes=15)), previous_label="BREAKOUT")
        _append_history(db, signal=_signal(b, SignalLabel.BREAKOUT, t + timedelta(minutes=30)), previous_label="BREAKOUT")

        # Asset C sequence
        _append_history(db, signal=_signal(c, SignalLabel.IDLE, t), previous_label=None)
        _append_history(db, signal=_signal(c, SignalLabel.MOVE, t + timedelta(minutes=15)), previous_label="IDLE")

        db.flush()

        total_rows = db.query(AssetSignalHistory).count()
        alert_rows = db.execute(text("""
            SELECT COUNT(*) FROM asset_signal_history
            WHERE previous_label IS NOT NULL
              AND label != previous_label
        """)).scalar()

    assert total_rows == 5, f"Expected 5 rows written (guard blocked 3 repeats), got {total_rows}"
    assert alert_rows == 2, f"Expected 2 alert-visible transitions (A and C), got {alert_rows}"
