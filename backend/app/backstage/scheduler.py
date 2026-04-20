from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.backstage.gap_detector import GapReport, get_gap_report
from backend.app.ingestion.pokemon_tcg import backfill_single_card, run_backfill_pass
from backend.app.services.backfill_retry_service import run_retry_pass
from backend.app.services.scheduler_run_log_service import (
    JOB_INGESTION,
    JOB_RETRY,
    JOB_SIGNALS,
    finish_run,
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
from sqlalchemy import text as sa_text

from backend.app.alerting.discord import send_discord_alert
from backend.app.services.alert_service import process_alert_notifications
from backend.app.services.signal_service import sweep_signals

logger = logging.getLogger(__name__)
ebay_logger = logging.getLogger("backend.app.ingestion.ebay_scheduled")
_STARTUP_DELAY: dict[str, int] = {
    "scheduled-ingestion":    120,   # 2 min
    "bulk-set-price-refresh": 300,   # 5 min
    "signal-sweep":           600,   # 10 min
    "alert-heartbeat":        720,   # 12 min — receives first sweep result before sending
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
    with SessionLocal() as _log_session:
        _run_id = start_run(_log_session, JOB_SIGNALS)
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
    with SessionLocal() as _log_session:
        _run_id = start_run(_log_session, JOB_RETRY)
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


def _send_heartbeat() -> None:
    """Send a periodic health pulse to Discord.

    The job runs every 10 minutes.  Actual send frequency depends on mode:
      - Observation mode (deploy_observation_mode_until is set and in the future):
        every 10 minutes so you can watch the first few sweeps closely.
      - Normal mode: only once per hour (minute 0–9 window).
    """
    settings = get_settings()
    if not settings.alert_heartbeat_enabled:
        return

    now = datetime.now(UTC)

    # Parse observation-mode deadline
    observation_until: datetime | None = None
    raw = settings.deploy_observation_mode_until
    if raw:
        try:
            observation_until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Invalid DEPLOY_OBSERVATION_MODE_UNTIL: %r", raw)

    in_observation = observation_until is not None and now < observation_until

    # Normal mode: only send during the first 10 minutes of each hour
    if not in_observation and now.minute >= 10:
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

    lines = [f"{r.status}: {r.cnt} runs, last at {r.last_run}" for r in rows]
    tag = " [观察期]" if in_observation else ""
    send_discord_alert(
        "heartbeat",
        f"Scheduler 健康{tag}",
        "\n".join(lines),
    )


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
        finally:
            importer.close()
    except Exception:
        logger.exception("Bulk set price refresh job failed.")


def _run_scheduled_ingestion() -> None:
    with SessionLocal() as _log_session:
        _run_id = start_run(_log_session, JOB_INGESTION)
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

    if not settings.ebay_scheduled_ingest_enabled:
        ebay_logger.info("ebay_scheduled_ingest_skipped reason=disabled")
        return EbayScheduledRunSummary(run_status="skipped", job_blocked_reason="disabled")

    if not settings.ebay_app_id or not settings.ebay_cert_id:
        ebay_logger.warning("ebay_scheduled_ingest_skipped reason=missing_credentials")
        return EbayScheduledRunSummary(run_status="skipped", job_blocked_reason="missing_credentials")

    started_at = datetime.now(UTC).replace(microsecond=0)
    today_start_iso = started_at.replace(hour=0, minute=0, second=0).isoformat()

    assets_considered = 0
    remaining_daily_budget = 0
    result = None

    try:
        with SessionLocal() as session:
            all_assets = list(session.scalars(_select(_Asset)).all())
            assets_considered = len(all_assets)

            # ── Daily budget: count assets already ingested since 00:00 UTC ──
            calls_today = sum(
                1 for a in all_assets
                if (a.metadata_json or {}).get("ebay_sold_last_ingested_at", "") >= today_start_iso
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
                return EbayScheduledRunSummary(
                    run_status="skipped",
                    assets_considered=assets_considered,
                    assets_skipped_budget=assets_considered,
                    budget_remaining=0,
                    job_blocked_reason="daily_budget_exhausted",
                )

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

            result = ingest_ebay_sold_cards(session, card_ids=selected_ids)

    except Exception:
        ebay_logger.exception("ebay_scheduled_ingest_job_failed")
        return EbayScheduledRunSummary(
            run_status="failed",
            assets_considered=assets_considered,
            errors=["Unhandled exception — see logs for details."],
            job_blocked_reason="exception",
        )

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
        else "success"
    )

    summary = EbayScheduledRunSummary(
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
        summary.run_status,
        summary.assets_considered,
        summary.assets_processed,
        summary.assets_skipped_budget,
        summary.api_calls_used,
        summary.budget_remaining,
        summary.observations_fetched,
        summary.matched,
        summary.unmatched,
        summary.price_points_inserted,
        summary.duplicates_skipped,
        summary.errors or "<none>",
        summary.match_status_counts,
    )
    return summary


def _register_ebay_job(scheduler: BackgroundScheduler, settings: object) -> None:
    from backend.app.core.config import Settings

    s: Settings = settings  # type: ignore[assignment]
    if not s.ebay_scheduled_ingest_enabled:
        logger.info("eBay scheduled ingestion disabled — job not registered.")
        return
    if not s.ebay_app_id or not s.ebay_cert_id:
        logger.warning("eBay scheduled ingestion enabled but credentials missing — job not registered.")
        return

    try:
        minute, hour, day, month, day_of_week = s.ebay_ingest_cron.split()
    except ValueError:
        logger.error(
            "Invalid EBAY_INGEST_CRON value %r — expected 5-field cron expression. Job not registered.",
            s.ebay_ingest_cron,
        )
        return

    effective_limit = min(s.ebay_max_calls_per_run, s.ebay_daily_budget_limit)
    scheduler.add_job(
        _run_ebay_ingestion,
        "cron",
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        id="ebay-ingestion",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "eBay scheduled ingestion registered. cron=%r effective_limit=%s (max_calls_per_run=%s daily_budget=%s)",
        s.ebay_ingest_cron,
        effective_limit,
        s.ebay_max_calls_per_run,
        s.ebay_daily_budget_limit,
    )


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
    return scheduler


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
