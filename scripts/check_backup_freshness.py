"""GitHub Actions backup freshness watchdog.

Hits the GitHub Releases API for ivancjz/flashcard-planet-backups and verifies
the most recent release is younger than BACKUP_MAX_AGE_HOURS (default 30h).

Usage (manual or via scheduler wrapper):
    python scripts/check_backup_freshness.py

Required env vars:
    BACKUP_REPO_READ_TOKEN  — GitHub PAT with read-only access to the backup repo

Optional env vars:
    BACKUP_REPO            — defaults to "ivancjz/flashcard-planet-backups"
    BACKUP_MAX_AGE_HOURS   — defaults to 30 (alert if latest release is older than this)

Exit codes:
    0 — latest backup is fresh
    1 — latest backup is stale, API error, or missing token

Return value (from check_backup_freshness()):
    (exit_code: int, meta: dict) where meta contains:
        latest_tag      — e.g. "backup-14"
        latest_size_mb  — asset size in MB (from assets[0].size)
        latest_age_hours — age at check time, rounded to 1 decimal
        releases_fetched — count of releases returned by this API call (per_page=10 max)
        status          — "fresh" | "stale" | "error"

Logging:
    Uses stdlib logging with JSON-structured output.
    # PR #14b: migrate this module to structlog once structlog is adopted in the codebase.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Logging — stdlib JSON format until structlog arrives in PR #14b.
# PR #14b: replace this block with structlog.get_logger() and remove the
# _JsonFormatter class. All log.info/log.error calls use the same kwargs so
# the migration is mechanical.
# ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    """Single-line JSON log records for structured log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Merge any extra kwargs passed via record.__dict__
        for k, v in record.__dict__.items():
            if k not in (
                "msg", "args", "levelname", "name", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "message", "taskName",
            ):
                payload[k] = v
        return json.dumps(payload, default=str)


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("check_backup_freshness")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


log = _get_logger()


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

_GITHUB_API_BASE = "https://api.github.com"


def check_backup_freshness() -> tuple[int, dict]:
    """Returns (exit_code, meta_dict). exit_code 0=fresh, 1=stale/error."""
    token = os.environ.get("BACKUP_REPO_READ_TOKEN")
    if not token:
        log.error("missing_env_var", extra={"var": "BACKUP_REPO_READ_TOKEN",
                  "hint": "Set BACKUP_REPO_READ_TOKEN to a GitHub PAT with repo read access"})
        return 1, {"status": "error", "error_reason": "BACKUP_REPO_READ_TOKEN not set",
                   "latest_tag": None, "latest_size_mb": None,
                   "latest_age_hours": None, "releases_fetched": 0}

    repo = os.environ.get("BACKUP_REPO", "ivancjz/flashcard-planet-backups")
    max_age_hours = float(os.environ.get("BACKUP_MAX_AGE_HOURS", "30"))

    url = f"{_GITHUB_API_BASE}/repos/{repo}/releases?per_page=10"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        reason = f"HTTP {exc.code}: {exc.reason}"
        log.error("github_api_http_error", extra={"http_status": exc.code, "reason": exc.reason, "url": url})
        return 1, {"status": "error", "error_reason": reason, "latest_tag": None,
                   "latest_size_mb": None, "latest_age_hours": None, "releases_fetched": 0}
    except urllib.error.URLError as exc:
        reason = f"URLError: {exc.reason}"
        log.error("github_api_url_error", extra={"reason": str(exc.reason), "url": url})
        return 1, {"status": "error", "error_reason": reason, "latest_tag": None,
                   "latest_size_mb": None, "latest_age_hours": None, "releases_fetched": 0}
    except Exception as exc:
        reason = f"unexpected: {exc}"
        log.error("github_api_unexpected_error", extra={"error": str(exc), "url": url})
        return 1, {"status": "error", "error_reason": reason, "latest_tag": None,
                   "latest_size_mb": None, "latest_age_hours": None, "releases_fetched": 0}

    if not releases:
        log.error("no_releases_found", extra={"repo": repo,
                  "hint": "No GitHub releases found — backup workflow may not have run yet"})
        return 1, {"status": "error", "error_reason": f"no releases found in {repo}",
                   "latest_tag": None, "latest_size_mb": None,
                   "latest_age_hours": None, "releases_fetched": 0}

    # GitHub API sorts by created_at (creation date of the release record), not published_at
    # (when the asset was last updated). Sort by published_at to find the most recent backup.
    releases.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    latest = releases[0]
    latest_tag: str = latest.get("tag_name", "")
    published_at_str: str = latest.get("published_at", "")

    # Validate backup asset exists and is non-empty.
    # A release can be created but the asset upload may fail (e.g. Actions transient error),
    # leaving a valid release timestamp with no downloadable backup. Without this check the
    # watchdog would report "fresh" even though there is no restorable backup.
    _MIN_BACKUP_BYTES = 1_048_576  # 1 MB — a real backup is ~450 MB; anything smaller is corrupt/missing
    assets = latest.get("assets", [])
    backup_asset = next(
        (a for a in assets if a.get("name", "").endswith(".sql.gz") and a.get("size", 0) >= _MIN_BACKUP_BYTES),
        None,
    )
    if backup_asset is None:
        asset_names = [a.get("name", "") for a in assets]
        log.error("backup_asset_missing_or_empty", extra={
            "latest_tag": latest_tag,
            "asset_names": asset_names,
            "hint": "Release exists but backup.sql.gz is absent or too small — asset upload may have failed",
        })
        return 1, {"status": "error",
                   "error_reason": f"no valid backup asset in release {latest_tag} (assets: {asset_names})",
                   "latest_tag": latest_tag, "latest_size_mb": 0,
                   "latest_age_hours": None, "releases_fetched": len(releases)}
    size_bytes: int = backup_asset.get("size", 0)
    size_mb = round(size_bytes / 1024 / 1024, 2)

    try:
        published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        log.error("published_at_parse_error", extra={"published_at": published_at_str, "error": str(exc)})
        return 1, {"status": "error",
                   "error_reason": f"could not parse published_at={published_at_str!r}: {exc}",
                   "latest_tag": latest_tag, "latest_size_mb": size_mb,
                   "latest_age_hours": None, "releases_fetched": len(releases)}

    now_utc = datetime.now(UTC)
    age_hours = round((now_utc - published_at).total_seconds() / 3600, 1)

    meta: dict = {
        "latest_tag": latest_tag,
        "latest_size_mb": size_mb,
        "latest_age_hours": age_hours,
        "releases_fetched": len(releases),
        "status": "fresh" if age_hours <= max_age_hours else "stale",
    }

    if age_hours > max_age_hours:
        log.error("backup_stale", extra={
            "latest_tag": latest_tag,
            "age_hours": age_hours,
            "max_age_hours": max_age_hours,
            "published_at": published_at_str,
        })
        return 1, meta

    log.info("backup_fresh", extra={
        "latest_tag": latest_tag,
        "age_hours": age_hours,
        "size_mb": size_mb,
        "releases_fetched": len(releases),
    })
    return 0, meta


if __name__ == "__main__":
    sys.exit(check_backup_freshness()[0])
