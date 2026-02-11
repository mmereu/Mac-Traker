"""Cleanup scheduler for automatic history cleanup.

Uses APScheduler to run periodic cleanup tasks.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.cleanup.history_cleanup_service import get_history_cleanup_service

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """Manages scheduled cleanup tasks."""

    def __init__(self):
        """Initialize the cleanup scheduler."""
        self.scheduler = BackgroundScheduler()
        self._is_running = False
        self._schedule_config: Dict[str, Any] = {
            "enabled": True,
            "time": "03:00"  # Default: 3 AM daily
        }

    def start(self):
        """Start the scheduler if not already running."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Cleanup scheduler started")

            # Schedule default cleanup job if enabled
            if self._schedule_config["enabled"]:
                self._schedule_cleanup_job()

    def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Cleanup scheduler stopped")

    def configure(self, enabled: bool = True, time: str = "03:00"):
        """Configure cleanup schedule.

        Args:
            enabled: Whether automatic cleanup is enabled
            time: Time for daily cleanup (HH:MM format)
        """
        self._schedule_config = {
            "enabled": enabled,
            "time": time
        }

        # Remove existing cleanup job if any
        try:
            self.scheduler.remove_job("auto_history_cleanup")
        except Exception:
            pass

        if enabled and self._is_running:
            self._schedule_cleanup_job()

        logger.info(f"Cleanup schedule configured: {self._schedule_config}")

    def _schedule_cleanup_job(self):
        """Schedule the automatic cleanup job based on configuration."""
        time_parts = self._schedule_config["time"].split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0

        trigger = CronTrigger(hour=hour, minute=minute)
        logger.info(f"Scheduling daily history cleanup at {hour:02d}:{minute:02d}")

        self.scheduler.add_job(
            self._run_cleanup,
            trigger=trigger,
            id="auto_history_cleanup",
            name="Automatic History Cleanup",
            replace_existing=True
        )

    def _run_cleanup(self):
        """Execute the history cleanup."""
        logger.info("Running scheduled history cleanup...")
        cleanup_service = get_history_cleanup_service()
        result = cleanup_service.cleanup_old_history()

        if result.get("success"):
            logger.info(f"Scheduled cleanup completed: {result.get('deleted_count')} records deleted")
        else:
            logger.error(f"Scheduled cleanup failed: {result.get('error')}")

        return result

    def run_manual_cleanup(self) -> Dict[str, Any]:
        """Run cleanup immediately.

        Returns:
            Dict with cleanup result
        """
        logger.info("Running manual history cleanup...")
        cleanup_service = get_history_cleanup_service()
        result = cleanup_service.cleanup_old_history()

        if result.get("success"):
            logger.info(f"Manual cleanup completed: {result.get('deleted_count')} records deleted")
        else:
            logger.error(f"Manual cleanup failed: {result.get('error')}")

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Dict with scheduler status and configuration
        """
        cleanup_service = get_history_cleanup_service()

        next_run = None
        job = self.scheduler.get_job("auto_history_cleanup")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        return {
            "is_running": self._is_running,
            "config": self._schedule_config,
            "retention_days": cleanup_service.get_retention_days(),
            "next_scheduled_cleanup": next_run,
            "last_cleanup_result": cleanup_service.get_last_cleanup_result()
        }

    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled cleanup time.

        Returns:
            datetime of next scheduled cleanup or None
        """
        job = self.scheduler.get_job("auto_history_cleanup")
        if job:
            return job.next_run_time
        return None


# Singleton instance
_cleanup_scheduler: Optional[CleanupScheduler] = None


def get_cleanup_scheduler() -> CleanupScheduler:
    """Get the cleanup scheduler singleton instance."""
    global _cleanup_scheduler
    if _cleanup_scheduler is None:
        _cleanup_scheduler = CleanupScheduler()
    return _cleanup_scheduler
