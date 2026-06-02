from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.backstage.gap_detector import GapReport, get_gap_report
from backend.app.ingestion.pokemon_tcg import backfill_single_card, run_backfill_pass
from backend.app.services.backfill_retry_service import run_retry_pass
from backend.app.services.scheduler_run_log_service import (
    JOB_BULK_REFRESH,
    JOB_CARDMARKET,
    JOB_DIGEST,
    JOB_EBAY,
    JOB_EBAY_WEB_SOLD,
    JOB_HEARTBEAT,
    JOB_HISTORY_PRUNE,
    JOB_INGESTION,
    JOB_RETRY,
    JOB_SIGNALS,
    JOB_TRIAL_EXPIRY,
    JOB_YGO,
    JOB_EXPLANATION,
    JOB_BACKUP_FRESHNESS,
    JOB_SEALED_INGEST,
    JOB_RESOLVE,
    finish_run,
    get_last_run,
    prune_old_runs,
    start_run,
)
from backend.app.core.config import get_settings
from backend.app.core.price_sources import (
    get_configured_price_providers,
    get_primary_price_source,
)
from backend.app.core.tracked_pools import get_tracked_pokemon_pools
from backend.app.db.session import SessionLocal
from backend.app.ingestion.provider_registry import (
    get_configured_provider_ingestors,
    get_unimplemented_configured_providers,
)
from sqlalchemy import func, select, text as sa_text
from sqlalchemy.orm import Session
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.scheduler_run_log import SchedulerRunLog

from backend.app.alerting.discord import send_discord_alert
from backend.app.services.alert_service import process_alert_notifications
from backend.app.services.signal_service import sweep_signals

logger = logging.getLogger(__name__)
ebay_logger = logging.getLogger("backend.app.ingestion.ebay_scheduled")

JOB_WALL_CLOCK_LIMIT = timedelta(minutes=30)
EBAY_DURATION_CANARY_THRESHOLD_SECS: int = 60
EBAY_DURATION_CANARY_WINDOW_HOURS: int = 24

_COMPLETED_STATUSES = {"success", "partial", "warning"}

# Maps DB game values to display labels used in the heartbeat message.
# Unknown game values fall back to the raw DB string (see _send_heartbeat usage).
_GAME_DISPLAY_LABELS: dict[str, str] = {"pokemon": "Pokemon", "ygo": "YGO"}


def get_zero_output_jobs(
    session: Session,
    *,
    job_names: list[str],
    window_hours: int,
    now: datetime,
) -> list[str]:
    """Return job names that ran but wrote zero records across the entire window.

    A job with no completed runs in the window is excluded — that is the 25h
    absence check's territory, not a zero-output alert.

    304-skipped runs are excluded from the zero-output check: CardMarket writes
    records_written=0 + meta_json={'not_modified': True} when the upstream S3
    file is unchanged. These are expected zero-output and must not trigger alerts.
    """
    cutoff = now - timedelta(hours=window_hours)
    flagged: list[str] = []
    for job_name in job_names:
        rows = session.execute(
            select(SchedulerRunLog)
            .where(
                SchedulerRunLog.job_name == job_name,
                SchedulerRunLog.started_at >= cutoff,
                SchedulerRunLog.status.in_(list(_COMPLETED_STATUSES)),
            )
        ).scalars().all()

        # Exclude known expected-zero runs so they don't fire false-positive alerts:
        #   not_modified=true  — CardMarket 304-skip (upstream file unchanged)
        #   job_blocked_reason — ebay-ingestion budget_exhausted / disabled path
        #   eligible=0         — resolve-predictions, no due predictions in window
        meaningful_rows = [
            r for r in rows
            if not (r.meta_json or {}).get("not_modified")
            and not (r.meta_json or {}).get("job_blocked_reason")
            and (r.meta_json or {}).get("eligible") != 0
        ]

        total = len(meaningful_rows)
        total_records = sum(r.records_written or 0 for r in meaningful_rows)
        if total > 0 and total_records == 0:
            flagged.append(job_name)
    return flagged


_STARTUP_DELAY: dict[str, int] = {
    "scheduled-ingestion":    120,   #  2 min — first mover
    "signal-sweep":           600,   # 10 min
    "alert-heartbeat":        720,   # 12 min — receives first sweep result before sending
    "ebay-ingestion":         660,   # 11 min — after signal-sweep, before heartbeat reports it
    "yugioh-ingestion":       780,   # 13 min — after heartbeat, YGO sets are small so runs fast
    "cardmarket-ingestion":   1050,  # 17.5 min — after explanation-sweep (960s), before digest (1200s); ±60s clear
    "bulk-set-price-refresh": 900,   # 15 min — after ingestion (120s+~5min run) and signal (600s)
    "explanation-sweep":      960,   # 16 min — after signal-sweep so new signals get explanations fast
    "market-digest-send":     1200,  # 20 min — after all other jobs have warmed up
    "signal-history-prune":   1500,  # 25 min — last; pure DB DELETE, no upstream dependency (TASK-105)
    "trial-expiry-sweep":     900,   # 15 min — subscription maintenance, no upstream dependency
    "sealed-ingest":          840,   # 14 min — eBay Browse API, after heartbeat registered
    "ebay-web-sold":          870,   # 14.5 min — eBay HTML scrape, 24h interval
    "resolve-predictions":    660,   # 11 min — after signal-sweep so prices are fresh
    "backup-freshness-check": 15000, # 4h 10min — runs every 4h so detection latency is ≤4h
                                     # regardless of deploy time. A fixed 24h startup delay would
                                     # allow the watchdog to fire before the 04:00 UTC backup if
                                     # deploys happen between 00:00-01:50 UTC, delaying detection
                                     # to the second day (~46h). 4h interval closes that gap.
    # "retry-pass" intentionally omitted — resume separately when confidence is high
}


@dataclass
class ScheduledIngestionRun:
    started_at: datetime
    ended_at: datetime | None = None
    records_written: int = 0
    card_failures: int = 0
    errors: list[str] = field(default_factory=list)
    gap_report: GapReport | None = None


@dataclass
class EbayScheduledRunSummary:
    """Summary of a single eBay scheduled ingestion run."""
    run_status: str  # "success" | "partial" | "skipped" | "failed"
    assets_considered: int = 0
    assets_processed: int = 0
    assets_skipped_budget: int = 0
    errors: list[str] = field(default_factory=list)
    api_calls_used: int = 0
    budget_remaining: int = 0
    observations_fetched: int = 0
    matched: int = 0
    unmatched: int = 0
    price_points_inserted: int = 0
    duplicates_skipped: int = 0
    match_status_counts: dict[str, int] = field(default_factory=dict)
    job_blocked_reason: str | None = None
    deadline_reached: bool = False
    assets_remaining: int = 0


def _log_gap_report(report: GapReport) -> None:
    logger.info(
        "Current gap report: total_assets=%s covered_assets=%s gap_count=%s zero_history_assets=%s thin_history_assets=%s partial_sets=%s threshold=%s set_coverage_threshold=%s",
        report.total_assets,
        report.covered_assets,
        report.gap_count,
        report.zero_history_assets,
        report.thin_history_assets,
        report.partial_sets,
        report.history_threshold,
        report.set_coverage_threshold,
    )


def _is_first_successful_sweep(session) -> bool:
    count = session.execute(
        sa_text(
            "SELECT COUNT(*) FROM scheduler_run_log "
            "WHERE job_name = 'signals' AND status = 'success'"
        )
    ).scalar()
    return count == 1


def _run_signal_sweep() -> None:
    settings = get_settings()
    if not settings.signal_sweep_enabled:
        logger.info("signal_sweep_skipped reason=kill_switch")
        return

    logger.info("Signal sweep tick started.")
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_SIGNALS)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_SIGNALS)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_SIGNALS}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return
    try:
        with SessionLocal() as session:
            result = sweep_signals(session)
        logger.info(
            "Signal sweep finished. total=%s breakout=%s move=%s watch=%s idle=%s "
            "insufficient_data=%s errors=%s duration_ms=%.1f",
            result.total, result.breakout, result.move, result.watch,
            result.idle, result.insufficient_data, result.errors, result.duration_ms,
        )
        meta = {
            "breakout": result.breakout,
            "move": result.move,
            "watch": result.watch,
            "idle": result.idle,
            "insufficient_data": result.insufficient_data,
            "errors": result.errors,
            "duration_ms": round(result.duration_ms, 1),
        }
        is_first = False
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status="success",
                records_written=result.total,
                meta_json=meta,
            )
            is_first = _is_first_successful_sweep(_log_session)
            prune_old_runs(_log_session, JOB_SIGNALS)

        if is_first:
            send_discord_alert(
                "success",
                "Signal sweep 首次生产运行成功",
                f"BREAKOUT={result.breakout} MOVE={result.move} "
                f"WATCH={result.watch} IDLE={result.idle} "
                f"INSUFFICIENT_DATA={result.insufficient_data}\n"
                f"Total={result.total} records",
            )

        if result.total > settings.signal_sweep_alert_threshold:
            send_discord_alert(
                "warning",
                "Signal sweep 产出异常大",
                f"一次 sweep 写入 {result.total} 条 signal，超过 {settings.signal_sweep_alert_threshold} 阈值\n"
                f"BREAKOUT={result.breakout} MOVE={result.move} "
                f"WATCH={result.watch} IDLE={result.idle} "
                f"INSUFFICIENT_DATA={result.insufficient_data}\n"
                "可能阈值配置错误，请检查",
            )

    except Exception:
        logger.exception("Signal sweep job failed.")
        with SessionLocal() as _log_session:
            finish_run(_log_session, _run_id, status="error")
        send_discord_alert(
            "error",
            "Signal sweep 失败",
            f"Run ID: {_run_id}\n"
            "如需紧急暂停，在 Railway 设 SIGNAL_SWEEP_ENABLED=false",
        )


