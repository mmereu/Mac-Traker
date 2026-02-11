"""Cleanup API endpoints for Mac-Traker.

Provides endpoints for MAC history cleanup management.
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.cleanup.history_cleanup_service import get_history_cleanup_service
from app.services.cleanup.cleanup_scheduler import get_cleanup_scheduler


router = APIRouter()


# Pydantic schemas
class CleanupResult(BaseModel):
    success: bool
    deleted_count: int = 0
    retention_days: int = 90
    cutoff_date: Optional[str] = None
    timestamp: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class CleanupStats(BaseModel):
    total_records: int = 0
    oldest_record: Optional[str] = None
    retention_days: int = 90
    cutoff_date: Optional[str] = None
    records_to_delete: int = 0
    records_to_keep: int = 0
    event_type_counts: dict = {}
    last_cleanup: Optional[dict] = None
    error: Optional[str] = None


class RetentionConfig(BaseModel):
    retention_days: int = 90


class SchedulerStatus(BaseModel):
    is_running: bool
    config: dict
    retention_days: int
    next_scheduled_cleanup: Optional[str] = None
    last_cleanup_result: Optional[dict] = None


@router.get("/stats", response_model=CleanupStats)
async def get_cleanup_stats():
    """Get statistics about MAC history records.

    Returns information about total records, oldest record,
    and how many records would be deleted based on retention policy.
    """
    cleanup_service = get_history_cleanup_service()
    return cleanup_service.get_stats()


@router.post("/run", response_model=CleanupResult)
async def run_cleanup():
    """Run cleanup immediately.

    Deletes MAC history records older than the configured retention period (default 90 days).
    """
    cleanup_service = get_history_cleanup_service()
    return cleanup_service.cleanup_old_history()


@router.get("/retention", response_model=RetentionConfig)
async def get_retention():
    """Get current retention configuration."""
    cleanup_service = get_history_cleanup_service()
    return {"retention_days": cleanup_service.get_retention_days()}


@router.put("/retention", response_model=RetentionConfig)
async def set_retention(config: RetentionConfig):
    """Set retention period in days.

    Args:
        config: RetentionConfig with retention_days (minimum 1 day)
    """
    cleanup_service = get_history_cleanup_service()
    cleanup_service.set_retention_days(config.retention_days)
    return {"retention_days": cleanup_service.get_retention_days()}


@router.get("/scheduler/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Get current cleanup scheduler status."""
    scheduler = get_cleanup_scheduler()
    return scheduler.get_status()


@router.post("/scheduler/start")
async def start_scheduler():
    """Start the cleanup scheduler."""
    scheduler = get_cleanup_scheduler()
    scheduler.start()
    return {
        "success": True,
        "message": "Cleanup scheduler avviato",
        "status": scheduler.get_status()
    }


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the cleanup scheduler."""
    scheduler = get_cleanup_scheduler()
    scheduler.stop()
    return {
        "success": True,
        "message": "Cleanup scheduler fermato",
        "status": scheduler.get_status()
    }
