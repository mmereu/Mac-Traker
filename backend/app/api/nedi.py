"""NeDi integration API endpoints."""
import os
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.nedi import NeDiService, get_nedi_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nedi", tags=["nedi"])


class NeDiConnectionStatus(BaseModel):
    """NeDi connection status response."""
    connected: bool
    host: str
    device_count: int = 0
    node_count: int = 0
    tables: List[str] = []
    error: Optional[str] = None


class NeDiImportRequest(BaseModel):
    """NeDi import request."""
    node_limit: int = 100000


class NeDiImportResponse(BaseModel):
    """NeDi import response."""
    success: bool
    devices: Dict[str, int]
    nodes: Dict[str, int]
    links: Dict[str, int]
    error: Optional[str] = None


class NeDiTableInfo(BaseModel):
    """NeDi table information."""
    name: str
    columns: List[Dict[str, Any]]


@router.get("/status", response_model=NeDiConnectionStatus)
async def get_nedi_status():
    """Check connection to NeDi database and return status."""
    try:
        with NeDiService() as nedi:
            tables = nedi.get_tables()
            summary = nedi.get_summary()

            return NeDiConnectionStatus(
                connected=True,
                host=nedi.config.host,
                device_count=summary.get("devices", 0),
                node_count=summary.get("nodes", 0),
                tables=tables,
            )
    except Exception as e:
        logger.error(f"Failed to connect to NeDi: {e}")
        return NeDiConnectionStatus(
            connected=False,
            host=os.getenv("NEDI_DB_HOST", "localhost"),
            error=str(e),
        )


@router.get("/tables")
async def get_nedi_tables():
    """List all tables in NeDi database."""
    try:
        with NeDiService() as nedi:
            tables = nedi.get_tables()
            return {"tables": tables, "count": len(tables)}
    except Exception as e:
        logger.error(f"Failed to get NeDi tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{table_name}")
async def get_nedi_table_structure(table_name: str):
    """Get structure of a specific NeDi table."""
    try:
        with NeDiService() as nedi:
            columns = nedi.get_table_structure(table_name)
            return {
                "table": table_name,
                "columns": columns,
            }
    except Exception as e:
        logger.error(f"Failed to get NeDi table structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices")
async def get_nedi_devices():
    """Get all devices from NeDi database."""
    try:
        with NeDiService() as nedi:
            devices = nedi.get_devices()
            return {
                "devices": devices,
                "count": len(devices),
            }
    except Exception as e:
        logger.error(f"Failed to get NeDi devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes")
async def get_nedi_nodes(limit: int = 1000):
    """Get MAC address nodes from NeDi database."""
    try:
        with NeDiService() as nedi:
            nodes = nedi.get_nodes(limit=limit)
            return {
                "nodes": nodes,
                "count": len(nodes),
                "total": nedi.get_node_count(),
            }
    except Exception as e:
        logger.error(f"Failed to get NeDi nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/links")
async def get_nedi_links():
    """Get topology links from NeDi database."""
    try:
        with NeDiService() as nedi:
            links = nedi.get_links()
            return {
                "links": links,
                "count": len(links),
            }
    except Exception as e:
        logger.error(f"Failed to get NeDi links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=NeDiImportResponse)
async def import_from_nedi(
    request: NeDiImportRequest = NeDiImportRequest(),
    db: Session = Depends(get_db),
):
    """Import data from NeDi database into Mac-Traker.

    This imports:
    - Devices (as switches)
    - Topology links
    - Nodes (MAC addresses with locations)
    """
    try:
        with NeDiService() as nedi:
            results = nedi.full_import(db, node_limit=request.node_limit)

            return NeDiImportResponse(
                success=results.get("success", False),
                devices=results.get("devices", {}),
                nodes=results.get("nodes", {}),
                links=results.get("links", {}),
                error=results.get("error"),
            )
    except Exception as e:
        logger.error(f"NeDi import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/devices")
async def import_devices_only(db: Session = Depends(get_db)):
    """Import only devices from NeDi."""
    try:
        with NeDiService() as nedi:
            stats = nedi.import_devices_to_mactraker(db)
            return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Device import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/nodes")
async def import_nodes_only(
    limit: int = 100000,
    db: Session = Depends(get_db),
):
    """Import only MAC address nodes from NeDi."""
    try:
        with NeDiService() as nedi:
            stats = nedi.import_nodes_to_mactraker(db, limit=limit)
            return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Node import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/links")
async def import_links_only(db: Session = Depends(get_db)):
    """Import only topology links from NeDi."""
    try:
        with NeDiService() as nedi:
            stats = nedi.import_links_to_mactraker(db)
            return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Link import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# NeDi Sync Scheduler Endpoints
# ============================================================================

class NeDiSchedulerConfig(BaseModel):
    """NeDi scheduler configuration."""
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None
    node_limit: Optional[int] = None


class NeDiSchedulerStatus(BaseModel):
    """NeDi scheduler status response."""
    enabled: bool
    interval_minutes: int
    node_limit: int
    is_running: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None


@router.get("/scheduler/status", response_model=NeDiSchedulerStatus)
async def get_nedi_scheduler_status():
    """Get NeDi sync scheduler status."""
    scheduler = get_nedi_scheduler()
    status = scheduler.get_status()
    return NeDiSchedulerStatus(**status)


@router.post("/scheduler/configure")
async def configure_nedi_scheduler(config: NeDiSchedulerConfig):
    """Configure NeDi sync scheduler.

    Args:
        enabled: Enable/disable automatic sync
        interval_minutes: Sync interval in minutes (default 15)
        node_limit: Maximum MACs to sync (default 200000)
    """
    scheduler = get_nedi_scheduler()
    scheduler.configure(
        enabled=config.enabled,
        interval_minutes=config.interval_minutes,
        node_limit=config.node_limit,
    )
    return {
        "success": True,
        "message": "NeDi scheduler configured",
        "status": scheduler.get_status(),
    }


@router.post("/scheduler/run-now")
async def run_nedi_sync_now():
    """Run NeDi sync immediately."""
    scheduler = get_nedi_scheduler()

    if scheduler._is_running:
        return {
            "success": False,
            "message": "Sync already in progress",
            "status": scheduler.get_status(),
        }

    # Run sync (blocking)
    result = scheduler.run_now()
    return {
        "success": result.get("success", False),
        "message": "NeDi sync completed" if result.get("success") else "Sync failed",
        "result": result,
    }


@router.post("/scheduler/enable")
async def enable_nedi_scheduler(interval_minutes: int = 15):
    """Enable NeDi sync scheduler."""
    scheduler = get_nedi_scheduler()
    scheduler.enable(interval_minutes)
    return {
        "success": True,
        "message": f"NeDi sync enabled (every {interval_minutes} minutes)",
        "status": scheduler.get_status(),
    }


@router.post("/scheduler/disable")
async def disable_nedi_scheduler():
    """Disable NeDi sync scheduler."""
    scheduler = get_nedi_scheduler()
    scheduler.disable()
    return {
        "success": True,
        "message": "NeDi sync disabled",
        "status": scheduler.get_status(),
    }
