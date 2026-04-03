import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.core.config import get_settings
from backend.app.core.price_sources import get_configured_price_providers, get_primary_price_source
from backend.app.core.tracked_pools import get_tracked_pokemon_pools
from backend.app.db.session import SessionLocal
from backend.app.ingestion.provider_registry import (
    get_configured_provider_ingestors,
    get_unimplemented_configured_providers,
)
from backend.app.services.alert_service import process_alert_notifications
from backend.app.services.data_health_service import get_data_health_report

logger = logging.getLogger(__name__)


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    tracked_pools = get_tracked_pokemon_pools()
    configured_providers = get_configured_price_providers()
    implemented_providers = get_configured_provider_ingestors()
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
        "Resolved scheduler config: POKEMON_TCG_SCHEDULE_ENABLED=%s, POKEMON_TCG_SCHEDULE_SECONDS=%s, SCHEDULER_POLL_SECONDS=%s, TRACKED_POOL_CARD_COUNTS=%s, CONFIGURED_PROVIDERS=%s, PRIMARY_PRICE_SOURCE=%s",
        settings.pokemon_tcg_schedule_enabled,
        settings.pokemon_tcg_schedule_seconds,
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

    def evaluate_alerts_job() -> None:
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

    def pokemon_tcg_ingestion_job() -> None:
        logger.info("Configured provider scheduled ingestion started.")
        try:
            for provider_index, provider in enumerate(implemented_providers):
                logger.info(
                    "Provider ingestion started [%s]: slot=%s source=%s primary=%s",
                    provider.label,
                    provider.slot,
                    provider.source,
                    provider.is_primary,
                )
                with SessionLocal() as session:
                    for pool_index, pool in enumerate(tracked_pools):
                        pool_result = provider.ingest_pool_cards(
                            session,
                            card_ids=pool.card_ids,
                            clear_sample_seed=(provider_index == 0 and pool_index == 0),
                        )
                        logger.info(
                            "Provider ingestion pool finished [%s/%s]: slot=%s source=%s cards_requested=%s cards_processed=%s cards_failed=%s cards_skipped_no_price=%s created=%s updated=%s price_points=%s price_points_changed=%s price_points_unchanged=%s price_points_skipped_existing_timestamp=%s sample_rows_deleted=%s latest_captured_at=%s inserted_assets=%s",
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
                            pool_result.price_points_skipped_existing_timestamp,
                            pool_result.sample_rows_deleted,
                            pool_result.latest_captured_at.isoformat() if pool_result.latest_captured_at else "<none>",
                            ", ".join(pool_result.inserted_asset_names) if pool_result.inserted_asset_names else "<none>",
                        )
            with SessionLocal() as session:
                alert_result = process_alert_notifications(session)
                data_health = get_data_health_report(session)
            logger.info(
                "Alert evaluation after Pokemon TCG ingestion finished. active_alerts_checked=%s triggered=%s price_movement_alerts_triggered=%s prediction_alerts_triggered=%s alerts_rearmed=%s notifications_sent=%s dm_delivery_failures=%s target_alerts_deactivated=%s",
                alert_result.active_alerts_checked,
                alert_result.triggered_alerts,
                alert_result.price_movement_alerts_triggered,
                alert_result.prediction_alerts_triggered,
                alert_result.alerts_rearmed,
                alert_result.notifications_sent,
                alert_result.dm_delivery_failures,
                alert_result.target_alerts_deactivated,
            )
            logger.info(
                "Tracked Pokemon data health snapshot after Pokemon TCG ingestion: total_assets=%s assets_with_real_history=%s assets_without_real_history=%s average_real_history_points_per_asset=%s assets_lt3=%s assets_lt5=%s assets_lt8=%s recent_real_rows_24h=%s recent_real_rows_7d=%s assets_changed_24h=%s assets_changed_7d=%s changed_row_pct_24h=%s changed_row_pct_7d=%s no_movement_assets=%s unchanged_latest_assets=%s rows_per_change_24h=%s rows_per_change_7d=%s",
                data_health.total_assets,
                data_health.assets_with_real_history,
                data_health.assets_without_real_history,
                data_health.average_real_history_points_per_asset,
                data_health.assets_with_fewer_than_3_real_points,
                data_health.assets_with_fewer_than_5_real_points,
                data_health.assets_with_fewer_than_8_real_points,
                data_health.recent_real_price_rows_last_24h,
                data_health.recent_real_price_rows_last_7d,
                data_health.assets_with_price_change_last_24h,
                data_health.assets_with_price_change_last_7d,
                data_health.percent_recent_rows_changed_last_24h,
                data_health.percent_recent_rows_changed_last_7d,
                data_health.assets_with_no_price_movement_full_history,
                data_health.assets_with_unchanged_latest_price,
                data_health.rows_per_recent_price_change_last_24h
                if data_health.rows_per_recent_price_change_last_24h is not None
                else "<none>",
                data_health.rows_per_recent_price_change_last_7d
                if data_health.rows_per_recent_price_change_last_7d is not None
                else "<none>",
            )
            for pool_report in data_health.pool_reports:
                logger.info(
                    "Tracked pool data health snapshot [%s]: total_assets=%s assets_with_real_history=%s assets_without_real_history=%s average_real_history_points_per_asset=%s assets_lt3=%s assets_lt5=%s assets_lt8=%s recent_real_rows_24h=%s recent_real_rows_7d=%s assets_changed_24h=%s assets_changed_7d=%s changed_row_pct_24h=%s changed_row_pct_7d=%s no_movement_assets=%s unchanged_latest_assets=%s rows_per_change_24h=%s rows_per_change_7d=%s",
                    pool_report.label,
                    pool_report.total_assets,
                    pool_report.assets_with_real_history,
                    pool_report.assets_without_real_history,
                    pool_report.average_real_history_points_per_asset,
                    pool_report.assets_with_fewer_than_3_real_points,
                    pool_report.assets_with_fewer_than_5_real_points,
                    pool_report.assets_with_fewer_than_8_real_points,
                    pool_report.recent_real_price_rows_last_24h,
                    pool_report.recent_real_price_rows_last_7d,
                    pool_report.assets_with_price_change_last_24h,
                    pool_report.assets_with_price_change_last_7d,
                    pool_report.percent_recent_rows_changed_last_24h,
                    pool_report.percent_recent_rows_changed_last_7d,
                    pool_report.assets_with_no_price_movement_full_history,
                    pool_report.assets_with_unchanged_latest_price,
                    pool_report.rows_per_recent_price_change_last_24h
                    if pool_report.rows_per_recent_price_change_last_24h is not None
                    else "<none>",
                    pool_report.rows_per_recent_price_change_last_7d
                    if pool_report.rows_per_recent_price_change_last_7d is not None
                    else "<none>",
                )
            for provider_report in data_health.provider_reports:
                logger.info(
                    "Configured provider data health snapshot [%s]: slot=%s source=%s primary=%s total_assets=%s assets_with_real_history=%s average_real_history_points_per_asset=%s assets_changed_24h=%s assets_changed_7d=%s changed_row_pct_24h=%s changed_row_pct_7d=%s no_movement_assets=%s unchanged_latest_assets=%s",
                    provider_report.label,
                    provider_report.slot,
                    provider_report.source,
                    provider_report.is_primary,
                    provider_report.total_assets,
                    provider_report.assets_with_real_history,
                    provider_report.average_real_history_points_per_asset,
                    provider_report.assets_with_price_change_last_24h,
                    provider_report.assets_with_price_change_last_7d,
                    provider_report.percent_recent_rows_changed_last_24h,
                    provider_report.percent_recent_rows_changed_last_7d,
                    provider_report.assets_with_no_price_movement_full_history,
                    provider_report.assets_with_unchanged_latest_price,
                )
        except Exception:
            logger.exception("Configured provider ingestion job failed.")

    if settings.pokemon_tcg_schedule_enabled:
        logger.info(
            "Pokemon TCG scheduled ingestion enabled. Interval=%s seconds, max_instances=1.",
            settings.pokemon_tcg_schedule_seconds,
        )
        scheduler.add_job(
            pokemon_tcg_ingestion_job,
            "interval",
            seconds=settings.pokemon_tcg_schedule_seconds,
            id="pokemon-price-ingest",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(UTC),
        )
        return scheduler

    logger.info(
        "Pokemon TCG scheduled ingestion disabled. Falling back to alert evaluation every %s seconds.",
        settings.scheduler_poll_seconds,
    )
    scheduler.add_job(
        evaluate_alerts_job,
        "interval",
        seconds=settings.scheduler_poll_seconds,
        id="alert-poller",
        replace_existing=True,
    )
    return scheduler
