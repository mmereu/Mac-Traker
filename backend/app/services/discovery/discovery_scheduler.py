"""Discovery scheduler for automatic network discovery.

Uses APScheduler to run periodic discovery tasks.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class DiscoveryScheduler:
    """Manages scheduled network discovery tasks."""

    def __init__(self):
        """Initialize the discovery scheduler."""
        self.scheduler = BackgroundScheduler()
        self._is_running = False
        self._schedule_config: Dict[str, Any] = {
            "enabled": True,
            "interval_minutes": 15,  # Default: every 15 minutes
        }
        self._last_discovery_result: Optional[Dict[str, Any]] = None
        self._discovery_function = None  # Will be set when we start

    def start(self, discovery_function=None):
        """Start the scheduler if not already running.

        Args:
            discovery_function: The function to call for discovery (async wrapper)
        """
        if not self._is_running:
            self._discovery_function = discovery_function
            self.scheduler.start()
            self._is_running = True
            logger.info("Discovery scheduler started")

            # Schedule default discovery job if enabled
            if self._schedule_config["enabled"] and self._discovery_function:
                self._schedule_discovery_job()

    def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Discovery scheduler stopped")

    def configure(self, enabled: bool = True, interval_minutes: int = 15):
        """Configure discovery schedule.

        Args:
            enabled: Whether automatic discovery is enabled
            interval_minutes: Minutes between discovery runs (5-60)
        """
        # Validate interval
        interval_minutes = max(5, min(60, interval_minutes))

        self._schedule_config = {
            "enabled": enabled,
            "interval_minutes": interval_minutes,
        }

        # Remove existing discovery job if any
        try:
            self.scheduler.remove_job("auto_discovery")
        except Exception:
            pass

        if enabled and self._is_running and self._discovery_function:
            self._schedule_discovery_job()

        logger.info(f"Discovery schedule configured: {self._schedule_config}")

    def _schedule_discovery_job(self):
        """Schedule the automatic discovery job based on configuration."""
        interval_minutes = self._schedule_config["interval_minutes"]

        trigger = IntervalTrigger(minutes=interval_minutes)
        logger.info(f"Scheduling discovery every {interval_minutes} minutes")

        self.scheduler.add_job(
            self._run_discovery,
            trigger=trigger,
            id="auto_discovery",
            name="Automatic Network Discovery",
            replace_existing=True
        )

    def _run_discovery(self):
        """Execute the discovery and store the result."""
        import asyncio
        from app.db.database import SessionLocal

        logger.info("Running scheduled discovery...")

        try:
            if self._discovery_function:
                # Create a new database session for this scheduled task
                db = SessionLocal()
                try:
                    # Run the async discovery function
                    asyncio.run(self._discovery_function(db))
                    self._last_discovery_result = {
                        "success": True,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message": "Scheduled discovery completed"
                    }
                    logger.info("Scheduled discovery completed successfully")
                finally:
                    db.close()
            else:
                self._last_discovery_result = {
                    "success": False,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": "Discovery function not configured"
                }
                logger.error("Discovery function not configured")
        except Exception as e:
            self._last_discovery_result = {
                "success": False,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"Error: {str(e)}"
            }
            logger.error(f"Scheduled discovery failed: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Dict with scheduler status and configuration
        """
        next_run = None
        job = self.scheduler.get_job("auto_discovery")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        return {
            "is_running": self._is_running,
            "config": self._schedule_config,
            "next_scheduled_discovery": next_run,
            "last_discovery_result": self._last_discovery_result
        }

    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled discovery time.

        Returns:
            datetime of next scheduled discovery or None
        """
        job = self.scheduler.get_job("auto_discovery")
        if job:
            return job.next_run_time
        return None

    def trigger_now(self):
        """Trigger a discovery immediately (for manual start)."""
        if self._discovery_function:
            self._run_discovery()


# Singleton instance
_discovery_scheduler: Optional[DiscoveryScheduler] = None


def get_discovery_scheduler() -> DiscoveryScheduler:
    """Get the discovery scheduler singleton instance."""
    global _discovery_scheduler
    if _discovery_scheduler is None:
        _discovery_scheduler = DiscoveryScheduler()
    return _discovery_scheduler
