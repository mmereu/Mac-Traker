"""Backup API endpoints for Mac-Traker.

Provides endpoints for database backup management.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.backup.backup_service import get_backup_service
from app.services.backup.backup_scheduler import get_backup_scheduler


router = APIRouter()


# Pydantic schemas
class BackupInfo(BaseModel):
    filename: str
    path: str
    size: int
    size_formatted: str
    created_at: str


class BackupResult(BaseModel):
    success: bool
    filename: str = None
    path: str = None
    size: int = None
    size_formatted: str = None
    timestamp: str = None
    error: str = None
    message: str = None


class BackupVerification(BaseModel):
    success: bool
    integrity: str = None
    tables: dict = None
    total_records: int = None
    error: str = None


class ScheduleConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 24
    time: str = "02:00"

    class Config:
        extra = "allow"


class SchedulerStatus(BaseModel):
    is_running: bool
    config: dict  # Changed to dict for flexibility
    next_scheduled_backup: Optional[str] = None
    last_backup_result: Optional[dict] = None  # None when no backup has run yet

    class Config:
        extra = "allow"


@router.get("/", response_model=List[BackupInfo])
async def list_backups():
    """List all available backups."""
    backup_service = get_backup_service()
    return backup_service.list_backups()


@router.post("/create", response_model=BackupResult)
async def create_backup(label: str = None):
    """Create a new database backup.

    Args:
        label: Optional label to include in backup filename
    """
    backup_service = get_backup_service()
    result = backup_service.create_backup(label=label)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return result


@router.post("/manual", response_model=BackupResult)
async def manual_backup():
    """Trigger a manual backup immediately."""
    scheduler = get_backup_scheduler()
    result = scheduler.run_manual_backup()

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return result


@router.delete("/{filename}")
async def delete_backup(filename: str):
    """Delete a specific backup file.

    Args:
        filename: Name of the backup file to delete
    """
    backup_service = get_backup_service()
    result = backup_service.delete_backup(filename)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.get("/{filename}/verify", response_model=BackupVerification)
async def verify_backup(filename: str):
    """Verify a backup file integrity.

    Args:
        filename: Name of the backup file to verify
    """
    backup_service = get_backup_service()
    result = backup_service.verify_backup(filename)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/{filename}/restore")
async def restore_backup(filename: str):
    """Restore database from a backup.

    WARNING: This will overwrite the current database!

    Args:
        filename: Name of the backup file to restore
    """
    backup_service = get_backup_service()
    result = backup_service.restore_backup(filename)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/scheduler/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Get current backup scheduler status."""
    scheduler = get_backup_scheduler()
    status = scheduler.get_status()
    return status


@router.post("/scheduler/configure")
async def configure_scheduler(config: ScheduleConfig):
    """Configure the backup scheduler.

    Args:
        config: Scheduler configuration (enabled, interval_hours, time)
    """
    scheduler = get_backup_scheduler()
    scheduler.configure(
        enabled=config.enabled,
        interval_hours=config.interval_hours,
        time=config.time
    )
    return {
        "success": True,
        "message": "Scheduler configured",
        "config": config.model_dump()
    }


@router.post("/scheduler/start")
async def start_scheduler():
    """Start the backup scheduler."""
    scheduler = get_backup_scheduler()
    scheduler.start()
    return {
        "success": True,
        "message": "Scheduler started",
        "status": scheduler.get_status()
    }


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the backup scheduler."""
    scheduler = get_backup_scheduler()
    scheduler.stop()
    return {
        "success": True,
        "message": "Scheduler stopped",
        "status": scheduler.get_status()
    }
