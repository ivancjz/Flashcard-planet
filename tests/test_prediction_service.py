"""Unit tests for prediction_service. All tests are pure Python — no DB session needed.
DB-interaction functions are tested by inspecting what they write, using a MagicMock Session.
Math helpers (brier_score, wilson_ci, calibration_metrics) are pure functions tested directly.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.app.services.prediction_service import (
    CalibrationMetrics,
    PredictionResolution,
    ReliabilityBin,
    _brier_score,
    _build_reliability_bins,
    _evaluate_threshold,
    _wilson_ci,
    create_prediction,
    get_calibration_metrics,
    resolve_prediction,
)


def _asset_id() -> uuid.UUID:
    return uuid.uuid4()


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=30)


# ── create_prediction ──────────────────────────────────────────────────────

class TestCreatePrediction:
    def test_returns_uuid(self):
        db = MagicMock()
        result = create_prediction(
            db=db,
            asset_id=_asset_id(),
            prediction_text="Charizard ex SIR will exceed $80 by June 30",
            threshold_value=Decimal("80.00"),
            threshold_direction="above",
            stated_probability=Decimal("0.65"),
            resolution_date=_future(),
            methodology_version="v0.1-abc1234",
        )
        assert isinstance(result, uuid.UUID)

    def test_writes_prediction_row(self):
        db = MagicMock()
        asset_id = _asset_id()
        create_prediction(
            db=db,
            asset_id=asset_id,
            prediction_text="Test call",
            threshold_value=Decimal("10.00"),
            threshold_direction="above",
            stated_probability=Decimal("0.50"),
            resolution_date=_future(),
            methodology_version="v0.1-abc1234",
        )
        db.add.assert_called()
        added = db.add.call_args_list[0][0][0]
        from backend.app.models.predictions import Prediction
        assert isinstance(added, Prediction)
        assert added.asset_id == asset_id
        assert added.is_paper is True
        assert added.resolution_status == "PENDING"

    def test_paper_flag_defaults_true(self):
        db = MagicMock()
        create_prediction(
            db=db, asset_id=_asset_id(), prediction_text="Test",
            threshold_value=Decimal("1.00"), threshold_direction="above",
            stated_probability=Decimal("0.50"), resolution_date=_future(),
            methodology_version="v0.1",
        )
        added = db.add.call_args_list[0][0][0]
        assert added.is_paper is True

    def test_paper_flag_can_be_false(self):
        db = MagicMock()
        create_prediction(
            db=db, asset_id=_asset_id(), prediction_text="Public call",
            threshold_value=Decimal("1.00"), threshold_direction="above",
            stated_probability=Decimal("0.50"), resolution_date=_future(),
            methodology_version="v0.1", is_paper=False,
        )
        added = db.add.call_args_list[0][0][0]
        assert added.is_paper is False

    def test_rejects_invalid_threshold_direction(self):
        db = MagicMock()
        with pytest.raises(ValueError, match="threshold_direction"):
            create_prediction(
                db=db, asset_id=_asset_id(), prediction_text="Test",
                threshold_value=Decimal("1.00"), threshold_direction="sideways",
                stated_probability=Decimal("0.50"), resolution_date=_future(),
                methodology_version="v0.1",
            )

    def test_rejects_probability_above_1(self):
        db = MagicMock()
        with pytest.raises(ValueError, match="stated_probability"):
            create_prediction(
                db=db, asset_id=_asset_id(), prediction_text="Test",
                threshold_value=Decimal("1.00"), threshold_direction="above",
                stated_probability=Decimal("1.5"), resolution_date=_future(),
                methodology_version="v0.1",
            )

    def test_rejects_probability_below_0(self):
        db = MagicMock()
        with pytest.raises(ValueError, match="stated_probability"):
            create_prediction(
                db=db, asset_id=_asset_id(), prediction_text="Test",
                threshold_value=Decimal("1.00"), threshold_direction="above",
                stated_probability=Decimal("-0.1"), resolution_date=_future(),
                methodology_version="v0.1",
            )

    def test_within_band_requires_band_high(self):
        db = MagicMock()
        with pytest.raises(ValueError, match="threshold_band_high"):
            create_prediction(
                db=db, asset_id=_asset_id(), prediction_text="Test",
                threshold_value=Decimal("10.00"), threshold_direction="within_band",
                threshold_band_high=None,
                stated_probability=Decimal("0.50"), resolution_date=_future(),
                methodology_version="v0.1",
            )

    def test_within_band_with_band_high_succeeds(self):
        db = MagicMock()
        result = create_prediction(
            db=db, asset_id=_asset_id(), prediction_text="Test",
            threshold_value=Decimal("10.00"), threshold_direction="within_band",
            threshold_band_high=Decimal("20.00"),
            stated_probability=Decimal("0.50"), resolution_date=_future(),
            methodology_version="v0.1",
        )
        assert isinstance(result, uuid.UUID)

    def test_writes_audit_row_on_insert(self):
        db = MagicMock()
        create_prediction(
            db=db, asset_id=_asset_id(), prediction_text="Test",
            threshold_value=Decimal("1.00"), threshold_direction="above",
            stated_probability=Decimal("0.50"), resolution_date=_future(),
            methodology_version="v0.1",
        )
        assert db.add.call_count == 2
        from backend.app.models.predictions import PredictionAudit
        audit = db.add.call_args_list[1][0][0]
        assert isinstance(audit, PredictionAudit)
        assert audit.action == "INSERT"


# ── _evaluate_threshold ────────────────────────────────────────────────────

class TestEvaluateThreshold:
    def test_above_hit(self):
        assert _evaluate_threshold(
            actual_value=Decimal("95"), threshold_value=Decimal("80"),
            threshold_direction="above", threshold_band_high=None,
        ) == "HIT"

    def test_above_exact_is_hit(self):
        assert _evaluate_threshold(
            actual_value=Decimal("80"), threshold_value=Decimal("80"),
            threshold_direction="above", threshold_band_high=None,
        ) == "HIT"

    def test_above_miss(self):
        assert _evaluate_threshold(
            actual_value=Decimal("70"), threshold_value=Decimal("80"),
            threshold_direction="above", threshold_band_high=None,
        ) == "MISS"

    def test_below_hit(self):
        assert _evaluate_threshold(
            actual_value=Decimal("40"), threshold_value=Decimal("50"),
            threshold_direction="below", threshold_band_high=None,
        ) == "HIT"

    def test_below_exact_is_hit(self):
        assert _evaluate_threshold(
            actual_value=Decimal("50"), threshold_value=Decimal("50"),
            threshold_direction="below", threshold_band_high=None,
        ) == "HIT"

    def test_below_miss(self):
        assert _evaluate_threshold(
            actual_value=Decimal("60"), threshold_value=Decimal("50"),
            threshold_direction="below", threshold_band_high=None,
        ) == "MISS"

    def test_within_band_hit(self):
        assert _evaluate_threshold(
            actual_value=Decimal("15"), threshold_value=Decimal("10"),
            threshold_direction="within_band", threshold_band_high=Decimal("20"),
        ) == "HIT"

    def test_within_band_miss_above(self):
        assert _evaluate_threshold(
            actual_value=Decimal("25"), threshold_value=Decimal("10"),
            threshold_direction="within_band", threshold_band_high=Decimal("20"),
        ) == "MISS"

    def test_within_band_miss_below(self):
        assert _evaluate_threshold(
            actual_value=Decimal("5"), threshold_value=Decimal("10"),
            threshold_direction="within_band", threshold_band_high=Decimal("20"),
        ) == "MISS"


# ── resolve_prediction ─────────────────────────────────────────────────────

class TestResolvePrediction:
    def _pending(
        self,
        direction: str = "above",
        threshold: Decimal = Decimal("80.00"),
        band_high: Decimal | None = None,
    ):
        from backend.app.models.predictions import Prediction
        p = Prediction()
        p.id = uuid.uuid4()
        p.resolution_status = "PENDING"
        p.threshold_direction = direction
        p.threshold_value = threshold
        p.threshold_band_high = band_high
        return p

    def _db(self, prediction):
        db = MagicMock()
        db.scalars.return_value.first.return_value = prediction
        return db

    def test_hit_above(self):
        db = self._db(self._pending("above", Decimal("80")))
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("95"))
        assert result.resolution_status == "HIT"

    def test_miss_above(self):
        db = self._db(self._pending("above", Decimal("80")))
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("70"))
        assert result.resolution_status == "MISS"

    def test_hit_below(self):
        db = self._db(self._pending("below", Decimal("50")))
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("40"))
        assert result.resolution_status == "HIT"

    def test_miss_below(self):
        db = self._db(self._pending("below", Decimal("50")))
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("60"))
        assert result.resolution_status == "MISS"

    def test_hit_within_band(self):
        db = self._db(self._pending("within_band", Decimal("10"), Decimal("20")))
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("15"))
        assert result.resolution_status == "HIT"

    def test_miss_outside_band(self):
        db = self._db(self._pending("within_band", Decimal("10"), Decimal("20")))
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("25"))
        assert result.resolution_status == "MISS"

    def test_not_found_raises(self):
        db = MagicMock()
        db.scalars.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("1"))

    def test_already_resolved_raises(self):
        from backend.app.models.predictions import Prediction
        p = Prediction()
        p.id = uuid.uuid4()
        p.resolution_status = "HIT"
        db = self._db(p)
        with pytest.raises(ValueError, match="already resolved"):
            resolve_prediction(db=db, prediction_id=p.id, actual_value=Decimal("1"))

    def test_writes_audit_row(self):
        db = self._db(self._pending())
        resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("95"))
        from backend.app.models.predictions import PredictionAudit
        assert db.add.called
        audit = db.add.call_args[0][0]
        assert isinstance(audit, PredictionAudit)
        assert audit.action == "RESOLVE"

    def test_returns_resolution_object(self):
        db = self._db(self._pending())
        result = resolve_prediction(db=db, prediction_id=uuid.uuid4(), actual_value=Decimal("95"))
        assert isinstance(result, PredictionResolution)
        assert result.actual_value == Decimal("95")


# ── _brier_score ───────────────────────────────────────────────────────────

class TestBrierScore:
    def test_empty_returns_none(self):
        assert _brier_score([]) is None

    def test_perfect_calibration(self):
        assert _brier_score([(1.0, 1), (1.0, 1)]) == pytest.approx(0.0)

    def test_worst_calibration(self):
        assert _brier_score([(1.0, 0)]) == pytest.approx(1.0)

    def test_baseline_calibration(self):
        pairs = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
        assert _brier_score(pairs) == pytest.approx(0.25)

    def test_single_hit(self):
        assert _brier_score([(0.8, 1)]) == pytest.approx((0.8 - 1.0) ** 2)


# ── _wilson_ci ─────────────────────────────────────────────────────────────

class TestWilsonCI:
    def test_n_zero_full_range(self):
        lo, hi = _wilson_ci(0, 0)
        assert lo == pytest.approx(0.0)
        assert hi == pytest.approx(1.0)

    def test_bounds_within_0_1(self):
        lo, hi = _wilson_ci(5, 10)
        assert 0.0 <= lo <= hi <= 1.0

    def test_all_hits_near_1(self):
        lo, hi = _wilson_ci(100, 100)
        assert lo > 0.9

    def test_ci_contains_true_rate(self):
        lo, hi = _wilson_ci(3, 5)
        assert lo < 0.6 < hi


# ── _build_reliability_bins ────────────────────────────────────────────────

class TestReliabilityBins:
    def test_10_bins_returned(self):
        bins = _build_reliability_bins([])
        assert len(bins) == 10

    def test_bins_cover_0_to_1(self):
        bins = _build_reliability_bins([])
        assert bins[0].prob_bin_low == pytest.approx(0.0)
        assert bins[-1].prob_bin_high == pytest.approx(1.0)

    def test_prediction_in_correct_bin(self):
        bins = _build_reliability_bins([(0.75, 1)])
        assert bins[7].n == 1
        assert bins[7].hit_rate == pytest.approx(1.0)

    def test_probability_1_in_last_bin(self):
        bins = _build_reliability_bins([(1.0, 1)])
        assert bins[9].n == 1


# ── get_calibration_metrics ────────────────────────────────────────────────

class TestCalibrationMetrics:
    def _db(self, rows):
        db = MagicMock()
        db.scalars.return_value.all.return_value = rows
        db.scalar.return_value = len(rows)
        return db

    def test_empty_brier_is_none(self):
        metrics = get_calibration_metrics(self._db([]))
        assert metrics.brier_score is None
        assert metrics.total_resolved == 0

    def test_10_reliability_bins(self):
        metrics = get_calibration_metrics(self._db([]))
        assert len(metrics.reliability_bins) == 10

    def test_brier_computed(self):
        from backend.app.models.predictions import Prediction
        p = Prediction()
        p.stated_probability = Decimal("0.8")
        p.resolution_status = "HIT"
        p.is_paper = False
        metrics = get_calibration_metrics(self._db([p]))
        assert metrics.brier_score == pytest.approx((0.8 - 1.0) ** 2)
