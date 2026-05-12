"""Daily Postgres backup script — uploads pg_dump output to Cloudflare R2.

Usage (manual trigger or via scheduler wrapper):
    python scripts/backup_postgres.py

Required env vars:
    DATABASE_URL_DIRECT           — direct Postgres connection URL, bypasses PgBouncer
                                    (same as DATABASE_URL until PR #14c adds PgBouncer)
    CLOUDFLARE_R2_ACCOUNT_ID      — Cloudflare account ID
    CLOUDFLARE_R2_ACCESS_KEY_ID   — R2 API token key
    CLOUDFLARE_R2_SECRET_ACCESS_KEY — R2 API token secret
    CLOUDFLARE_R2_BUCKET          — R2 bucket name (flashcard-planet-backups)

Output key in R2: daily/YYYY-MM-DD.dump  (pg_dump custom format, compress=9)

Exit codes:
    0 — success
    1 — failure (pg_dump error or R2 upload error)

Logging:
    Uses stdlib logging with JSON-structured output.
    # PR #14b: migrate this module to structlog once structlog is adopted in the codebase.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------------------
# Logging — stdlib JSON format until structlog arrives in PR #14b.
# PR #14b: replace this block with structlog.get_logger() and remove the
# JsonFormatter class. All log.info/log.error calls use the same kwargs so
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
    logger = logging.getLogger("backup_postgres")
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

def run_backup() -> int:
    """Execute the backup. Returns 0 on success, 1 on any failure."""
    try:
        database_url = os.environ["DATABASE_URL_DIRECT"]
    except KeyError:
        log.error("missing_env_var", var="DATABASE_URL_DIRECT",
                  hint="Set DATABASE_URL_DIRECT in Railway env vars (same as DATABASE_URL until PgBouncer lands in PR #14c)")
        return 1

    try:
        r2_account = os.environ["CLOUDFLARE_R2_ACCOUNT_ID"]
        r2_access_key = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"]
        r2_secret_key = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
        r2_bucket = os.environ["CLOUDFLARE_R2_BUCKET"]
    except KeyError as exc:
        log.error("missing_env_var", var=str(exc),
                  hint="Set all CLOUDFLARE_R2_* env vars in Railway env vars")
        return 1

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    local_path = Path(f"/tmp/flashcard-planet-{today}.dump")
    log.info("backup_start", date=today, bucket=r2_bucket)

    # ------------------------------------------------------------------
    # Step 1: pg_dump — custom format, compress=9, no-owner, no-privileges
    # DATABASE_URL_DIRECT bypasses PgBouncer (needed for pg_dump which holds
    # transactions open and uses session features incompatible with
    # transaction-pool mode).  See PR #14c for PgBouncer deployment.
    # ------------------------------------------------------------------
    try:
        result = subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--compress=9",
                "--no-owner",
                "--no-privileges",
                f"--file={local_path}",
                database_url,
            ],
            check=True,
            capture_output=True,
            timeout=1800,  # 30 min hard limit
        )
        size_mb = local_path.stat().st_size / 1024 / 1024
        log.info("pg_dump_complete", size_mb=round(size_mb, 2), path=str(local_path))
    except subprocess.CalledProcessError as exc:
        log.error("pg_dump_failed",
                  returncode=exc.returncode,
                  stderr=exc.stderr.decode("utf-8", errors="replace")[:500])
        return 1
    except subprocess.TimeoutExpired:
        log.error("pg_dump_timeout", timeout_s=1800)
        return 1
    except FileNotFoundError:
        log.error("pg_dump_not_found",
                  hint="pg_dump not in PATH. Add postgresql_18 to nixPkgs in nixpacks.toml.")
        return 1
    except Exception as exc:
        log.error("pg_dump_unexpected_error", error=str(exc))
        return 1

    # ------------------------------------------------------------------
    # Step 2: Upload to R2
    # R2 is S3-compatible; boto3 points at the Cloudflare endpoint.
    # ------------------------------------------------------------------
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{r2_account}.r2.cloudflarestorage.com",
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            region_name="auto",
        )
        key = f"daily/{today}.dump"
        s3.upload_file(
            str(local_path),
            r2_bucket,
            key,
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        log.info("r2_upload_complete", key=key, bucket=r2_bucket,
                 size_mb=round(size_mb, 2))
    except (BotoCoreError, ClientError) as exc:
        log.error("r2_upload_failed", error=str(exc))
        return 1
    except Exception as exc:
        log.error("r2_upload_unexpected_error", error=str(exc))
        return 1
    finally:
        # Always clean up /tmp regardless of upload outcome
        local_path.unlink(missing_ok=True)

    log.info("backup_success", date=today)
    return 0


if __name__ == "__main__":
    sys.exit(run_backup())
