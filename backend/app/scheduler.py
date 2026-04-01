import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.core.config import get_settings
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import ingest_pokemon_tcg_cards

logger = logging.getLogger(__name__)


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")

    def check_alerts_stub() -> None:
        logger.info(
            "Alert polling tick executed. Replace this stub with price ingestion and alert evaluation."
        )

    def pokemon_tcg_ingestion_job() -> None:
        try:
            with SessionLocal() as session:
                result = ingest_pokemon_tcg_cards(session)
            logger.info(
                "Pokemon TCG ingestion finished: cards=%s created=%s updated=%s price_points=%s sample_rows_deleted=%s",
                result.cards_processed,
                result.assets_created,
                result.assets_updated,
                result.price_points_inserted,
                result.sample_rows_deleted,
            )
        except Exception:
            logger.exception("Pokemon TCG ingestion job failed.")

    job_func = check_alerts_stub
    job_id = "alert-poller"
    if settings.pokemon_tcg_schedule_enabled:
        job_func = pokemon_tcg_ingestion_job
        job_id = "pokemon-price-ingest"

    scheduler.add_job(
        job_func,
        "interval",
        seconds=settings.scheduler_poll_seconds,
        id=job_id,
        replace_existing=True,
    )
    return scheduler