def _run_retry_pass() -> None:
    if not get_settings().retry_pass_enabled:
        logger.info("retry_pass_skipped reason=kill_switch")
        return
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_RETRY)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_RETRY)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_RETRY}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return
    try:
        with SessionLocal() as session:
            result = run_retry_pass(session, backfill_fn=backfill_single_card)
            session.commit()
        logger.info(
            '{"event": "retry_pass_complete", "recovered": %d, "still_failing": %d, "newly_permanent": %d}',
            result.recovered,
            result.still_failing,
            result.newly_permanent,
        )
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status="success",
                records_written=result.recovered,
                errors=result.still_failing,
            )
            prune_old_runs(_log_session, JOB_RETRY)
    except Exception:
        logger.exception('{"event": "retry_pass_error"}')
        with SessionLocal() as _log_session:
            finish_run(_log_session, _run_id, status="error")


def _ebay_duration_canary_rows(
    session: "Session",
    threshold_secs: int,
    window_hours: int,
) -> tuple[int, int]:
    """Return (total_completed_runs, fast_runs) for ebay-ingestion in window.

    A run is "fast" if it completed in < threshold_secs seconds.
    Explicitly-skipped runs (disabled, budget_exhausted, missing_credentials)
    are excluded via job_blocked_reason IS NULL — they have short duration by
    design (they did no API work), not because of fast-failing.
    Used by _send_heartbeat to detect the fast-failing pattern
    (Finding API rejecting before Browse fallback).
    """
    row = session.execute(sa_text("""
        SELECT
            COUNT(*) AS total_runs,
            COUNT(*) FILTER (
                WHERE finished_at IS NOT NULL
                  AND EXTRACT(EPOCH FROM (finished_at - started_at)) < :threshold
            ) AS fast_runs
        FROM scheduler_run_log
        WHERE job_name = 'ebay-ingestion'
          AND status IN ('success', 'partial', 'warning', 'error', 'failed')
          AND (meta_json->>'job_blocked_reason') IS NULL
          AND started_at > NOW() - (:window_hours || ' hours')::INTERVAL
    """), {"threshold": threshold_secs, "window_hours": window_hours}).fetchone()
    return (int(row.total_runs or 0), int(row.fast_runs or 0))


def _send_heartbeat() -> None:
    """Send a periodic health pulse to Discord.

    The job runs every 10 minutes.  Actual send frequency depends on mode:
      - Observation mode (deploy_observation_mode_until is set and in the future):
        every 10 minutes so you can watch the first few sweeps closely.
      - Normal mode: only once per hour (minute 0–9 window).
    """
    settings = get_settings()

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_HEARTBEAT)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_HEARTBEAT)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_HEARTBEAT}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return

    _exc: BaseException | None = None
    _log_meta: dict | None = None

    try:
        if not settings.alert_heartbeat_enabled:
            _log_meta = {"skipped_reason": "heartbeat_disabled"}
            return

        now = datetime.now(UTC)

        # Parse observation-mode deadline
        observation_until: datetime | None = None
        raw = settings.deploy_observation_mode_until
        if raw:
            try:
                observation_until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if observation_until.tzinfo is None:
                    observation_until = observation_until.replace(tzinfo=UTC)
            except ValueError:
                logger.warning("Invalid DEPLOY_OBSERVATION_MODE_UNTIL: %r", raw)

        in_observation = observation_until is not None and now < observation_until

        # Normal mode: only send during the first 10 minutes of each hour
        if not in_observation and now.minute >= 10:
            _log_meta = {"skipped_reason": "outside_send_window", "minute": now.minute}
            return

        with SessionLocal() as session:
            rows = session.execute(sa_text("""
                SELECT status, COUNT(*) AS cnt, MAX(started_at) AS last_run
                FROM scheduler_run_log
                WHERE job_name = 'signals'
                  AND started_at > now() - interval '1 hour'
                GROUP BY status
            """)).fetchall()

        if not rows:
            send_discord_alert(
                "warning",
                "Heartbeat: signal-sweep 过去 1 小时没有运行",
                "Scheduler 可能挂了，或 SIGNAL_SWEEP_ENABLED=false",
            )
            return

        # eBay ingestion health: warn if ebay-ingestion is enabled and credentials
        # are set but no successful/partial/warning run in the last 25 hours.
        if settings.ebay_scheduled_ingest_enabled and settings.ebay_app_id and settings.ebay_cert_id:
            _good_statuses = ["success", "partial", "warning"]
            with SessionLocal() as _ebay_session:
                last_ebay = get_last_run(_ebay_session, JOB_EBAY, only_statuses=_good_statuses)
            if last_ebay is None:
                ebay_age_h = None
            else:
                last_started = last_ebay.started_at
                if last_started.tzinfo is None:
                    last_started = last_started.replace(tzinfo=UTC)
                ebay_age_h = (now - last_started).total_seconds() / 3600
            if ebay_age_h is None or ebay_age_h > 25:
                send_discord_alert(
                    "warning",
                    "eBay ingestion 超过 25h 未成功运行",
                    f"上次成功运行: {'从未' if last_ebay is None else last_ebay.started_at.isoformat()}\n"
                    "interval job 可能被 deploy 打断，或凭证失效，或每次 api_calls_used=0",
                )

        # Zero-output alert: jobs that ran completed runs but wrote zero records.
        # Detects the eBay-outage pattern: API calls consumed, status=success, 0 rows written.
        # JOB_EBAY excluded: Finding API permanently dead. The job runs its full loop
        # (200+ API calls), gets 0 results on every call, and writes 0 records. There is
        # no job_blocked_reason set on this path — the job "succeeds" but is useless.
        # Monitoring it produces a false-positive alert every 24h with no actionable signal.
        # The 25h absence check above (hardcoded) still runs independently for JOB_EBAY.
        _monitored_jobs = [JOB_INGESTION, JOB_BULK_REFRESH, JOB_SIGNALS, JOB_YGO, JOB_CARDMARKET, JOB_EXPLANATION, JOB_DIGEST, JOB_TRIAL_EXPIRY, JOB_SEALED_INGEST, JOB_EBAY_WEB_SOLD, JOB_RESOLVE]
        with SessionLocal() as _zero_session:
            zero_output = get_zero_output_jobs(
                _zero_session,
                job_names=_monitored_jobs,
                window_hours=settings.zero_output_alert_window_hours,
                now=now,
            )
        if zero_output:
            window_h = settings.zero_output_alert_window_hours
            send_discord_alert(
                "warning",
                f"零产出告警: {len(zero_output)} 个 job 在 {window_h}h 内无数据写入",
                "以下 job 有完成的运行记录但 records_written=0 贯穿整个窗口:\n"
                + "\n".join(f"  • {j}" for j in zero_output)
                + f"\n\n检查 scheduler_run_log (last {window_h}h) 和对应的外部 API 状态。",
            )

        # eBay duration canary: warn when ALL completed runs in the window finished
        # in under EBAY_DURATION_CANARY_THRESHOLD_SECS seconds.
        #
        # Rationale: a healthy Browse API run should take at least minutes once
        # listing_snapshot is wired. Sub-threshold duration = fast-failing:
        # the Finding API (svcs.ebay.com, decommissioned 2025-02-05) rejects on
        # the first call before Browse fallback is attempted.
        # This is a forward-looking WARNING — Browse fallback / listing_snapshot
        # integration does not exist yet. Alert is informational, not actionable today.
        if settings.ebay_scheduled_ingest_enabled and settings.ebay_app_id and settings.ebay_cert_id:
            with SessionLocal() as _dur_session:
                _ebay_total, _ebay_fast = _ebay_duration_canary_rows(
                    _dur_session,
                    threshold_secs=EBAY_DURATION_CANARY_THRESHOLD_SECS,
                    window_hours=EBAY_DURATION_CANARY_WINDOW_HOURS,
                )
            if _ebay_total > 0 and _ebay_total == _ebay_fast:
                send_discord_alert(
                    "warning",
                    f"eBay ingestion 快速失败警告: 过去 {EBAY_DURATION_CANARY_WINDOW_HOURS}h 全部 {_ebay_total} 次运行 < {EBAY_DURATION_CANARY_THRESHOLD_SECS}s",
                    f"Finding API (svcs.ebay.com) 已于 2025-02-05 下线，首次调用即返回拒绝 (10001)。\n"
                    f"Browse API fallback / listing_snapshot 尚未建立。\n"
                    f"此为前瞻性 WARNING，当前无可操作修复。参见 CLAUDE.md eBay API status 节。",
                )

        # Defensive: alert if any ingest path wrote market_segment=NULL in the last 24h.
        # Pre-backfill NULLs from old rows are excluded by the captured_at filter,
        # so this only fires when a live ingest path is missing segment classification.
        with SessionLocal() as _seg_session:
            null_seg_rows = _seg_session.execute(sa_text("""
                SELECT source, COUNT(*) AS cnt
                FROM price_history
                WHERE market_segment IS NULL
                  AND captured_at > now() - interval '24 hours'
                GROUP BY source
                ORDER BY cnt DESC
            """)).fetchall()
        if null_seg_rows:
            detail = "\n".join(f"  {r.source}: {r.cnt} rows" for r in null_seg_rows)
            send_discord_alert(
                "warning",
                "市场数据质量警告: market_segment IS NULL (24h内)",
                f"以下数据源写入了未分类的 price_history 行:\n{detail}\n"
                "信号引擎会过滤这些行 → 对应资产信号静默丢失。"
                "\n\n检查对应 ingest 路径，确认 market_segment='raw' 已设置。",
            )

        # Per-game signal breakdown — query asset_signals joined to assets,
        # grouped by game and label (INSUFFICIENT_DATA excluded as noise).
        #
        # Edge-case decisions:
        #   1. Game with zero actionable signals (all INSUFFICIENT_DATA): shows
        #      BREAKOUT=0 MOVE=0 WATCH=0 IDLE=0. Do NOT skip — the game exists.
        #   2. Game with no assets in DB at all: silently absent from GROUP BY
        #      result; skipped here too. Expected state for unseeded games.
        #   3. Unknown game value: included as-is using raw DB string, so no
        #      data is silently dropped from the breakdown line.
        per_game: dict[str, dict[str, int]] = {}
        with SessionLocal() as _sig_session:
            signal_rows = _sig_session.execute(
                select(Asset.game, AssetSignal.label, func.count().label("cnt"))
                .join(Asset, Asset.id == AssetSignal.asset_id)
                .where(AssetSignal.label != "INSUFFICIENT_DATA")
                .group_by(Asset.game, AssetSignal.label)
            ).all()
        for sig_row in signal_rows:
            game = sig_row.game
            if game not in per_game:
                per_game[game] = {"BREAKOUT": 0, "MOVE": 0, "WATCH": 0, "IDLE": 0}
            if sig_row.label in per_game[game]:
                per_game[game][sig_row.label] = sig_row.cnt

        lines = [f"{r.status}: {r.cnt} runs, last at {r.last_run}" for r in rows]
        game_parts = []
        for game_db, counts in sorted(per_game.items()):
            label = _GAME_DISPLAY_LABELS.get(game_db, game_db)
            game_parts.append(
                f"{label}: BREAKOUT={counts['BREAKOUT']} MOVE={counts['MOVE']} WATCH={counts['WATCH']} IDLE={counts['IDLE']}"
            )
        if game_parts:
            lines.append("Signals: " + " | ".join(game_parts))
        tag = " [观察期]" if in_observation else ""
        send_discord_alert(
            "heartbeat",
            f"Scheduler 健康{tag}",
            "\n".join(lines),
        )

    except Exception as exc:
        _exc = exc
        raise

    finally:
        log_status = "error" if _exc is not None else "success"
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status=log_status,
                meta_json=_log_meta,
                error_message=str(_exc) if _exc is not None else None,
            )
            prune_old_runs(_log_session, JOB_HEARTBEAT)


