"""
tests/test_workflow_b.py

Covers:
  B2 — rule_engine_patches: graded filter, variant extractor,
        language detector, confidence penalty, preflight shim
  B3 — backfill_retry_service: record_failure upsert, permanent marking,
        clear on success, queue summary, failure classification
  B4 — card_credibility_service: sample_size, source_breakdown (Pro gate),
        match_confidence (Pro gate), data_age formatting, render helpers

Run with:  pytest tests/test_workflow_b.py -v
"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# B2 — rule_engine_patches
# ─────────────────────────────────────────────────────────────────────────────

from backend.app.ingestion.rule_engine_patches import (
    CardLanguage,
    CardVariant,
    ConfidencePenalty,
    ObservationSkipReason,
    PreflightResult,
    confidence_penalty,
    detect_language,
    extract_grade_info,
    extract_variant,
    is_graded_listing,
    preflight_observation,
)


class TestGradedCardFilter(unittest.TestCase):
    def test_detects_psa(self):
        self.assertTrue(is_graded_listing("Charizard Base Set PSA 10"))

    def test_detects_bgs(self):
        self.assertTrue(is_graded_listing("Pikachu BGS 9.5 Pristine"))

    def test_detects_cgc(self):
        self.assertTrue(is_graded_listing("Mewtwo CGC 8.5 NM/MT"))

    def test_detects_sgc(self):
        self.assertTrue(is_graded_listing("Blastoise SGC 7 Near Mint"))

    def test_detects_beckett(self):
        self.assertTrue(is_graded_listing("Venusaur BECKETT 9"))

    def test_detects_no_space(self):
        self.assertTrue(is_graded_listing("Charizard PSA10"))

    def test_detects_lowercase(self):
        self.assertTrue(is_graded_listing("lugia neo genesis psa 9"))

    def test_does_not_flag_nm_holo(self):
        self.assertFalse(is_graded_listing("Charizard Base Set Holo NM"))

    def test_does_not_flag_first_edition(self):
        self.assertFalse(is_graded_listing("Pikachu 1st Edition"))

    def test_does_not_flag_set_code_sgca(self):
        # "SGCA-001" contains "SGC" but is a set code, not a grader
        self.assertFalse(is_graded_listing("SGCA-001 card"))

    def test_extract_grade_info_psa(self):
        info = extract_grade_info("Charizard PSA 10 Gem Mint")
        self.assertEqual(info, {"grader": "PSA", "grade": 10.0})

    def test_extract_grade_info_bgs_decimal(self):
        info = extract_grade_info("Pikachu BGS 9.5")
        self.assertEqual(info, {"grader": "BGS", "grade": 9.5})

    def test_extract_grade_info_none_when_absent(self):
        self.assertIsNone(extract_grade_info("Charizard NM Holo"))


class TestVariantExtractor(unittest.TestCase):
    def _v(self, title):
        return extract_variant(title).variant

    def test_first_edition(self):
        self.assertEqual(self._v("Charizard 1st Edition Holo"), CardVariant.FIRST_EDITION)

    def test_first_edition_full_word(self):
        self.assertEqual(self._v("Blastoise First Edition Base Set"), CardVariant.FIRST_EDITION)

    def test_shadowless(self):
        self.assertEqual(self._v("Pikachu Shadowless Base Set"), CardVariant.SHADOWLESS)

    def test_reverse_holo(self):
        self.assertEqual(self._v("Mewtwo Reverse Holo"), CardVariant.REVERSE_HOLO)

    def test_rev_holo_abbreviation(self):
        self.assertEqual(self._v("Venusaur Rev Holo NM"), CardVariant.REVERSE_HOLO)

    def test_full_art(self):
        self.assertEqual(self._v("Charizard Full Art Ultra Rare"), CardVariant.FULL_ART)

    def test_secret_rare(self):
        self.assertEqual(self._v("Umbreon Secret Rare Rainbow"), CardVariant.SECRET_RARE)

    def test_promo(self):
        self.assertEqual(self._v("Mewtwo Promo Card"), CardVariant.PROMO)

    def test_holo(self):
        self.assertEqual(self._v("Charizard Holo Rare Base Set"), CardVariant.HOLO)

    def test_unlimited(self):
        self.assertEqual(self._v("Blastoise Unlimited Near Mint"), CardVariant.UNLIMITED)

    def test_base_when_none(self):
        self.assertEqual(self._v("Pikachu Base Set Near Mint"), CardVariant.BASE)

    def test_first_edition_priority_over_holo(self):
        self.assertEqual(self._v("Charizard 1st Edition Holo"), CardVariant.FIRST_EDITION)

    def test_variant_stripped_from_title(self):
        r = extract_variant("Charizard Reverse Holo Base Set NM")
        self.assertNotIn("Reverse Holo", r.title_without_variant)
        self.assertIn("Charizard", r.title_without_variant)

    def test_base_title_unchanged(self):
        title = "Charizard Base Set Near Mint"
        r = extract_variant(title)
        self.assertEqual(r.title_without_variant, title)


class TestLanguageDetector(unittest.TestCase):
    def _lang(self, title):
        return detect_language(title)

    def test_japanese(self):
        self.assertEqual(self._lang("Charizard Japanese Holo"), CardLanguage.JP)

    def test_japan(self):
        self.assertEqual(self._lang("Pikachu Japan NM Base Set"), CardLanguage.JP)

    def test_korean(self):
        self.assertEqual(self._lang("Mewtwo Korean Version NM"), CardLanguage.KR)

    def test_french(self):
        self.assertEqual(self._lang("Blastoise French Near Mint"), CardLanguage.FR)

    def test_german(self):
        self.assertEqual(self._lang("Venusaur German NM"), CardLanguage.DE)

    def test_spanish(self):
        self.assertEqual(self._lang("Charizard Spanish Card"), CardLanguage.ES)

    def test_italian(self):
        self.assertEqual(self._lang("Pikachu Italian NM"), CardLanguage.IT)

    def test_portuguese(self):
        self.assertEqual(self._lang("Mewtwo Portuguese Version"), CardLanguage.PT)

    def test_chinese(self):
        self.assertEqual(self._lang("Charizard Chinese Traditional"), CardLanguage.ZH)

    def test_english_holo(self):
        self.assertEqual(self._lang("Charizard Base Set Holo NM"), CardLanguage.EN)

    def test_english_first_ed(self):
        self.assertEqual(self._lang("Pikachu 1st Edition"), CardLanguage.EN)

    def test_high_non_ascii_jp_fallback(self):
        jp_title = "ポケモン Charizard カード NM"
        self.assertEqual(self._lang(jp_title), CardLanguage.JP)

    def test_low_non_ascii_stays_en(self):
        self.assertEqual(self._lang("Charizard Holo Base Set é"), CardLanguage.EN)


class TestConfidencePenalty(unittest.TestCase):
    def test_lot_penalised(self):
        p = confidence_penalty("Lot of 10 Charizard cards NM", 0.90)
        self.assertGreater(p.amount, 0)
        self.assertIn("lot", p.reason.lower())

    def test_bundle_penalised(self):
        p = confidence_penalty("Bundle 5 Base Set holos", 0.90)
        self.assertGreater(p.amount, 0)

    def test_short_title_penalised(self):
        p = confidence_penalty("Charizard NM", 0.90)
        self.assertGreater(p.amount, 0)
        self.assertIn("short", p.reason.lower())

    def test_no_collector_number_penalised(self):
        p = confidence_penalty("Charizard Base Set Holo Rare Near Mint", 0.90)
        self.assertGreater(p.amount, 0)
        self.assertIn("collector", p.reason.lower())

    def test_collector_number_clears_that_penalty(self):
        p = confidence_penalty("Charizard Base Set 4/102 Holo Rare NM", 0.90)
        self.assertNotIn("collector", p.reason.lower())

    def test_penalty_capped_at_confidence(self):
        p = confidence_penalty("Lot bundle short", 0.10)
        self.assertLessEqual(p.amount, 0.10)

    def test_clean_title_no_penalty(self):
        p = confidence_penalty("Charizard 4/102 Holo Rare Base Set NM", 0.95)
        self.assertEqual(p.amount, 0.0)


class TestPreflightObservation(unittest.TestCase):
    def test_graded_skipped(self):
        r = preflight_observation("Charizard PSA 10 Gem Mint")
        self.assertTrue(r.should_skip)
        self.assertEqual(r.skip_reason, ObservationSkipReason.GRADED_CARD)
        self.assertEqual(r.grade_info, {"grader": "PSA", "grade": 10.0})

    def test_japanese_skipped(self):
        r = preflight_observation("Pikachu Japanese Holo Base Set")
        self.assertTrue(r.should_skip)
        self.assertEqual(r.skip_reason, ObservationSkipReason.NON_ENGLISH)
        self.assertEqual(r.language, CardLanguage.JP)

    def test_english_raw_not_skipped(self):
        r = preflight_observation("Charizard Base Set Holo NM")
        self.assertFalse(r.should_skip)
        self.assertEqual(r.language, CardLanguage.EN)

    def test_variant_annotated_not_skipped(self):
        r = preflight_observation("Charizard 1st Edition Holo NM")
        self.assertFalse(r.should_skip)
        self.assertEqual(r.variant, CardVariant.FIRST_EDITION)
        self.assertNotIn("1st", r.normalised_title.lower())

    def test_graded_check_before_language(self):
        r = preflight_observation("Charizard Japanese PSA 10")
        self.assertEqual(r.skip_reason, ObservationSkipReason.GRADED_CARD)


# ─────────────────────────────────────────────────────────────────────────────
# B3 — backfill_retry_service
# ─────────────────────────────────────────────────────────────────────────────

from backend.app.services.backfill_retry_service import (
    MAX_RETRY_ATTEMPTS,
    FailureType,
    _classify_exception,
    clear_backfill_failure,
    get_queue_summary,
    record_backfill_failure,
)


class TestFailureClassification(unittest.TestCase):
    def _c(self, msg):
        return _classify_exception(Exception(msg))

    def test_timeout(self):
        self.assertEqual(self._c("Connection timed out"), FailureType.API_TIMEOUT)

    def test_read_timeout(self):
        self.assertEqual(self._c("Read timeout after 30s"), FailureType.API_TIMEOUT)

    def test_not_found(self):
        self.assertEqual(self._c("404 not found"), FailureType.NO_RESULT)

    def test_no_result(self):
        self.assertEqual(self._c("No result for card"), FailureType.NO_RESULT)

    def test_image(self):
        self.assertEqual(self._c("image fetch failed"), FailureType.IMAGE_FETCH_FAILED)

    def test_thumbnail(self):
        self.assertEqual(self._c("thumbnail unavailable"), FailureType.IMAGE_FETCH_FAILED)

    def test_price_history(self):
        self.assertEqual(self._c("price_history insert error"), FailureType.PRICE_FETCH_FAILED)

    def test_match_confidence(self):
        self.assertEqual(self._c("match confidence too low"), FailureType.MAPPING_FAILED)

    def test_unknown(self):
        self.assertEqual(self._c("some unknown error xyzzy"), FailureType.UNKNOWN)


class TestRecordBackfillFailure(unittest.TestCase):
    def _make_db(self, existing_row=None):
        db = MagicMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = existing_row
        db.execute.return_value = execute_result
        return db

    def test_creates_new_row(self):
        db = self._make_db(existing_row=None)
        record_backfill_failure(db, uuid.uuid4(), Exception("timeout"))
        db.add.assert_called_once()
        db.flush.assert_called_once()

    def test_increments_existing_row(self):
        existing = MagicMock()
        existing.attempt_count = 1
        existing.is_permanent = False
        db = self._make_db(existing_row=existing)
        record_backfill_failure(db, uuid.uuid4(), Exception("timeout"))
        self.assertEqual(existing.attempt_count, 2)
        db.add.assert_not_called()

    def test_marks_permanent_at_max_attempts(self):
        existing = MagicMock()
        existing.attempt_count = MAX_RETRY_ATTEMPTS - 1
        existing.is_permanent = False
        db = self._make_db(existing_row=existing)
        record_backfill_failure(db, uuid.uuid4(), Exception("timeout"))
        self.assertTrue(existing.is_permanent)

    def test_not_permanent_below_max(self):
        existing = MagicMock()
        existing.attempt_count = 1
        existing.is_permanent = False
        db = self._make_db(existing_row=None)  # new row — count = 1
        record_backfill_failure(db, uuid.uuid4(), Exception("timeout"))
        added = db.add.call_args[0][0]
        self.assertFalse(added.is_permanent)

    def test_explicit_failure_type_used(self):
        db = self._make_db(existing_row=None)
        record_backfill_failure(
            db, uuid.uuid4(), Exception("some error"),
            failure_type=FailureType.IMAGE_FETCH_FAILED,
        )
        added = db.add.call_args[0][0]
        self.assertEqual(added.failure_type, FailureType.IMAGE_FETCH_FAILED.value)

    def test_error_truncated_to_max_length(self):
        from backend.app.services.backfill_retry_service import MAX_ERROR_LENGTH
        db = self._make_db(existing_row=None)
        long_error = "x" * (MAX_ERROR_LENGTH + 100)
        record_backfill_failure(db, uuid.uuid4(), Exception(long_error))
        added = db.add.call_args[0][0]
        self.assertLessEqual(len(added.last_error), MAX_ERROR_LENGTH)


class TestClearBackfillFailure(unittest.TestCase):
    def test_deletes_all_rows(self):
        db = MagicMock()
        row1, row2 = MagicMock(), MagicMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = [row1, row2]
        db.execute.return_value = execute_result
        clear_backfill_failure(db, uuid.uuid4())
        self.assertEqual(db.delete.call_count, 2)

    def test_no_error_when_empty(self):
        db = MagicMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        db.execute.return_value = execute_result
        clear_backfill_failure(db, uuid.uuid4())  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# B4 — card_credibility_service
# ─────────────────────────────────────────────────────────────────────────────

from backend.app.services.card_credibility_service import (
    CredibilityIndicators,
    _confidence_status,
    _format_age,
    _format_sample_size,
    build_credibility_indicators,
    render_credibility_html,
)


class TestFormatHelpers(unittest.TestCase):
    def test_age_minutes(self):
        self.assertEqual(_format_age(0.25), "Updated 15m ago")

    def test_age_under_1h(self):
        self.assertEqual(_format_age(0.9), "Updated 54m ago")

    def test_age_hours(self):
        self.assertEqual(_format_age(3.0), "Updated 3h ago")

    def test_age_47h(self):
        self.assertEqual(_format_age(47.0), "Updated 47h ago")

    def test_age_days(self):
        self.assertEqual(_format_age(48.0), "Updated 2d ago")

    def test_age_3d(self):
        self.assertEqual(_format_age(72.0), "Updated 3d ago")

    def test_age_none(self):
        self.assertEqual(_format_age(None), "No data")

    def test_sample_zero(self):
        self.assertEqual(_format_sample_size(0), "No sales data")

    def test_sample_one(self):
        self.assertEqual(_format_sample_size(1), "Based on 1 sale")

    def test_sample_many(self):
        self.assertEqual(_format_sample_size(47), "Based on 47 sales")

    def test_sample_thousands(self):
        self.assertEqual(_format_sample_size(1000), "Based on 1,000 sales")

    def test_confidence_green(self):
        self.assertEqual(_confidence_status(0.95), "green")

    def test_confidence_green_boundary(self):
        self.assertEqual(_confidence_status(0.85), "green")

    def test_confidence_yellow(self):
        self.assertEqual(_confidence_status(0.80), "yellow")

    def test_confidence_yellow_boundary(self):
        self.assertEqual(_confidence_status(0.70), "yellow")

    def test_confidence_red(self):
        self.assertEqual(_confidence_status(0.69), "red")

    def test_confidence_none_unknown(self):
        self.assertEqual(_confidence_status(None), "unknown")


class TestBuildCredibilityIndicators(unittest.TestCase):
    def _make_db(self, sample_count=10, latest_hours_ago=5, conf=0.90):
        db = MagicMock()
        now = datetime.now(timezone.utc)

        main_row = MagicMock()
        main_row.cnt = sample_count
        main_row.latest = (
            now - timedelta(hours=latest_hours_ago)
            if latest_hours_ago is not None else None
        )

        source_rows = [
            MagicMock(source="ebay_sold", cnt=7),
            MagicMock(source="pokemon_tcg_api", cnt=3),
        ]

        call_count = [0]
        returns = [
            MagicMock(one=lambda: main_row),
            MagicMock(all=lambda: source_rows),
            MagicMock(scalar_one_or_none=lambda: conf),
        ]

        def side_effect(*args, **kwargs):
            idx = min(call_count[0], len(returns) - 1)
            call_count[0] += 1
            return returns[idx]

        db.execute.side_effect = side_effect
        return db

    def test_sample_size_free(self):
        db = self._make_db(sample_count=47)
        ind = build_credibility_indicators(db, uuid.uuid4(), "free")
        self.assertEqual(ind.sample_size, 47)
        self.assertIn("47", ind.sample_size_label)

    def test_data_age_free(self):
        db = self._make_db(latest_hours_ago=3)
        ind = build_credibility_indicators(db, uuid.uuid4(), "free")
        self.assertIsNotNone(ind.data_age_hours)
        self.assertIn("3h", ind.data_age_label)

    def test_source_breakdown_hidden_for_free(self):
        db = self._make_db()
        ind = build_credibility_indicators(db, uuid.uuid4(), "free")
        self.assertIsNone(ind.source_breakdown)

    def test_source_breakdown_visible_for_pro(self):
        db = self._make_db()
        ind = build_credibility_indicators(db, uuid.uuid4(), "pro")
        self.assertIsNotNone(ind.source_breakdown)
        self.assertIn("ebay_sold", ind.source_breakdown)
        self.assertIn("pokemon_tcg_api", ind.source_breakdown)

    def test_source_breakdown_sums_to_one(self):
        db = self._make_db()
        ind = build_credibility_indicators(db, uuid.uuid4(), "pro")
        self.assertAlmostEqual(sum(ind.source_breakdown.values()), 1.0, places=2)

    def test_match_confidence_hidden_for_free(self):
        db = self._make_db(conf=0.92)
        ind = build_credibility_indicators(db, uuid.uuid4(), "free")
        self.assertIsNone(ind.match_confidence)

    def test_match_confidence_visible_for_pro(self):
        db = self._make_db(conf=0.92)
        ind = build_credibility_indicators(db, uuid.uuid4(), "pro")
        self.assertAlmostEqual(ind.match_confidence, 0.92)

    def test_no_data(self):
        db = self._make_db(sample_count=0, latest_hours_ago=None)
        ind = build_credibility_indicators(db, uuid.uuid4(), "free")
        self.assertEqual(ind.sample_size, 0)
        self.assertIsNone(ind.data_age_hours)
        self.assertEqual(ind.data_age_label, "No data")


class TestRenderCredibilityHtml(unittest.TestCase):
    def _ind(self, **kw):
        defaults = dict(
            sample_size=47,
            data_age_hours=3.0,
            source_breakdown=None,
            match_confidence=None,
            data_age_label="Updated 3h ago",
            sample_size_label="Based on 47 sales",
            confidence_status="unknown",
        )
        defaults.update(kw)
        return CredibilityIndicators(**defaults)

    def test_renders_age(self):
        html = render_credibility_html(self._ind())
        self.assertIn("Updated 3h ago", html)

    def test_renders_sample(self):
        html = render_credibility_html(self._ind())
        self.assertIn("Based on 47 sales", html)

    def test_source_breakdown_omitted_when_none(self):
        html = render_credibility_html(self._ind())
        self.assertNotIn("credibility-sources", html)

    def test_source_breakdown_rendered(self):
        html = render_credibility_html(self._ind(
            source_breakdown={"ebay_sold": 0.72, "pokemon_tcg_api": 0.28}
        ))
        self.assertIn("eBay", html)
        self.assertIn("TCG API", html)
        self.assertIn("72%", html)

    def test_confidence_badge_omitted_when_none(self):
        html = render_credibility_html(self._ind())
        self.assertNotIn("confidence-badge", html)

    def test_confidence_badge_rendered(self):
        html = render_credibility_html(self._ind(
            match_confidence=0.88,
            confidence_status="green",
        ))
        self.assertIn("confidence-badge--green", html)
        self.assertIn("88%", html)


if __name__ == "__main__":
    unittest.main()
