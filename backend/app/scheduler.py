import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")

    def check_alerts_stub() -> None:
        logger.info(
            "Alert polling tick executed. Replace this stub with price ingestion and alert evaluation."
        )

    scheduler.add_job(
        check_alerts_stub,
        "interval",
        seconds=settings.scheduler_poll_seconds,
        id="alert-poller",
        replace_existing=True,
    )
    return scheduler
