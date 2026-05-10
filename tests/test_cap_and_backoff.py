"""
Unit tests for cap_and_backoff — the shared retry-delay helper in pokemon_tcg.py.

Five tests covering three symmetric cases (matching PR #12's helper intent) plus
two boundary cases for the attempt clamp:
  (i)   Retry-After present and within 60s cap → returned unchanged
  (ii)  Retry-After present and exceeds 60s cap → clamped to 60.0
  (iii) No Retry-After → [2.0, 5.0, 15.0] fallback indexed by attempt
  (iv)  attempt=0 (invalid) → clamped to first fallback (2.0), no IndexError
  (v)   attempt=99 (beyond range) → clamped to last fallback (15.0), no IndexError
"""
import unittest
from backend.app.ingestion.pokemon_tcg import cap_and_backoff


class CapAndBackoffTests(unittest.TestCase):

    def test_retry_after_within_cap_returned_unchanged(self):
        """Retry-After: 30 is below the 60s cap — return it as-is."""
        self.assertEqual(cap_and_backoff(30.0, attempt=1), 30.0)

    def test_retry_after_exceeds_cap_clamped_to_60(self):
        """Retry-After: 3600 must be clamped to exactly 60.0."""
        self.assertEqual(cap_and_backoff(3600.0, attempt=1), 60.0)

    def test_no_retry_after_uses_fallback_sequence(self):
        """None → fallback [2.0, 5.0, 15.0] indexed by attempt 1/2/3."""
        self.assertEqual(cap_and_backoff(None, attempt=1), 2.0)
        self.assertEqual(cap_and_backoff(None, attempt=2), 5.0)
        self.assertEqual(cap_and_backoff(None, attempt=3), 15.0)

    def test_attempt_zero_clamped_to_first_fallback(self):
        """attempt=0 is out-of-range — must not IndexError, must return 2.0."""
        self.assertEqual(cap_and_backoff(None, attempt=0), 2.0)

    def test_attempt_beyond_range_clamped_to_last_fallback(self):
        """attempt=99 is out-of-range — must not IndexError, must return 15.0."""
        self.assertEqual(cap_and_backoff(None, attempt=99), 15.0)