def _evaluate_alerts() -> None:
    logger.info("Alert evaluation tick started.")
    try:
        with SessionLocal() as session:
            result = process_alert_notifications(session)
        logger.info(
            "Alert evaluation finished. active_alerts_checked=%s triggered=%s price_movement_alerts_triggered=%s prediction_alerts_triggered=%s alerts_rearmed=%s notifications_sent=%s dm_delivery_failures=%s target_alerts_deactivated=%s",
            result.active_alerts_checked,
            result.triggered_alerts,
            result.price_movement_alerts_triggered,
            result.prediction_alerts_triggered,
            result.alerts_rearmed,
            result.notifications_sent,
            result.dm_delivery_failures,
            result.target_alerts_deactivated,
        )
    except Exception:
        logger.exception("Alert evaluation job failed.")


def _run_bulk_set_price_refresh() -> None:
    from scripts.import_pokemon_cards import (
        DEFAULT_BATCH_SIZE,
        PokemonTCGImporter,
        build_asset_payload,
        build_price_payload,
        flush_batch,
        price_history_available,
    )

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_BULK_REFRESH)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_BULK_REFRESH)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_BULK_REFRESH}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return

    _records_written = 0
    _errors = 0
    _error_message: str | None = None
    _meta_json: dict | None = None
    importer = None

    try:
        settings = get_settings()
        set_ids = settings.bulk_set_id_list
        if not set_ids:
            logger.info("Bulk set price refresh skipped because no set IDs are configured.")
            return

        importer = PokemonTCGImporter(api_key=None, limit=None)

        try:
            with SessionLocal() as session:
                can_record_prices = price_history_available(session)
                if not can_record_prices:
                    logger.warning(
                        "price_history model or table is unavailable; bulk set price refresh will skip price ingestion."
                    )

                asset_batch: list[dict[str, object]] = []
                price_batch: list[dict[str, object]] = []

                for set_id in set_ids:
                    if not settings.bulk_refresh_auto_import_new_sets:
                        existing_count = session.scalar(
                            select(func.count()).select_from(Asset)
                            .where(Asset.metadata_json["set_id"].as_string() == set_id)
                        )
                        if existing_count == 0:
                            logger.info(
                                "Bulk set price refresh skipping %s: no existing assets in DB. "
                                "Run scripts/import_pokemon_cards.py to import first, or set "
                                "BULK_REFRESH_AUTO_IMPORT_NEW_SETS=true to allow auto-import.",
                                set_id,
                            )
                            continue
                    logger.info("Bulk set price refresh fetching cards for set %s.", set_id)
                    cards = importer.fetch_cards_for_set(set_id)
                    if not cards:
                        logger.info("Bulk set price refresh received no cards for set %s.", set_id)
                        continue

                    importer.summary.sets_processed += 1
                    for card in cards:
                        asset_batch.append(build_asset_payload(card))
                        if can_record_prices:
                            price_payload = build_price_payload(
                                card,
                                captured_at=importer._run_captured_at,
                            )
                            if price_payload is not None:
                                price_batch.append(price_payload)

                        if len(asset_batch) >= DEFAULT_BATCH_SIZE:
                            cards_processed, prices_recorded = flush_batch(
                                session,
                                asset_payloads=asset_batch,
                                price_payloads=price_batch,
                            )
                            importer.summary.cards_processed += cards_processed
                            importer.summary.prices_recorded += prices_recorded
                            logger.info(
                                "Bulk set price refresh committed batch: assets_inserted=%s prices_recorded=%s total_seen=%s",
                                cards_processed,
                                prices_recorded,
                                importer.summary.cards_seen,
                            )
                            asset_batch.clear()
                            price_batch.clear()

                if asset_batch:
                    cards_processed, prices_recorded = flush_batch(
                        session,
                        asset_payloads=asset_batch,
                        price_payloads=price_batch,
                    )
                    importer.summary.cards_processed += cards_processed
                    importer.summary.prices_recorded += prices_recorded
                    logger.info(
                        "Bulk set price refresh committed final batch: assets_inserted=%s prices_recorded=%s total_seen=%s",
                        cards_processed,
                        prices_recorded,
                        importer.summary.cards_seen,
                    )
            _records_written = importer.summary.prices_recorded
            _meta_json = {
                "sets_processed": importer.summary.sets_processed,
                "cards_processed": importer.summary.cards_processed,
                "prices_recorded": importer.summary.prices_recorded,
            }
        finally:
            importer.close()

    except Exception as exc:
        _errors = 1
        _error_message = str(exc)
        _meta_json = {
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
            "sets_completed_before_failure": importer.summary.sets_processed if importer is not None else 0,
        }
        logger.exception("Bulk set price refresh job failed.")

    finally:
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status="success" if not _errors else "error",
                records_written=_records_written,
                errors=_errors,
                error_message=_error_message,
                meta_json=_meta_json,
            )
            prune_old_runs(_log_session, JOB_BULK_REFRESH)


