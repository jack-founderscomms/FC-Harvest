"""
APScheduler wrapper.
Reads cron schedule from config and fires the harvest runner.
Can be run standalone: python -m harvest.scheduler
"""

import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .runner import load_config, run_harvest

logger = logging.getLogger(__name__)


def start_scheduler() -> BackgroundScheduler:
    config = load_config()
    schedule_cfg = config.get("schedule", {})
    cron_expr = schedule_cfg.get("cron", "0 7 * * *")
    timezone = schedule_cfg.get("timezone", "Europe/London")

    # Parse "0 7 * * *" into CronTrigger fields
    parts = cron_expr.split()
    trigger = CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        timezone=timezone,
    )

    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        _scheduled_harvest,
        trigger=trigger,
        id="harvest",
        replace_existing=True,
        misfire_grace_time=3600,  # run up to 1h late if server was down
    )
    scheduler.start()
    logger.info("Scheduler started. Next run: %s", scheduler.get_job("harvest").next_run_time)
    return scheduler


def _scheduled_harvest():
    logger.info("Scheduled harvest starting...")
    try:
        result = run_harvest()
        logger.info("Scheduled harvest done: %s", result)
    except Exception as exc:
        logger.error("Scheduled harvest failed: %s", exc, exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scheduler = start_scheduler()
    logger.info("Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
