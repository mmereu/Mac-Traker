"""NeDi Sync Scheduler.

Synchronizes MAC address data from NeDi database periodically.
This replaces slow SNMP discovery with fast database sync.
"""
from datetime import datetime
from typing import Optional, Callable, Dict, Any
import threading
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.database import SessionLocal
from app.services.nedi.nedi_service import NeDiService

logger = logging.getLogger(__name__)


class NeDiScheduler:
    """Scheduler for periodic NeDi database synchronization."""

    _instance: Optional["NeDiScheduler"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._scheduler = BackgroundScheduler()
        self._enabled = False
        self._interval_minutes = 15  # Default: every 15 minutes
        self._node_limit = 200000  # Sync up to 200k MACs
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._on_complete: Optional[Callable] = None
        self._is_running = False

    def start(self, interval_minutes: int = 15, enabled: bool = True):
        """Start the NeDi sync scheduler.

        Args:
            interval_minutes: Sync interval (default 15 min)
            enabled: Whether to enable automatic sync (default True)
        """
        self._interval_minutes = interval_minutes
        self._enabled = enabled

        if not self._scheduler.running:
            self._scheduler.start()

        if enabled:
            self._schedule_job()
            logger.info(f"NeDi sync scheduler enabled: every {interval_minutes} minutes")
        else:
            logger.info("NeDi sync scheduler started (disabled)")

    def _schedule_job(self):
        """Schedule the NeDi sync job."""
        # Remove existing job if any
        if self._scheduler.get_job("nedi_sync"):
            self._scheduler.remove_job("nedi_sync")

        self._scheduler.add_job(
            self._run_sync,
            trigger=IntervalTrigger(minutes=self._interval_minutes),
            id="nedi_sync",
            name="NeDi Database Sync",
            replace_existing=True,
        )

    def _run_sync(self):
        """Execute NeDi database synchronization."""
        if self._is_running:
            logger.warning("NeDi sync already running, skipping...")
            return

        self._is_running = True
        logger.info(f"[{datetime.now()}] Starting NeDi sync...")

        try:
            db = SessionLocal()
            try:
                with NeDiService() as nedi:
                    results = nedi.full_import(db, node_limit=self._node_limit)

                self._last_run = datetime.now()
                self._last_result = {
                    "success": results.get("success", False),
                    "devices": results.get("devices", {}),
                    "nodes": results.get("nodes", {}),
                    "links": results.get("links", {}),
                    "error": results.get("error"),
                    "timestamp": self._last_run.isoformat(),
                }

                # Calculate totals
                devices_total = sum(results.get("devices", {}).values())
                nodes_total = (
                    results.get("nodes", {}).get("created", 0) +
                    results.get("nodes", {}).get("updated", 0)
                )
                links_total = (
                    results.get("links", {}).get("created", 0) +
                    results.get("links", {}).get("updated", 0)
                )

                logger.info(
                    f"NeDi sync complete: {devices_total} devices, "
                    f"{nodes_total} MACs, {links_total} links"
                )

                # Call callback if set
                if self._on_complete:
                    self._on_complete(self._last_result)

            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error in NeDi sync: {e}")
            self._last_result = {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        finally:
            self._is_running = False

    def enable(self, interval_minutes: Optional[int] = None):
        """Enable scheduled sync."""
        if interval_minutes:
            self._interval_minutes = interval_minutes
        self._enabled = True
        self._schedule_job()
        logger.info(f"NeDi sync scheduler enabled: every {self._interval_minutes} minutes")

    def disable(self):
        """Disable scheduled sync."""
        self._enabled = False
        if self._scheduler.get_job("nedi_sync"):
            self._scheduler.remove_job("nedi_sync")
        logger.info("NeDi sync scheduler disabled")

    def run_now(self) -> Dict[str, Any]:
        """Run sync immediately."""
        self._run_sync()
        return self._last_result or {"success": False, "error": "No result"}

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        next_run = None
        job = self._scheduler.get_job("nedi_sync")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        return {
            "enabled": self._enabled,
            "interval_minutes": self._interval_minutes,
            "node_limit": self._node_limit,
            "is_running": self._is_running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": next_run,
            "last_result": self._last_result,
        }

    def configure(
        self,
        enabled: Optional[bool] = None,
        interval_minutes: Optional[int] = None,
        node_limit: Optional[int] = None,
    ):
        """Configure the scheduler."""
        if interval_minutes is not None:
            self._interval_minutes = interval_minutes
        if node_limit is not None:
            self._node_limit = node_limit
        if enabled is not None:
            if enabled:
                self.enable()
            else:
                self.disable()
        elif self._enabled:
            # Re-schedule with new interval
            self._schedule_job()

    def set_on_complete(self, callback: Callable):
        """Set callback for when sync completes."""
        self._on_complete = callback

    def stop(self):
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info("NeDi sync scheduler stopped")


# Singleton getter
_nedi_scheduler: Optional[NeDiScheduler] = None


def get_nedi_scheduler() -> NeDiScheduler:
    """Get the singleton NeDi scheduler instance."""
    global _nedi_scheduler
    if _nedi_scheduler is None:
        _nedi_scheduler = NeDiScheduler()
    return _nedi_scheduler