def _run_scheduled_ingestion() -> None:
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_INGESTION)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_INGESTION)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_INGESTION}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return
    tracked_pools = get_tracked_pokemon_pools()
    implemented_providers = get_configured_provider_ingestors()
    run = ScheduledIngestionRun(started_at=datetime.now(UTC).replace(microsecond=0))

    logger.info("Scheduled ingestion run started. start_time=%s", run.started_at.isoformat())

    try:
        if not implemented_providers:
            run.errors.append("No configured ingestion providers are available.")
            logger.warning("Scheduled ingestion skipped because no configured ingestion providers are available.")
        if not tracked_pools:
            run.errors.append("No tracked Pokemon pools are configured.")
            logger.warning("Scheduled ingestion skipped because no tracked Pokemon pools are configured.")

        for provider_index, provider in enumerate(implemented_providers):
            for pool_index, pool in enumerate(tracked_pools):
                logger.info(
                    "Provider ingestion started [%s/%s]: slot=%s source=%s primary=%s",
                    provider.label,
                    pool.label,
                    provider.slot,
                    provider.source,
                    provider.is_primary,
                )
                try:
                    with SessionLocal() as session:
                        pool_result = provider.ingest_pool_cards(
                            session,
                            card_ids=pool.card_ids,
                            clear_sample_seed=(provider_index == 0 and pool_index == 0),
                        )
                except Exception as exc:
                    error_message = (
                        f"Provider ingestion failed for {provider.label}/{pool.label}: {exc}"
                    )
                    run.errors.append(error_message)
                    logger.exception(
                        "Provider ingestion failed [%s/%s]: slot=%s source=%s",
                        provider.label,
                        pool.label,
                        provider.slot,
                        provider.source,
                    )
                    continue

                run.records_written += pool_result.price_points_inserted
                run.card_failures += pool_result.cards_failed
                if pool_result.cards_failed:
                    run.errors.append(
                        f"{provider.label}/{pool.label}: {pool_result.cards_failed} card(s) failed during ingestion."
                    )

                logger.info(
                    "Provider ingestion finished [%s/%s]: slot=%s source=%s cards_requested=%s cards_processed=%s cards_failed=%s cards_skipped_no_price=%s assets_created=%s assets_updated=%s records_written=%s price_points_changed=%s price_points_unchanged=%s latest_captured_at=%s",
                    provider.label,
                    pool.label,
                    provider.slot,
                    provider.source,
                    pool_result.cards_requested,
                    pool_result.cards_processed,
                    pool_result.cards_failed,
                    pool_result.cards_skipped_no_price,
                    pool_result.assets_created,
                    pool_result.assets_updated,
                    pool_result.price_points_inserted,
                    pool_result.price_points_changed,
                    pool_result.price_points_unchanged,
                    pool_result.latest_captured_at.isoformat()
                    if pool_result.latest_captured_at
                    else "<none>",
                )

        _evaluate_alerts()
    finally:
        try:
            with SessionLocal() as session:
                run.gap_report = get_gap_report(session)
            _log_gap_report(run.gap_report)
        except Exception as exc:
            run.errors.append(f"Gap detection failed: {exc}")
            logger.exception("Gap detection after scheduled ingestion failed.")

        try:
            with SessionLocal() as session:
                run_backfill_pass(session)
        except Exception as exc:
            run.errors.append(f"Backfill pass failed: {exc}")
            logger.exception("Backfill pass after scheduled ingestion failed.")

        run.ended_at = datetime.now(UTC).replace(microsecond=0)
        logger.info(
            "Scheduled ingestion run finished. start_time=%s end_time=%s records_written=%s card_failures=%s errors=%s",
            run.started_at.isoformat(),
            run.ended_at.isoformat(),
            run.records_written,
            run.card_failures,
            run.errors if run.errors else "<none>",
        )
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status="success" if not run.errors else "error",
                records_written=run.records_written,
                errors=len(run.errors),
                error_message=run.errors[-1] if run.errors else None,
            )
            prune_old_runs(_log_session, JOB_INGESTION)


def _run_ebay_ingestion() -> EbayScheduledRunSummary:
    from backend.app.ingestion.ebay_sold import ingest_ebay_sold_cards
    from backend.app.models.asset import Asset as _Asset
    from sqlalchemy import select as _select

    settings = get_settings()

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_EBAY)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_EBAY)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_EBAY}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return EbayScheduledRunSummary(run_status="failed", job_blocked_reason="start_run_failed")

    _summary: EbayScheduledRunSummary | None = None

    try:
        if not settings.ebay_scheduled_ingest_enabled:
            ebay_logger.info("ebay_scheduled_ingest_skipped reason=disabled")
            _summary = EbayScheduledRunSummary(run_status="skipped", job_blocked_reason="disabled")
            return _summary

        if not settings.ebay_app_id or not settings.ebay_cert_id:
            ebay_logger.warning("ebay_scheduled_ingest_skipped reason=missing_credentials")
            _summary = EbayScheduledRunSummary(run_status="skipped", job_blocked_reason="missing_credentials")
            return _summary

        started_at = datetime.now(UTC).replace(microsecond=0)
        today_start_iso = started_at.replace(hour=0, minute=0, second=0).isoformat()
        deadline = started_at + JOB_WALL_CLOCK_LIMIT

        assets_considered = 0
        remaining_daily_budget = 0
        result = None
        assets_skipped_budget = 0

        try:
            with SessionLocal() as session:
                all_assets = list(session.scalars(_select(_Asset)).all())
                assets_considered = len(all_assets)

                # ── Daily budget: sum api_calls_used from completed runs today (UTC) ──
                # Counts actual API calls attempted, not just successful asset writes.
                _today_start = started_at.replace(hour=0, minute=0, second=0, microsecond=0)
                _today_runs = session.execute(
                    select(SchedulerRunLog)
                    .where(SchedulerRunLog.job_name == "ebay-ingestion")
                    .where(SchedulerRunLog.started_at >= _today_start)
                ).scalars().all()
                calls_today = sum(
                    (r.meta_json or {}).get("api_calls_used") or 0
                    for r in _today_runs
                )
                remaining_daily_budget = max(0, settings.ebay_daily_budget_limit - calls_today)
                effective_limit = min(settings.ebay_max_calls_per_run, remaining_daily_budget)

                if effective_limit <= 0:
                    ebay_logger.info(
                        "ebay_scheduled_ingest_skipped reason=daily_budget_exhausted "
                        "daily_budget=%s calls_today=%s",
                        settings.ebay_daily_budget_limit,
                        calls_today,
                    )
                    _summary = EbayScheduledRunSummary(
                        run_status="skipped",
                        assets_considered=assets_considered,
                        assets_skipped_budget=assets_considered,
                        budget_remaining=0,
                        job_blocked_reason="daily_budget_exhausted",
                    )
                    return _summary

                assets_skipped_budget = max(0, assets_considered - effective_limit)

                ebay_logger.info(
                    "ebay_scheduled_ingest_started start=%s assets_considered=%s "
                    "calls_today=%s remaining_daily_budget=%s effective_limit=%s",
                    started_at.isoformat(),
                    assets_considered,
                    calls_today,
                    remaining_daily_budget,
                    effective_limit,
                )

                # ── Priority ordering: tracked-pool assets first, then least-recently ingested ──
                tracked_pools = get_tracked_pokemon_pools()
                priority_external_ids: set[str] = set()
                for pool in tracked_pools:
                    priority_external_ids.update(pool.card_ids)

                def _sort_key(asset: _Asset) -> tuple[int, str]:
                    in_priority = int((asset.external_id or "") not in priority_external_ids)
                    last_ingested = (asset.metadata_json or {}).get("ebay_sold_last_ingested_at") or ""
                    return (in_priority, last_ingested)

                ordered_assets = sorted(all_assets, key=_sort_key)
                selected_ids = [
                    asset.external_id or str(asset.id)
                    for asset in ordered_assets[:effective_limit]
                ]

                result = ingest_ebay_sold_cards(session, card_ids=selected_ids, deadline=deadline)

        except Exception:
            ebay_logger.exception("ebay_scheduled_ingest_job_failed")
            _summary = EbayScheduledRunSummary(
                run_status="failed",
                assets_considered=assets_considered,
                errors=["Unhandled exception — see logs for details."],
                job_blocked_reason="exception",
            )
            return _summary

        ended_at = datetime.now(UTC).replace(microsecond=0)
        duration_s = (ended_at - started_at).total_seconds()
        api_calls_used = result.api_calls_used
        budget_remaining = max(0, remaining_daily_budget - api_calls_used)
        errors: list[str] = []
        if result.cards_failed:
            errors.append(f"{result.cards_failed} asset(s) failed during ingestion.")
        run_status = (
            "failed" if not result.cards_processed and result.cards_failed
            else "partial" if result.cards_failed
            else "warning" if result.api_calls_used == 0
            else "success"
        )

        _summary = EbayScheduledRunSummary(
            run_status=run_status,
            assets_considered=assets_considered,
            assets_processed=result.cards_processed,
            assets_skipped_budget=assets_skipped_budget,
            errors=errors,
            api_calls_used=api_calls_used,
            budget_remaining=budget_remaining,
            observations_fetched=result.observations_logged,
            matched=result.observations_matched,
            unmatched=result.observations_unmatched,
            price_points_inserted=result.price_points_inserted,
            duplicates_skipped=result.price_points_skipped_existing_timestamp,
            match_status_counts=dict(result.observation_match_status_counts),
            deadline_reached=result.deadline_reached,
            assets_remaining=result.assets_remaining,
        )

        ebay_logger.info(
            "ebay_scheduled_ingest_summary "
            "start=%s end=%s duration_s=%.1f "
            "run_status=%s assets_considered=%s assets_processed=%s assets_skipped_budget=%s "
            "api_calls_used=%s budget_remaining=%s "
            "observations_fetched=%s matched=%s unmatched=%s "
            "price_points_inserted=%s duplicates_skipped=%s "
            "errors=%s match_status=%s",
            started_at.isoformat(),
            ended_at.isoformat(),
            duration_s,
            _summary.run_status,
            _summary.assets_considered,
            _summary.assets_processed,
            _summary.assets_skipped_budget,
            _summary.api_calls_used,
            _summary.budget_remaining,
            _summary.observations_fetched,
            _summary.matched,
            _summary.unmatched,
            _summary.price_points_inserted,
            _summary.duplicates_skipped,
            _summary.errors or "<none>",
            _summary.match_status_counts,
        )
        return _summary

    finally:
        # Guaranteed on every exit path (disabled, budget_exhausted, exception, success)
        if _summary is None:
            log_status = "error"
            log_records = 0
            log_meta = None
            log_error_message: str | None = "Unhandled exception — see logs for details."
        elif _summary.run_status == "skipped":
            log_status = "success"
            log_records = 0
            log_meta = {"job_blocked_reason": _summary.job_blocked_reason}
            log_error_message = None
        elif _summary.job_blocked_reason == "exception":
            log_status = "error"
            log_records = 0
            log_meta = None
            log_error_message = _summary.errors[0] if _summary.errors else None
        else:
            log_status = _summary.run_status
            log_records = _summary.price_points_inserted
            log_meta = {
                "assets_processed": _summary.assets_processed,
                "api_calls_used": _summary.api_calls_used,
                "matched": _summary.matched,
                "unmatched": _summary.unmatched,
                "match_status_counts": _summary.match_status_counts,
                "deadline_reached": _summary.deadline_reached,
                "assets_remaining": _summary.assets_remaining,
            }
            log_error_message = _summary.errors[0] if _summary.errors else None
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status=log_status,
                records_written=log_records,
                meta_json=log_meta,
                error_message=log_error_message,
            )
            prune_old_runs(_log_session, JOB_EBAY)


