"""Background scheduler for periodic polling."""

import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.database import get_db_context
from app.services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()


async def poll_and_process():
    """Background job to poll and process issues."""
    logger.info("Scheduler: Starting poll cycle")
    
    try:
        with get_db_context() as db:
            orchestrator = Orchestrator(db)
            
            # Check existing sessions first
            await orchestrator.check_sessions()
            
            # Then process new issues
            result = await orchestrator.run()
            logger.info(f"Scheduler: Poll complete - {result}")
            
    except Exception as e:
        logger.error(f"Scheduler: Error during poll - {e}")


def start_scheduler():
    """Start the background scheduler."""
    if not scheduler.running:
        scheduler.add_job(
            poll_and_process,
            trigger=IntervalTrigger(minutes=settings.poll_interval_minutes),
            id="poll_issues",
            name="Poll and process issues",
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"Scheduler started: polling every {settings.poll_interval_minutes} minutes")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


def get_next_run_time():
    """Get the next scheduled run time."""
    job = scheduler.get_job("poll_issues")
    if job:
        return job.next_run_time
    return None
