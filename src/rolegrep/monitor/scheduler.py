"""APScheduler wrapper for the daily monitor job."""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from rolegrep.config import DEFAULT_MONITOR_HOUR, DEFAULT_MONITOR_MINUTE
from rolegrep.monitor.runner import format_monitor_summary, run_monitor_once

logger = logging.getLogger(__name__)


def build_scheduler(
    *,
    hour: int = DEFAULT_MONITOR_HOUR,
    minute: int = DEFAULT_MONITOR_MINUTE,
    provider: str | None = None,
    model: str | None = None,
    database_url: str | None = None,
) -> BlockingScheduler:
    scheduler = BlockingScheduler()

    def _job() -> None:
        logger.info("Starting scheduled monitor run")
        summary = run_monitor_once(
            database_url=database_url,
            provider=provider,
            model=model,
            progress=lambda msg: logger.info(msg),
        )
        logger.info("Monitor finished:\n%s", format_monitor_summary(summary))

    scheduler.add_job(
        _job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_monitor",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def run_scheduler_forever(**kwargs: Any) -> None:
    """Block and run the daily monitor cron."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    hour = kwargs.get("hour", DEFAULT_MONITOR_HOUR)
    minute = kwargs.get("minute", DEFAULT_MONITOR_MINUTE)
    scheduler = build_scheduler(**kwargs)
    logger.info("Scheduler started — daily monitor at %02d:%02d local time", hour, minute)
    scheduler.start()