def _run_ygo_ingestion() -> None:
    from backend.app.ingestion.ygo import ingest_ygo_sets

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_YGO)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_YGO)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_YGO}", f"error={exc}\nJob 已跳过，本次无 run_log 记录")
        return

    _records = 0
    _errors = 0
    _error_message: str | None = None

    try:
        with SessionLocal() as session:
            result = ingest_ygo_sets(session)
        _records = result.price_points_inserted
        if result.sets_failed:
            _errors = len(result.sets_failed)
            _error_message = f"Sets failed: {', '.join(result.sets_failed)}"
        logger.info(
            "yugioh_ingestion_complete assets_created=%s price_points=%s sets_failed=%s",
            result.assets_created, result.price_points_inserted, result.sets_failed,
        )
    except Exception as exc:
        _errors = 1
        _error_message = str(exc)
        logger.exception("yugioh_ingestion_failed")
    finally:
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status="success" if not _errors else "error",
                records_written=_records,
                errors=_errors,
                error_message=_error_message,
            )
            prune_old_runs(_log_session, JOB_YGO)


def _run_cardmarket_ingestion() -> None:
    from backend.app.ingestion.cardmarket import ingest_cardmarket_ygo
    from backend.app.models.scheduler_run_log import SchedulerRunLog

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_CARDMARKET)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_CARDMARKET)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_CARDMARKET}", f"error={exc}")
        return

    _records = 0
    _errors = 0
    _error_message: str | None = None
    _meta: dict = {}

    try:
        # Read last ETag from most recent successful run to enable 304 conditional fetch
        with SessionLocal() as _etag_db:
            last_run = _etag_db.execute(
                select(SchedulerRunLog)
                .where(SchedulerRunLog.job_name == JOB_CARDMARKET,
                       SchedulerRunLog.status == "success")
                .order_by(SchedulerRunLog.finished_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            last_etag = (last_run.meta_json or {}).get("catalog_etag") if last_run else None

        with SessionLocal() as session:
            result = ingest_cardmarket_ygo(session, last_etag=last_etag)
            if not result.skipped_not_modified:
                session.commit()
        _records = result.price_points_written
        _meta = {"catalog_etag": result.catalog_etag, "not_modified": result.skipped_not_modified}
        if result.skipped_not_modified:
            logger.info("cardmarket_ingestion_skipped_304 etag=%s", last_etag)
        else:
            logger.info(
                "cardmarket_ingestion_complete matched=%s no_match=%s no_price=%s written=%s",
                result.assets_matched, result.assets_skipped_no_match,
                result.assets_skipped_no_price, result.price_points_written,
            )
    except Exception as exc:
        _errors = 1
        _error_message = str(exc)
        logger.exception("cardmarket_ingestion_failed")
    finally:
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status="success" if not _errors else "error",
                records_written=_records,
                errors=_errors,
                error_message=_error_message,
                meta_json=_meta if _meta else None,
            )
            prune_old_runs(_log_session, JOB_CARDMARKET)


def _run_ebay_web_sold() -> None:
    from backend.app.ingestion.ebay_web_scrape import ingest_ebay_web_sold

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_EBAY_WEB_SOLD)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_EBAY_WEB_SOLD)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_EBAY_WEB_SOLD}", f"error={exc}")
        return

    _status = "error"
    _records = 0
    _errors = 0
    _error_message: str | None = None
    _meta: dict = {}

    try:
        with SessionLocal() as session:  # commit owned by ingest_ebay_web_sold internally
            result = ingest_ebay_web_sold(
                session,
                max_assets=get_settings().ebay_web_sold_max_assets_per_run,
            )

        if result.assets_skipped_http_error > 0:
            _status = "partial"
        elif result.price_points_written == 0:
            _status = "no_op"   # ran cleanly but no EN singles found — not an error
        else:
            _status = "success"
        _records = result.price_points_written
        _errors = result.assets_skipped_http_error
        _meta = {
            "assets_attempted": result.assets_attempted,
            "assets_written": result.assets_written,
            "assets_skipped_no_sales": result.assets_skipped_no_sales,
            "assets_skipped_http_error": result.assets_skipped_http_error,
            "http_error_counts": result.http_error_counts or {},
        }
    except Exception as exc:
        logger.exception("ebay_web_sold_failed")
        _errors = 1
        _error_message = str(exc)
        send_discord_alert("error", "ebay-web-sold job failed", "check logs")
    finally:
        with SessionLocal() as _log_session:
            finish_run(
                _log_session,
                _run_id,
                status=_status,
                records_written=_records,
                errors=_errors,
                error_message=_error_message,
                meta_json=_meta,
            )
            prune_old_runs(_log_session, JOB_EBAY_WEB_SOLD)


