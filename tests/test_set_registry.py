"""
tests/test_set_registry.py

Covers backend/app/core/set_registry.py:
  - SUPPORTED_SETS completeness and internal consistency
  - P1_P2_SETS / P1_P2_CARD_IDS derivation
  - _card_ids_for_set() generation

ALL_BULK_SET_IDS / P1_P2_BULK_SET_IDS / get_set / sets_by_priority were removed
as dead code (021ea53) — zero callers in production code.

Run with:  pytest tests/test_set_registry.py -v
"""
from __future__ import annotations

import unittest

from backend.app.core.set_registry import (
    P1_P2_CARD_IDS,
    P1_P2_SETS,
    SUPPORTED_SETS,
    SetConfig,
    _card_ids_for_set,
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
        base1 = next((s for s in SUPPORTED_SETS if s.set_id == "base1"), None)
        self.assertIsNotNone(base1)
        self.assertEqual(base1.priority, 1)

    def test_jungle_fossil_team_rocket_are_priority_2(self):
        set_map = {s.set_id: s for s in SUPPORTED_SETS}
        for set_id in ("base2", "base3", "base5"):
            s = set_map.get(set_id)
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
