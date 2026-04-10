"""Ingestion cron runner.

Entry point: python -m backend.app.ingestion.runner

Runs run_batch() on a fixed interval. Traps SIGTERM for graceful shutdown —
completes the current batch before exiting.
"""
from __future__ import annotations

import asyncio
import json
import logging
import logging.config
import os
import signal
import sys

from backend.app.db.session import SessionLocal
from backend.app.ingestion.pipeline import run_batch

INTERVAL_SECONDS = int(os.getenv("INGESTION_INTERVAL_SECONDS", "7200"))

_shutdown_requested = False


def _configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "logging.Formatter",
                    "fmt": "%(message)s",
                }
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                }
            },
            "root": {"level": os.getenv("LOG_LEVEL", "INFO"), "handlers": ["stdout"]},
        }
    )


def _log_json(level: int, event: str, **fields: object) -> None:
    logging.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


def _handle_sigterm(signum: int, frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    _log_json(logging.INFO, "runner_shutdown_requested", signal=signum)


async def _run_once() -> None:
    _log_json(logging.INFO, "runner_batch_start")
    db = SessionLocal()
    try:
        result = await run_batch(db)
        _log_json(
            logging.INFO,
            "runner_batch_done",
            assets_written=result.assets_written,
            errors=len(result.errors),
            duration_ms=round(result.duration_ms, 1),
        )
    except Exception as exc:
        _log_json(logging.ERROR, "runner_batch_error", error_type=type(exc).__name__, message=str(exc))
    finally:
        db.close()


async def _loop() -> None:
    _log_json(logging.INFO, "runner_started", interval_seconds=INTERVAL_SECONDS)
    while not _shutdown_requested:
        await _run_once()
        if _shutdown_requested:
            break
        _log_json(logging.INFO, "runner_sleeping", seconds=INTERVAL_SECONDS)
        # Sleep in small increments so SIGTERM is handled promptly
        for _ in range(INTERVAL_SECONDS * 10):
            if _shutdown_requested:
                break
            await asyncio.sleep(0.1)
    _log_json(logging.INFO, "runner_stopped")


def main() -> None:
    _configure_logging()
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    try:
        asyncio.run(_loop())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
