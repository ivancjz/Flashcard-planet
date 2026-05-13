"""
tests/test_check_backup_freshness.py

Tests for scripts/check_backup_freshness.py::check_backup_freshness().

Six scenarios:
  1. Fresh backup (age < 30h)                       → (0, meta with status="fresh")
  2. Stale backup (age > 30h)                       → (1, meta with status="stale")
  3. Missing token                                  → (1, meta with status="error")
  4. Empty releases list                            → (1, meta with status="error")
  5. GitHub API HTTP error                          → (1, meta with status="error")
  6. API returns releases out of published_at order → selects most recently published
"""
from __future__ import annotations

import io
import json
import unittest
import urllib.error
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build mock GitHub API responses
# ---------------------------------------------------------------------------

def _make_release(age_hours: float, tag: str = "backup-14", size_bytes: int = 5_242_880) -> dict:
    """Return a dict shaped like one GitHub release object."""
    published_at = datetime.now(UTC) - timedelta(hours=age_hours)
    return {
        "tag_name": tag,
        "published_at": published_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assets": [{"size": size_bytes}],
    }


def _mock_urlopen(releases: list[dict]):
    """Return a context-manager mock that yields the given releases as JSON."""
    body = json.dumps(releases).encode("utf-8")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read = MagicMock(return_value=body)
    return cm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckBackupFreshness(unittest.TestCase):

    def setUp(self):
        # Always provide the token env var unless a specific test overrides it
        self._token_patch = patch.dict("os.environ", {
            "BACKUP_REPO_READ_TOKEN": "ghp_test_token",
            "BACKUP_REPO": "ivancjz/flashcard-planet-backups",
        })
        self._token_patch.start()

    def tearDown(self):
        self._token_patch.stop()

    # ------------------------------------------------------------------
    # 1. Fresh backup
    # ------------------------------------------------------------------
    def test_fresh_backup_returns_0_and_fresh_status(self):
        releases = [_make_release(age_hours=6.0, tag="backup-14", size_bytes=5_242_880)]

        with patch("urllib.request.urlopen", return_value=_mock_urlopen(releases)):
            from scripts.check_backup_freshness import check_backup_freshness
            exit_code, meta = check_backup_freshness()

        self.assertEqual(exit_code, 0)
        self.assertEqual(meta["status"], "fresh")
        self.assertEqual(meta["latest_tag"], "backup-14")
        self.assertAlmostEqual(meta["latest_age_hours"], 6.0, delta=0.2)
        self.assertAlmostEqual(meta["latest_size_mb"], 5.0, delta=0.01)
        self.assertEqual(meta["releases_fetched"], 1)

    # ------------------------------------------------------------------
    # 2. Stale backup
    # ------------------------------------------------------------------
    def test_stale_backup_returns_1_and_stale_status(self):
        releases = [_make_release(age_hours=36.0, tag="backup-13")]

        with patch("urllib.request.urlopen", return_value=_mock_urlopen(releases)):
            from scripts.check_backup_freshness import check_backup_freshness
            exit_code, meta = check_backup_freshness()

        self.assertEqual(exit_code, 1)
        self.assertEqual(meta["status"], "stale")
        self.assertEqual(meta["latest_tag"], "backup-13")
        self.assertGreater(meta["latest_age_hours"], 30.0)

    # ------------------------------------------------------------------
    # 3. Missing token
    # ------------------------------------------------------------------
    def test_missing_token_returns_error(self):
        with patch.dict("os.environ", {}, clear=True):
            from scripts.check_backup_freshness import check_backup_freshness
            exit_code, meta = check_backup_freshness()

        self.assertEqual(exit_code, 1)
        self.assertEqual(meta["status"], "error")
        self.assertIsNone(meta["latest_tag"])

    # ------------------------------------------------------------------
    # 4. Empty releases list
    # ------------------------------------------------------------------
    def test_empty_releases_returns_error(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])):
            from scripts.check_backup_freshness import check_backup_freshness
            exit_code, meta = check_backup_freshness()

        self.assertEqual(exit_code, 1)
        self.assertEqual(meta["status"], "error")
        self.assertEqual(meta["releases_fetched"], 0)

    # ------------------------------------------------------------------
    # 5. HTTP error (403, 404)
    # ------------------------------------------------------------------
    def test_http_error_returns_error(self):
        http_err = urllib.error.HTTPError(
            url="https://api.github.com/repos/x/y/releases?per_page=10",
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            from scripts.check_backup_freshness import check_backup_freshness
            exit_code, meta = check_backup_freshness()

        self.assertEqual(exit_code, 1)
        self.assertEqual(meta["status"], "error")
        self.assertEqual(meta["releases_fetched"], 0)


    # ------------------------------------------------------------------
    # 6. API returns releases out of published_at order (GitHub sorts by created_at)
    # ------------------------------------------------------------------
    def test_selects_most_recently_published_when_order_mixed(self):
        # Simulate GitHub returning backup-9 (older published_at) before
        # backup-14 (newer published_at) because created_at ordering differs.
        old_release = _make_release(age_hours=150.0, tag="backup-9")
        new_release = _make_release(age_hours=6.0, tag="backup-14")
        releases_out_of_order = [old_release, new_release]  # old first, as GitHub would return

        with patch("urllib.request.urlopen", return_value=_mock_urlopen(releases_out_of_order)):
            from scripts.check_backup_freshness import check_backup_freshness
            exit_code, meta = check_backup_freshness()

        self.assertEqual(exit_code, 0)
        self.assertEqual(meta["status"], "fresh")
        self.assertEqual(meta["latest_tag"], "backup-14")


if __name__ == "__main__":
    unittest.main()