def _register_ebay_job(scheduler: BackgroundScheduler, settings: object) -> None:
    from backend.app.core.config import Settings

    s: Settings = settings  # type: ignore[assignment]
    if not s.ebay_scheduled_ingest_enabled:
        logger.info("eBay scheduled ingestion disabled — job not registered.")
        return
    if not s.ebay_app_id or not s.ebay_cert_id:
        logger.warning("eBay scheduled ingestion enabled but credentials missing — job not registered.")
        return

    scheduler.add_job(
        _run_ebay_ingestion,
        "interval",
        hours=24,
        id="ebay-ingestion",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,  # activated by prepare_scheduler_for_startup
    )
    logger.info(
        "eBay scheduled ingestion registered. trigger=interval/24h first_run=startup+%ds",
        _STARTUP_DELAY.get("ebay-ingestion", 660),
    )


def _run_resolve_predictions() -> None:
    """Resolve PENDING predictions whose resolution_date has passed.

    Interval: 4 hours. Startup offset: +660s (after signal-sweep so prices are fresh).
    Kill switch: RESOLVE_PREDICTIONS_ENABLED env var (default False — Category β).
    Kill switch reason: triggers Discord alerts to users and writes irreversible audit rows.

    For each eligible prediction:
      1. Fetch latest raw market price from price_history (market_segment='raw').
      2. Evaluate threshold_direction (above/below/within_band).
      3. Write HIT/MISS to predictions + predictions_audit.
      4. Send Discord embed with resolution summary.

    Predictions with no price data in the last 7 days are skipped (logged as warning).
    AMBIGUOUS/VOIDED statuses are out of scope for this scheduler — set manually.
    """
    from decimal import Decimal

    from sqlalchemy import select, text as sa_text

    from backend.app.models.predictions import Prediction, PredictionAudit
    from backend.app.services.prediction_service import resolve_prediction

    settings = get_settings()

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_RESOLVE)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_RESOLVE)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_RESOLVE}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _resolved = 0
    _skipped_no_price = 0
    _errors = 0
    _eligible = 0
    _error_message: str | None = None
    _exc: BaseException | None = None

    try:
        if not getattr(settings, "resolve_predictions_enabled", False):
            logger.info("resolve_predictions_skipped reason=kill_switch")
            # finish_run in finally will log status=success with skipped=True
            _error_message = None  # clean exit
            return

        now = datetime.now(UTC)

        with SessionLocal() as session:
            pending = session.scalars(
                select(Prediction).where(
                    Prediction.resolution_status == "PENDING",
                    Prediction.resolution_date <= now,
                )
            ).all()

        _eligible = len(pending)
        logger.info("resolve_predictions_tick eligible=%d", _eligible)

        for prediction in pending:
            try:
                # Fetch latest raw price within the last 7 days
                with SessionLocal() as session:
                    row = session.execute(
                        sa_text("""
                            SELECT price
                            FROM price_history
                            WHERE asset_id = :asset_id
                              AND market_segment = 'raw'
                              AND captured_at >= NOW() - INTERVAL '7 days'
                            ORDER BY captured_at DESC
                            LIMIT 1
                        """),
                        {"asset_id": str(prediction.asset_id)},
                    ).fetchone()

                if row is None:
                    logger.warning(
                        "resolve_predictions_no_price prediction_id=%s asset_id=%s",
                        prediction.id, prediction.asset_id,
                    )
                    _skipped_no_price += 1
                    continue

                actual_value = Decimal(str(row.price))

                with SessionLocal() as session:
                    result = resolve_prediction(
                        session,
                        prediction_id=prediction.id,
                        actual_value=actual_value,
                        resolved_at=now,
                    )

                _resolved += 1
                logger.info(
                    "resolve_predictions_resolved id=%s status=%s actual=%.2f threshold=%.2f direction=%s",
                    prediction.id, result.resolution_status, actual_value,
                    prediction.threshold_value, prediction.threshold_direction,
                )

                # Discord embed per resolution
                icon = "✅" if result.resolution_status == "HIT" else "❌"
                paper_tag = " [PAPER]" if prediction.is_paper else ""
                send_discord_alert(
                    "success" if result.resolution_status == "HIT" else "warning",
                    f"{icon} Prediction {result.resolution_status}{paper_tag}",
                    f"Prediction resolved: {prediction.prediction_text[:120]}\n"
                    f"Stated probability: {float(prediction.stated_probability):.0%} → "
                    f"Actual: ${actual_value:.2f} | "
                    f"Threshold: ${float(prediction.threshold_value):.2f} {prediction.threshold_direction}\n"
                    f"Driver: {prediction.driver_attribution or 'N/A'} | "
                    f"ID: {str(prediction.id)[:8]}",
                )

            except Exception as exc:
                _errors += 1
                _error_message = str(exc)
                logger.exception(
                    "resolve_predictions_error prediction_id=%s error=%s",
                    prediction.id, exc,
                )

    except BaseException as exc:
        _exc = exc
        _error_message = str(exc)
        raise

    finally:
        log_status = (
            "error" if (_exc is not None or (_errors > 0 and _resolved == 0))
            else "partial" if _errors > 0
            else "success"
        )
        meta = {
            "resolved": _resolved,
            "skipped_no_price": _skipped_no_price,
            "errors": _errors,
            "eligible": _eligible,
            "kill_switch_off": not getattr(settings, "resolve_predictions_enabled", False),
        }
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status=log_status,
                records_written=_resolved,
                errors=_errors,
                error_message=_error_message,
                meta_json=meta,
            )
            prune_old_runs(_log_session, JOB_RESOLVE)


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    tracked_pools = get_tracked_pokemon_pools()
    configured_providers = get_configured_price_providers()
    pending_providers = get_unimplemented_configured_providers()
    pool_card_counts = (
        ", ".join(f"{pool.label}={len(pool.card_ids)}" for pool in tracked_pools)
        if tracked_pools
        else "<none>"
    )
    provider_slots = (
        ", ".join(
            f"{provider.slot}={provider.source}{' (primary)' if provider.is_primary else ''}"
            for provider in configured_providers
        )
        if configured_providers
        else "<none>"
    )

    logger.info(
        "Resolved backstage scheduler config: INGEST_SCHEDULE_ENABLED=%s, INGEST_INTERVAL_HOURS=%s, GAP_HISTORY_THRESHOLD=%s, GAP_SET_COVERAGE_THRESHOLD=%s, SCHEDULER_POLL_SECONDS=%s, TRACKED_POOL_CARD_COUNTS=%s, CONFIGURED_PROVIDERS=%s, PRIMARY_PRICE_SOURCE=%s",
        settings.resolved_ingest_schedule_enabled,
        settings.resolved_ingest_interval_hours,
        settings.gap_history_threshold,
        settings.gap_set_coverage_threshold,
        settings.scheduler_poll_seconds,
        pool_card_counts,
        provider_slots,
        get_primary_price_source(),
    )
    if pending_providers:
        logger.info(
            "Configured provider slots without an ingestion implementation yet: %s",
            ", ".join(f"{provider.slot}={provider.source}" for provider in pending_providers),
        )

    if settings.resolved_ingest_schedule_enabled:
        logger.info(
            "Scheduled ingestion enabled. Interval=%s hours (%s seconds), max_instances=1.",
            settings.resolved_ingest_interval_hours,
            settings.resolved_ingest_interval_seconds,
        )
        scheduler.add_job(
            _run_scheduled_ingestion,
            "interval",
            seconds=settings.resolved_ingest_interval_seconds,
            id="scheduled-ingestion",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
        if settings.bulk_set_id_list:
            scheduler.add_job(
                _run_bulk_set_price_refresh,
                "interval",
                seconds=settings.resolved_ingest_interval_seconds,
                id="bulk-set-price-refresh",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=None,
            )
        scheduler.add_job(
            _run_signal_sweep,
            "interval",
            seconds=settings.signal_sweep_interval_seconds,
            id="signal-sweep",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
        scheduler.add_job(
            _run_retry_pass,
            "interval",
            hours=6,
            id="retry-pass",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )

    else:
        logger.info(
            "Scheduled ingestion disabled. Falling back to alert evaluation every %s seconds.",
            settings.scheduler_poll_seconds,
        )
        scheduler.add_job(
            _evaluate_alerts,
            "interval",
            seconds=settings.scheduler_poll_seconds,
            id="alert-poller",
            replace_existing=True,
        )
        scheduler.add_job(
            _run_signal_sweep,
            "interval",
            seconds=settings.signal_sweep_interval_seconds,
            id="signal-sweep",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    # Heartbeat — always registered, regardless of ingestion mode
    scheduler.add_job(
        _send_heartbeat,
        "interval",
        seconds=600,  # 10 min; function throttles actual sends based on mode
        id="alert-heartbeat",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )

    _register_ebay_job(scheduler, settings)

    scheduler.add_job(
        _run_ygo_ingestion,
        "interval",
        hours=6,
        id="yugioh-ingestion",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )

    if settings.cardmarket_ingest_enabled:
        scheduler.add_job(
            _run_cardmarket_ingestion,
            "interval",
            hours=24,
            id=JOB_CARDMARKET,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
        logger.info(
            "CardMarket ingestion registered. trigger=interval/24h first_run=startup+%ds",
            _STARTUP_DELAY.get(JOB_CARDMARKET, 1050),
        )

    if settings.ebay_web_sold_enabled:
        scheduler.add_job(
            _run_ebay_web_sold,
            "interval",
            hours=24,
            id=JOB_EBAY_WEB_SOLD,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
        logger.info(
            "ebay-web-sold registered. trigger=interval/24h first_run=startup+%ds",
            _STARTUP_DELAY.get(JOB_EBAY_WEB_SOLD, 870),
        )

    scheduler.add_job(
        _run_explanation_sweep,
        "interval",
        hours=6,
        id="explanation-sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )

    scheduler.add_job(
        _send_market_digests,
        "interval",
        minutes=30,
        id="market-digest-send",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )
    logger.info(
        "Market Digest job registered. trigger=interval/30min first_run=startup+%ds",
        _STARTUP_DELAY.get("market-digest-send", 1200),
    )

    scheduler.add_job(
        _run_signal_history_prune,
        "interval",
        hours=24,
        id="signal-history-prune",
        replace_existing=True,
        max_instances=1,
        next_run_time=None,
    )
    logger.info(
        "signal-history-prune registered. trigger=interval/24h first_run=startup+%ds",
        _STARTUP_DELAY.get("signal-history-prune", 1500),
    )

    scheduler.add_job(
        _scheduled_trial_expiry_sweep,
        "interval",
        hours=6,
        id="trial-expiry-sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )
    logger.info(
        "trial-expiry-sweep registered. trigger=interval/6h first_run=startup+%ds",
        _STARTUP_DELAY.get("trial-expiry-sweep", 900),
    )

    scheduler.add_job(
        _scheduled_sealed_ingest,
        "interval",
        hours=6,
        id="sealed-ingest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )
    logger.info(
        "sealed-ingest registered. trigger=interval/6h first_run=startup+%ds",
        _STARTUP_DELAY.get("sealed-ingest", 840),
    )

    scheduler.add_job(
        _run_backup_freshness_check,
        "interval",
        hours=4,
        id="backup-freshness-check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )
    logger.info(
        "backup-freshness-check registered. trigger=interval/4h first_run=startup+%ds",
        _STARTUP_DELAY.get("backup-freshness-check", 15000),
    )

    # Category β kill switch: default off. Set RESOLVE_PREDICTIONS_ENABLED=true
    # only after Gate 4 (7-day staging validation) passes per quality-gates.md.
    if getattr(settings, "resolve_predictions_enabled", False):
        scheduler.add_job(
            _run_resolve_predictions,
            "interval",
            hours=4,
            id="resolve-predictions",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
        logger.info(
            "resolve-predictions registered. trigger=interval/4h first_run=startup+%ds",
            _STARTUP_DELAY.get("resolve-predictions", 660),
        )
    else:
        logger.info("resolve-predictions disabled — set RESOLVE_PREDICTIONS_ENABLED=true after Gate 4.")

    return scheduler


def _run_explanation_sweep() -> None:
    """Generate AI explanations for all stale non-INSUFFICIENT_DATA signals."""
    from backend.app.services.signal_explainer import bulk_generate_explanations

    with SessionLocal() as db:
        run_id = start_run(db, "explanation-sweep")
        try:
            written = bulk_generate_explanations(db)
            finish_run(db, run_id, status="success", records_written=written)
        except Exception as exc:
            with SessionLocal() as err_db:
                finish_run(err_db, run_id, status="error", error_message=str(exc))
            logger.exception("explanation-sweep failed")
        finally:
            with SessionLocal() as prune_db:
                prune_old_runs(prune_db, "explanation-sweep")


def _send_market_digests() -> None:
    """Market Digest job — fires every 30 min, executes only in 06:45–07:15 UTC window.

    Idempotency:
      Gate 1: time-window check (06:45–07:15 UTC)
      Gate 2: job-level dedupe (any send today → skip)
    """
    import time as _time_module
    from datetime import time as _time
    from backend.app.services.market_digest import (
        DRY_RUN,
        get_digest_candidates,
        get_or_generate_explanation,
        resolve_subscribers,
        send_digest,
        should_send_digest,
    )
    from backend.app.models.user import User
    from sqlalchemy import select, text as sa_text

    with SessionLocal() as db:
        run_id = start_run(db, JOB_DIGEST)
        try:
            now_utc = datetime.now(UTC)
            t = now_utc.time()

            # Gate 1: only execute in the 06:45–07:15 UTC window
            if not (_time(6, 45) <= t <= _time(7, 15)):
                finish_run(db, run_id, status="no_op",
                           meta_json={"reason": "outside_send_window",
                                      "current_utc": t.isoformat()})
                return

            # Gate 2: job-level dedupe — skip if any send completed today
            today_utc = now_utc.date()
            existing = db.execute(
                sa_text("SELECT 1 FROM digest_send_log WHERE sent_at::date = :d LIMIT 1"),
                {"d": today_utc},
            ).fetchone()
            if existing:
                finish_run(db, run_id, status="no_op",
                           meta_json={"reason": "already_sent_today",
                                      "date": today_utc.isoformat()})
                return

            # Build today's candidate cards (shared across all users)
            candidates = get_digest_candidates(db, today_utc)
            has_signals = any(c.signal_type in ("BREAKOUT", "MOVE") for c in candidates)

            if not candidates:
                finish_run(db, run_id, status="no_op",
                           meta_json={"reason": "insufficient_content"})
                return

            # Populate explanations
            for card in candidates:
                card.explanation = get_or_generate_explanation(
                    db,
                    card.asset_id,
                    card.signal_type,
                    today_utc,
                    card.name,
                    card.price_delta_pct,
                )

            # Resolve subscriber list (dry-run: operator only; normal: all active paid users)
            subscribers = resolve_subscribers(db)
            if subscribers is None:
                finish_run(db, run_id, status="no_op",
                           meta_json={"reason": "dry_run_user_not_found"})
                return

            sent_count = 0
            fail_count = 0

            for user in subscribers:
                trigger_type = "event" if has_signals else "weekly_fallback"
                if not should_send_digest(user, today_utc, has_signals=has_signals):
                    continue
                try:
                    send_digest(db, user, candidates, trigger_type, today_utc)
                    sent_count += 1
                except Exception as e:
                    logger.error("digest_batch_error user=%s error=%s", getattr(user, "id", "?"), e)
                    fail_count += 1
                _time_module.sleep(0.2)

            status = "success" if fail_count == 0 else ("partial" if sent_count > 0 else "error")
            finish_run(db, run_id, status=status, records_written=sent_count,
                       errors=fail_count,
                       meta_json={"sent": sent_count, "failed": fail_count,
                                  "dry_run": DRY_RUN})
        except Exception as e:
            finish_run(db, run_id, status="error", error_message=str(e))
            logger.exception("market-digest-send job failed: %s", e)
        finally:
            prune_old_runs(db, JOB_DIGEST)


def _run_trial_expiry_sweep(session: Session) -> int:
    """Downgrade users whose 14-day trial has expired.

    Pure function: takes a session, returns the count of users downgraded.
    Sets subscription_status='expired' and access_tier='free' for every user
    whose subscription_status is 'trialing' and trial_ends_at is in the past.
    Also sends a conversion email to users whose trial expires within 48h.
    """
    from backend.app.models.user import User
    now = datetime.now(UTC)

    # Send conversion emails to users whose trial expires within 48h (sweep runs every 6h)
    settings = get_settings()
    app_url = settings.app_url or "https://flashcard-planet.up.railway.app"
    warning_candidates = session.execute(
        select(User).where(
            User.subscription_status == "trialing",
            User.trial_ends_at.isnot(None),
            User.trial_ends_at > now,
            User.trial_ends_at <= now + timedelta(hours=48),
        )
    ).scalars().all()
    for user in warning_candidates:
        try:
            from backend.app.email.resend_client import send_trial_expiring_soon_email
            send_trial_expiring_soon_email(
                user.email,
                user.trial_ends_at.strftime("%B %d, %Y"),
                app_url=app_url,
            )
        except Exception:
            logger.warning("trial_expiry_email_failed user_id=%s", user.id)

    # Downgrade expired trials
    expired_users = session.execute(
        select(User).where(
            User.subscription_status == "trialing",
            User.trial_ends_at.isnot(None),
            User.trial_ends_at < now,
        )
    ).scalars().all()
    count = 0
    for user in expired_users:
        user.subscription_status = "expired"
        user.access_tier = "free"
        count += 1
    if count > 0:
        session.flush()
    return count


def _scheduled_trial_expiry_sweep() -> None:
    """Scheduled wrapper for _run_trial_expiry_sweep.

    Runs every 6 hours. Downgrades users whose trial has expired,
    writing a scheduler_run_log row on every exit path.
    """
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_TRIAL_EXPIRY)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_TRIAL_EXPIRY)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_TRIAL_EXPIRY}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _exc: BaseException | None = None
    _log_meta: dict | None = None

    try:
        with SessionLocal() as session:
            count = _run_trial_expiry_sweep(session)
            session.commit()

        _log_meta = {"users_downgraded": count}
        logger.info(
            "trial-expiry-sweep complete: users_downgraded=%d",
            count,
        )
    except BaseException as exc:
        _exc = exc
        raise
    finally:
        if _exc is not None:
            log_status = "error"
        elif (_log_meta or {}).get("users_downgraded", 0) == 0:
            log_status = "no_op"  # expected when no trials are expiring; not a zero-output failure
        else:
            log_status = "success"
        try:
            with SessionLocal() as _log_session:
                finish_run(
                    _log_session, _run_id,
                    status=log_status,
                    records_written=_log_meta["users_downgraded"] if _log_meta else 0,
                    meta_json=_log_meta,
                    error_message=str(_exc) if _exc is not None else None,
                )
                prune_old_runs(_log_session, JOB_TRIAL_EXPIRY)
        except Exception:
            logger.exception(
                "finish_run_failed job=%s run_id=%s",
                JOB_TRIAL_EXPIRY, _run_id,
            )


def _scheduled_sealed_ingest() -> None:
    """Sealed product from-price ingest via eBay Browse API (every 6h).

    Polls 20 manually curated sealed products defined in sealed_products.json.
    Writes listing_snapshot rows (ask prices — NOT price_history per CLAUDE.md).
    Upserts Asset rows with asset_class=SEALED on first run.
    """
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_SEALED_INGEST)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_SEALED_INGEST)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_SEALED_INGEST}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _exc: BaseException | None = None
    _log_meta: dict | None = None

    try:
        from backend.app.ingestion.sealed_browse_client import run_sealed_ingest
        with SessionLocal() as session:
            _log_meta = run_sealed_ingest(session)
        snapshots = _log_meta.get("snapshots_written", 0)
        failed = _log_meta.get("products_failed", 0)
        logger.info(
            "sealed-ingest complete: snapshots=%d failed=%d",
            snapshots, failed,
        )
    except BaseException as exc:
        _exc = exc
        raise
    finally:
        log_status = "error" if _exc is not None else (
            "partial" if (_log_meta or {}).get("products_failed", 0) > 0 else "success"
        )
        records = (_log_meta or {}).get("snapshots_written", 0)
        try:
            with SessionLocal() as _log_session:
                finish_run(
                    _log_session, _run_id,
                    status=log_status,
                    records_written=records,
                    meta_json=_log_meta,
                    error_message=str(_exc) if _exc is not None else None,
                )
                prune_old_runs(_log_session, JOB_SEALED_INGEST)
        except Exception:
            logger.exception(
                "finish_run_failed job=%s run_id=%s",
                JOB_SEALED_INGEST, _run_id,
            )


def _run_backup_freshness_check() -> None:
    """Backup freshness watchdog: verifies the GitHub Actions backup ran within the last 30h.

    Fires every 4h (interval trigger). 4h cadence caps detection latency regardless
    of deploy time — a fixed daily delay could fire before the 04:00 UTC backup if
    Railway deploys during 00:00-01:50 UTC, delaying detection to the second day.
    Alerts Discord if the latest backup is stale or the check errors.

    Calls scripts/check_backup_freshness.py::check_backup_freshness() which
    hits the GitHub Releases API for ivancjz/flashcard-planet-backups and
    verifies the most recent release is younger than BACKUP_MAX_AGE_HOURS.

    # PR #14b: migrate this module to structlog once structlog is adopted in the codebase.
    """
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_BACKUP_FRESHNESS)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_BACKUP_FRESHNESS)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_BACKUP_FRESHNESS}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _exc: BaseException | None = None
    _exit_code: int = 0
    _meta: dict = {}

    try:
        from scripts.check_backup_freshness import check_backup_freshness
        _exit_code, _meta = check_backup_freshness()
        if _exit_code != 0:
            send_discord_alert(
                "error",
                "⚠️ Backup freshness check FAILED",
                f"latest backup is stale or check errored\nmeta={_meta}",
            )
    except BaseException as exc:
        _exc = exc
        send_discord_alert(
            "error",
            "⚠️ Backup freshness check 崩溃",
            f"error={exc}\n需要立即调查。",
        )
        raise
    finally:
        log_status = "error" if (_exc is not None or _exit_code != 0) else "success"
        try:
            with SessionLocal() as _log_session:
                finish_run(
                    _log_session, _run_id,
                    status=log_status,
                    records_written=0,
                    error_message=str(_exc) if _exc is not None else (
                        _meta.get("error_reason") or f"exit_code={_exit_code}"
                        if _exit_code != 0 else None
                    ),
                    meta_json=_meta if _meta else None,
                )
                prune_old_runs(_log_session, JOB_BACKUP_FRESHNESS)
        except Exception:
            logger.exception(
                "finish_run_failed job=%s run_id=%s",
                JOB_BACKUP_FRESHNESS, _run_id,
            )


def _run_signal_history_prune() -> None:
    """Daily DELETE of asset_signal_history rows older than the retention window.

    Phase 2 of Issue D fix (Phase 1 = transition guard in commit 78bd30b).
    Steady-state row count ≈ retention_days × post-fix daily transition rate
    (~1500 rows/day as of 2026-05-08).

    Pre-fix repeat rows age out naturally as computed_at crosses the retention
    boundary. For immediate pre-fix bulk cleanup, see PR-B (TASK-106).
    """
    settings = get_settings()

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_HISTORY_PRUNE)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_HISTORY_PRUNE)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_HISTORY_PRUNE}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _exc: BaseException | None = None
    _log_meta: dict | None = None

    try:
        retention_days = settings.signal_history_retention_days
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        with SessionLocal() as session:
            result = session.execute(
                sa_text("DELETE FROM asset_signal_history WHERE computed_at < :cutoff"),
                {"cutoff": cutoff},
            )
            session.commit()
            rows_deleted = result.rowcount or 0

            oldest_remaining = session.execute(
                sa_text("SELECT MIN(computed_at) FROM asset_signal_history")
            ).scalar()

        _log_meta = {
            "retention_days_applied": retention_days,
            "rows_deleted": rows_deleted,
            "oldest_remaining_at": (
                oldest_remaining.isoformat()
                if oldest_remaining and hasattr(oldest_remaining, "isoformat")
                else str(oldest_remaining) if oldest_remaining else None
            ),
        }
        logger.info(
            "signal-history-prune complete: deleted=%d retention_days=%d oldest_remaining=%s",
            rows_deleted, retention_days, oldest_remaining,
        )
    except BaseException as exc:
        _exc = exc
        raise
    finally:
        log_status = "error" if _exc is not None else "success"
        try:
            with SessionLocal() as _log_session:
                finish_run(
                    _log_session, _run_id,
                    status=log_status,
                    meta_json=_log_meta,
                    error_message=str(_exc) if _exc is not None else None,
                )
                prune_old_runs(_log_session, JOB_HISTORY_PRUNE)
        except Exception:
            logger.exception(
                "finish_run_failed job=%s run_id=%s",
                JOB_HISTORY_PRUNE, _run_id,
            )


def prepare_scheduler_for_startup(
    scheduler: BackgroundScheduler,
    *,
    now: datetime | None = None,
) -> None:
    """Resume all paused jobs at startup with staggered first runs.

    Each job gets a distinct first_run_time to avoid a thundering-herd
    at process start.  Jobs not registered (e.g. bulk-set-price-refresh
    when no bulk set IDs are configured) are skipped with a warning.
    """
    now = now or datetime.now(UTC)
    resumed: list[str] = []
    for job_id, delay_seconds in _STARTUP_DELAY.items():
        job = scheduler.get_job(job_id)
        if job is None:
            logger.warning("prepare_scheduler_for_startup: job %r not found — skipping", job_id)
            continue
        first_run = now + timedelta(seconds=delay_seconds)
        scheduler.modify_job(job_id, next_run_time=first_run)
        logger.info(
            "Resumed job %r, first run at %s (+%ds)",
            job_id, first_run.isoformat(), delay_seconds,
        )
        resumed.append(job_id)
    logger.info("prepare_scheduler_for_startup complete. resumed=%s", resumed)
