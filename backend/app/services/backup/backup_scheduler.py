"""Backup scheduler for automatic database backups.

Uses APScheduler to run periodic backups.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.backup.backup_service import get_backup_service

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Manages scheduled database backups."""

    def __init__(self):
        """Initialize the backup scheduler."""
        self.scheduler = BackgroundScheduler()
        self._is_running = False
        self._schedule_config: Dict[str, Any] = {
            "enabled": True,
            "interval_hours": 24,  # Default: daily backup
            "time": "02:00"  # Default: 2 AM
        }
        self._last_backup_result: Optional[Dict[str, Any]] = None

    def start(self):
        """Start the scheduler if not already running."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Backup scheduler started")

            # Schedule default backup job if enabled
            if self._schedule_config["enabled"]:
                self._schedule_backup_job()

    def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Backup scheduler stopped")

    def configure(self, enabled: bool = True, interval_hours: int = 24, time: str = "02:00"):
        """Configure backup schedule.

        Args:
            enabled: Whether automatic backups are enabled
            interval_hours: Hours between backups (0 = use time-based schedule)
            time: Time for daily backup (HH:MM format, used when interval_hours is 0 or 24)
        """
        self._schedule_config = {
            "enabled": enabled,
            "interval_hours": interval_hours,
            "time": time
        }

        # Remove existing backup job if any
        try:
            self.scheduler.remove_job("auto_backup")
        except Exception:
            pass

        if enabled and self._is_running:
            self._schedule_backup_job()

        logger.info(f"Backup schedule configured: {self._schedule_config}")

    def _schedule_backup_job(self):
        """Schedule the automatic backup job based on configuration."""
        interval_hours = self._schedule_config["interval_hours"]

        if interval_hours == 24 or interval_hours == 0:
            # Daily backup at specific time
            time_parts = self._schedule_config["time"].split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            trigger = CronTrigger(hour=hour, minute=minute)
            logger.info(f"Scheduling daily backup at {hour:02d}:{minute:02d}")
        else:
            # Interval-based backup
            trigger = IntervalTrigger(hours=interval_hours)
            logger.info(f"Scheduling backup every {interval_hours} hours")

        self.scheduler.add_job(
            self._run_backup,
            trigger=trigger,
            id="auto_backup",
            name="Automatic Database Backup",
            replace_existing=True
        )

    def _run_backup(self):
        """Execute the backup and store the result."""
        logger.info("Running scheduled backup...")
        backup_service = get_backup_service()
        result = backup_service.create_backup(label="auto")

        if result.get("success"):
            logger.info(f"Scheduled backup completed: {result.get('filename')}")
        else:
            logger.error(f"Scheduled backup failed: {result.get('error')}")

        self._last_backup_result = result
        return result

    def run_manual_backup(self) -> Dict[str, Any]:
        """Run a manual backup immediately.

        Returns:
            Dict with backup result
        """
        logger.info("Running manual backup...")
        backup_service = get_backup_service()
        result = backup_service.create_backup(label="manual")

        if result.get("success"):
            logger.info(f"Manual backup completed: {result.get('filename')}")
        else:
            logger.error(f"Manual backup failed: {result.get('error')}")

        self._last_backup_result = result
        return result

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Dict with scheduler status and configuration
        """
        next_run = None
        job = self.scheduler.get_job("auto_backup")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        return {
            "is_running": self._is_running,
            "config": self._schedule_config,
            "next_scheduled_backup": next_run,
            "last_backup_result": self._last_backup_result
        }

    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled backup time.

        Returns:
            datetime of next scheduled backup or None
        """
        job = self.scheduler.get_job("auto_backup")
        if job:
            return job.next_run_time
        return None


# Singleton instance
_backup_scheduler: Optional[BackupScheduler] = None


def get_backup_scheduler() -> BackupScheduler:
    """Get the backup scheduler singleton instance."""
    global _backup_scheduler
    if _backup_scheduler is None:
        _backup_scheduler = BackupScheduler()
    return _backup_scheduler
