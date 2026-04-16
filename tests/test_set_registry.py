"""
tests/test_set_registry.py

Covers backend/app/core/set_registry.py (B1):
  - SUPPORTED_SETS completeness and internal consistency
  - P1_P2_SETS / P1_P2_CARD_IDS derivation
  - ALL_BULK_SET_IDS / P1_P2_BULK_SET_IDS string format
  - _card_ids_for_set() generation
  - get_set() lookup
  - sets_by_priority() ordering and filtering

Run with:  pytest tests/test_set_registry.py -v
"""
from __future__ import annotations

import unittest

from backend.app.core.set_registry import (
    ALL_BULK_SET_IDS,
    P1_P2_BULK_SET_IDS,
    P1_P2_CARD_IDS,
    P1_P2_SETS,
    SUPPORTED_SETS,
    SetConfig,
    _card_ids_for_set,
    get_set,
    sets_by_priority,
)


class TestSupportedSets(unittest.TestCase):
    def test_not_empty(self):
        self.assertGreater(len(SUPPORTED_SETS), 0)

    def test_all_entries_are_set_config(self):
        for s in SUPPORTED_SETS:
            self.assertIsInstance(s, SetConfig)

    def test_set_ids_are_unique(self):
        ids = [s.set_id for s in SUPPORTED_SETS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_have_positive_card_count(self):
        for s in SUPPORTED_SETS:
            self.assertGreater(s.card_count, 0, msg=f"{s.set_id} has card_count <= 0")

    def test_all_have_valid_priority(self):
        for s in SUPPORTED_SETS:
            self.assertIn(s.priority, (1, 2, 3, 4), msg=f"{s.set_id} has unexpected priority")

    def test_base1_is_priority_1(self):
        base1 = get_set("base1")
        self.assertIsNotNone(base1)
        self.assertEqual(base1.priority, 1)

    def test_jungle_fossil_team_rocket_are_priority_2(self):
        for set_id in ("base2", "base3", "base5"):
            s = get_set(set_id)
            self.assertIsNotNone(s, msg=f"{set_id} not found")
            self.assertEqual(s.priority, 2, msg=f"{set_id} should be P2")


class TestCardIdGeneration(unittest.TestCase):
    def test_generates_correct_count(self):
        ids = _card_ids_for_set("base1", 102)
        self.assertEqual(len(ids), 102)

    def test_first_id(self):
        ids = _card_ids_for_set("base1", 102)
        self.assertEqual(ids[0], "base1-1")

    def test_last_id(self):
        ids = _card_ids_for_set("base1", 102)
        self.assertEqual(ids[-1], "base1-102")

    def test_single_card_set(self):
        ids = _card_ids_for_set("promo1", 1)
        self.assertEqual(ids, ["promo1-1"])


class TestP1P2Derivation(unittest.TestCase):
    def test_p1p2_sets_all_have_priority_lte_2(self):
        for s in P1_P2_SETS:
            self.assertLessEqual(s.priority, 2)

    def test_p1p2_sets_includes_base1(self):
        ids = [s.set_id for s in P1_P2_SETS]
        self.assertIn("base1", ids)

    def test_p1p2_sets_excludes_p3(self):
        ids = [s.set_id for s in P1_P2_SETS]
        # sv1 is P3 — must not appear
        self.assertNotIn("sv1", ids)

    def test_p1p2_card_ids_not_empty(self):
        self.assertGreater(len(P1_P2_CARD_IDS), 0)

    def test_p1p2_card_ids_contains_base1_cards(self):
        self.assertIn("base1-1", P1_P2_CARD_IDS)
        self.assertIn("base1-102", P1_P2_CARD_IDS)

    def test_p1p2_card_ids_total_count(self):
        expected = sum(s.card_count for s in P1_P2_SETS)
        self.assertEqual(len(P1_P2_CARD_IDS), expected)

    def test_p1p2_card_ids_are_unique(self):
        self.assertEqual(len(P1_P2_CARD_IDS), len(set(P1_P2_CARD_IDS)))


class TestBulkSetIdStrings(unittest.TestCase):
    def test_all_bulk_set_ids_contains_all_set_ids(self):
        all_ids = set(ALL_BULK_SET_IDS.split(","))
        for s in SUPPORTED_SETS:
            self.assertIn(s.set_id, all_ids)

    def test_p1p2_bulk_set_ids_subset_of_all(self):
        all_ids = set(ALL_BULK_SET_IDS.split(","))
        p1p2_ids = set(P1_P2_BULK_SET_IDS.split(","))
        self.assertTrue(p1p2_ids.issubset(all_ids))

    def test_p1p2_bulk_excludes_p3(self):
        p1p2_ids = set(P1_P2_BULK_SET_IDS.split(","))
        self.assertNotIn("sv1", p1p2_ids)

    def test_no_empty_tokens_in_all_bulk(self):
        for token in ALL_BULK_SET_IDS.split(","):
            self.assertTrue(token.strip(), msg="Empty token found in ALL_BULK_SET_IDS")


class TestGetSet(unittest.TestCase):
    def test_returns_correct_set(self):
        s = get_set("base1")
        self.assertIsNotNone(s)
        self.assertEqual(s.name, "Base Set")
        self.assertEqual(s.card_count, 102)

    def test_returns_none_for_unknown(self):
        self.assertIsNone(get_set("nonexistent_set_xyz"))

    def test_returns_sv_set(self):
        s = get_set("sv3pt5")
        self.assertIsNotNone(s)
        self.assertEqual(s.name, "151")


class TestSetsByPriority(unittest.TestCase):
    def test_returns_only_up_to_max_priority(self):
        result = sets_by_priority(max_priority=2)
        for s in result:
            self.assertLessEqual(s.priority, 2)

    def test_sorted_by_priority_then_year(self):
        result = sets_by_priority(max_priority=4)
        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            self.assertLessEqual(
                (a.priority, a.release_year),
                (b.priority, b.release_year),
                msg=f"Sort order violated: {a.set_id} before {b.set_id}",
            )

    def test_default_max_priority_returns_all(self):
        result = sets_by_priority()
        self.assertEqual(len(result), len(SUPPORTED_SETS))

    def test_max_priority_1_returns_only_base1(self):
        result = sets_by_priority(max_priority=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].set_id, "base1")

    def test_max_priority_0_returns_empty(self):
        result = sets_by_priority(max_priority=0)
        self.assertEqual(result, [])
