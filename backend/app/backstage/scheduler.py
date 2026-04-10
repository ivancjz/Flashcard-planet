from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.backstage.gap_detector import GapReport, get_gap_report
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
from backend.app.services.alert_service import process_alert_notifications
from backend.app.services.signal_service import sweep_signals

logger = logging.getLogger(__name__)
INITIAL_INGEST_DELAY_SECONDS = 10


@dataclass
class ScheduledIngestionRun:
    started_at: datetime
    ended_at: datetime | None = None
    records_written: int = 0
    card_failures: int = 0
    errors: list[str] = field(default_factory=list)
    gap_report: GapReport | None = None


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


def _run_signal_sweep() -> None:
    logger.info("Signal sweep tick started.")
    try:
        with SessionLocal() as session:
            result = sweep_signals(session)
        logger.info(
            "Signal sweep finished. total=%s breakout=%s move=%s watch=%s idle=%s errors=%s duration_ms=%.1f",
            result.total, result.breakout, result.move, result.watch,
            result.idle, result.errors, result.duration_ms,
        )
    except Exception:
        logger.exception("Signal sweep job failed.")


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

        run.ended_at = datetime.now(UTC).replace(microsecond=0)
        logger.info(
            "Scheduled ingestion run finished. start_time=%s end_time=%s records_written=%s card_failures=%s errors=%s",
            run.started_at.isoformat(),
            run.ended_at.isoformat(),
            run.records_written,
            run.card_failures,
            run.errors if run.errors else "<none>",
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
        return scheduler

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
    return scheduler


def prepare_scheduler_for_startup(scheduler: BackgroundScheduler) -> None:
    job = scheduler.get_job("scheduled-ingestion")
    bulk_job = scheduler.get_job("bulk-set-price-refresh")
    if job is None and bulk_job is None:
        return

    first_run_at = datetime.now(UTC) + timedelta(seconds=INITIAL_INGEST_DELAY_SECONDS)
    if job is not None:
        scheduler.modify_job("scheduled-ingestion", next_run_time=first_run_at)
    if bulk_job is not None:
        scheduler.modify_job("bulk-set-price-refresh", next_run_time=first_run_at)
    logger.info(
        "Initial scheduled ingestion delayed until %s (%s seconds after startup).",
        first_run_at.isoformat(),
        INITIAL_INGEST_DELAY_SECONDS,
    )
