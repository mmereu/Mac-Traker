"""Intent Verification Scheduler.

Runs compliance checks periodically and stores results.
"""
from datetime import datetime
from typing import Optional, Callable
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.database import SessionLocal
from app.services.intent_verification import IntentVerificationService


class IntentScheduler:
    """Scheduler for periodic intent verification checks."""

    _instance: Optional["IntentScheduler"] = None
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
        self._interval_minutes = 60  # Default: every hour
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[dict] = None
        self._on_complete: Optional[Callable] = None

    def start(self, interval_minutes: int = 60, enabled: bool = False):
        """Start the intent scheduler."""
        self._interval_minutes = interval_minutes
        self._enabled = enabled

        if not self._scheduler.running:
            self._scheduler.start()

        if enabled:
            self._schedule_job()
            print(f"Intent scheduler enabled: every {interval_minutes} minutes")
        else:
            print("Intent scheduler started (disabled by default)")

    def _schedule_job(self):
        """Schedule the intent check job."""
        # Remove existing job if any
        if self._scheduler.get_job("intent_check"):
            self._scheduler.remove_job("intent_check")

        self._scheduler.add_job(
            self._run_checks,
            trigger=IntervalTrigger(minutes=self._interval_minutes),
            id="intent_check",
            name="Intent Verification Check",
            replace_existing=True,
        )

    def _run_checks(self):
        """Execute all intent verification checks."""
        print(f"[{datetime.now()}] Running scheduled intent checks...")
        try:
            db = SessionLocal()
            try:
                service = IntentVerificationService(db)
                results = service.run_all_checks()  # Returns list of CheckResult
                self._last_run = datetime.now()

                # Build summary dict from results list
                passed = sum(1 for r in results if r.passed)
                failed = len(results) - passed
                self._last_result = {
                    "total_checks": len(results),
                    "passed": passed,
                    "failed": failed,
                }

                print(f"Intent check complete: {passed}/{len(results)} passed, {failed} failed")

                # Call callback if set
                if self._on_complete:
                    self._on_complete(self._last_result)

            finally:
                db.close()
        except Exception as e:
            print(f"Error in scheduled intent check: {e}")

    def enable(self, interval_minutes: Optional[int] = None):
        """Enable scheduled checks."""
        if interval_minutes:
            self._interval_minutes = interval_minutes
        self._enabled = True
        self._schedule_job()
        print(f"Intent scheduler enabled: every {self._interval_minutes} minutes")

    def disable(self):
        """Disable scheduled checks."""
        self._enabled = False
        if self._scheduler.get_job("intent_check"):
            self._scheduler.remove_job("intent_check")
        print("Intent scheduler disabled")

    def run_now(self) -> dict:
        """Run checks immediately."""
        self._run_checks()
        return self._last_result or {}

    def get_status(self) -> dict:
        """Get scheduler status."""
        next_run = None
        job = self._scheduler.get_job("intent_check")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        return {
            "enabled": self._enabled,
            "interval_minutes": self._interval_minutes,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": next_run,
            "last_result_summary": {
                "passed": self._last_result.get("passed", 0) if self._last_result else 0,
                "failed": self._last_result.get("failed", 0) if self._last_result else 0,
            } if self._last_result else None,
        }

    def set_on_complete(self, callback: Callable):
        """Set callback for when checks complete."""
        self._on_complete = callback

    def stop(self):
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        print("Intent scheduler stopped")


# Singleton getter
_intent_scheduler: Optional[IntentScheduler] = None


def get_intent_scheduler() -> IntentScheduler:
    """Get the singleton intent scheduler instance."""
    global _intent_scheduler
    if _intent_scheduler is None:
        _intent_scheduler = IntentScheduler()
    return _intent_scheduler
