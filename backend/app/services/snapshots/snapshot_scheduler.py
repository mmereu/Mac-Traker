"""Snapshot scheduler for automatic network snapshots.

Creates periodic snapshots of the network state (MAC locations, topology).
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SnapshotScheduler:
    """Manages scheduled network snapshots."""

    def __init__(self):
        """Initialize the snapshot scheduler."""
        self.scheduler = BackgroundScheduler()
        self._is_running = False
        self._schedule_config: Dict[str, Any] = {
            "enabled": False,  # Disabled by default
            "interval_hours": 6,  # Default: every 6 hours
        }
        self._last_snapshot_result: Optional[Dict[str, Any]] = None
        self._snapshot_function: Optional[Callable] = None

    def start(self, snapshot_function: Optional[Callable] = None):
        """Start the scheduler if not already running.

        Args:
            snapshot_function: Function to call to create a snapshot
        """
        if snapshot_function:
            self._snapshot_function = snapshot_function

        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Snapshot scheduler started")

            # Schedule job if enabled
            if self._schedule_config["enabled"]:
                self._schedule_snapshot_job()

    def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Snapshot scheduler stopped")

    def configure(self, enabled: bool = False, interval_hours: int = 6):
        """Configure snapshot schedule.

        Args:
            enabled: Whether automatic snapshots are enabled
            interval_hours: Hours between snapshots
        """
        self._schedule_config = {
            "enabled": enabled,
            "interval_hours": interval_hours,
        }

        # Remove existing job if any
        try:
            self.scheduler.remove_job("auto_snapshot")
        except Exception:
            pass

        if enabled and self._is_running:
            self._schedule_snapshot_job()

        logger.info(f"Snapshot schedule configured: {self._schedule_config}")

    def _schedule_snapshot_job(self):
        """Schedule the automatic snapshot job based on configuration."""
        interval_hours = self._schedule_config["interval_hours"]

        trigger = IntervalTrigger(hours=interval_hours)
        logger.info(f"Scheduling snapshot every {interval_hours} hours")

        self.scheduler.add_job(
            self._run_snapshot,
            trigger=trigger,
            id="auto_snapshot",
            name="Automatic Network Snapshot",
            replace_existing=True
        )

    def _run_snapshot(self):
        """Execute the snapshot and store the result."""
        logger.info("Running scheduled snapshot...")

        if self._snapshot_function:
            try:
                result = self._snapshot_function()
                logger.info(f"Scheduled snapshot completed: {result}")
                self._last_snapshot_result = {
                    "success": True,
                    "timestamp": datetime.utcnow().isoformat(),
                    "result": result
                }
            except Exception as e:
                logger.error(f"Scheduled snapshot failed: {e}")
                self._last_snapshot_result = {
                    "success": False,
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e)
                }
        else:
            # Use default snapshot creation via API
            try:
                from app.db.database import SessionLocal
                from app.db.models import (
                    NetworkSnapshot, SnapshotMacLocation,
                    MacAddress, MacLocation, Switch, Port
                )

                db = SessionLocal()
                try:
                    # Create snapshot
                    snapshot = NetworkSnapshot(
                        name=f"Auto Snapshot {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                        description="Automatically generated snapshot",
                        status="creating",
                        started_at=datetime.utcnow(),
                    )
                    db.add(snapshot)
                    db.commit()
                    db.refresh(snapshot)

                    # Copy current MAC locations
                    mac_locations = db.query(MacLocation).filter(
                        MacLocation.is_current == True
                    ).all()

                    for loc in mac_locations:
                        mac = db.query(MacAddress).filter(
                            MacAddress.id == loc.mac_id
                        ).first()
                        switch = db.query(Switch).filter(
                            Switch.id == loc.switch_id
                        ).first()
                        port = db.query(Port).filter(
                            Port.id == loc.port_id
                        ).first()

                        if mac and switch and port:
                            snapshot_loc = SnapshotMacLocation(
                                snapshot_id=snapshot.id,
                                mac_address=mac.mac_address,
                                ip_address=loc.ip_address,
                                hostname=loc.hostname,
                                vendor_name=mac.vendor_name,
                                device_type=mac.device_type,
                                switch_hostname=switch.hostname,
                                switch_ip=switch.ip_address,
                                port_name=port.port_name,
                                vlan_id=loc.vlan_id,
                                site_code=switch.site_code,
                            )
                            db.add(snapshot_loc)

                    # Update snapshot stats
                    snapshot.total_macs = len(mac_locations)
                    snapshot.total_switches = db.query(Switch).filter(
                        Switch.is_active == True
                    ).count()
                    snapshot.status = "completed"
                    snapshot.completed_at = datetime.utcnow()

                    db.commit()

                    self._last_snapshot_result = {
                        "success": True,
                        "timestamp": datetime.utcnow().isoformat(),
                        "snapshot_id": snapshot.id,
                        "total_macs": snapshot.total_macs,
                    }
                    logger.info(f"Scheduled snapshot created: ID={snapshot.id}, MACs={snapshot.total_macs}")

                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Scheduled snapshot failed: {e}")
                self._last_snapshot_result = {
                    "success": False,
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e)
                }

        return self._last_snapshot_result

    def run_manual_snapshot(self) -> Dict[str, Any]:
        """Run a manual snapshot immediately.

        Returns:
            Dict with snapshot result
        """
        logger.info("Running manual snapshot...")
        return self._run_snapshot()

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Dict with scheduler status and configuration
        """
        next_run = None
        job = self.scheduler.get_job("auto_snapshot")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        return {
            "is_running": self._is_running,
            "config": self._schedule_config,
            "next_scheduled_snapshot": next_run,
            "last_snapshot_result": self._last_snapshot_result
        }


# Singleton instance
_snapshot_scheduler: Optional[SnapshotScheduler] = None


def get_snapshot_scheduler() -> SnapshotScheduler:
    """Get the snapshot scheduler singleton instance."""
    global _snapshot_scheduler
    if _snapshot_scheduler is None:
        _snapshot_scheduler = SnapshotScheduler()
    return _snapshot_scheduler
