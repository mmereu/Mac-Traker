"""API endpoints for Network Snapshots (IP Fabric-like snapshot system)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    NetworkSnapshot, SnapshotMacLocation,
    MacAddress, MacLocation, Switch, Port, TopologyLink
)

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


# Pydantic schemas
class SnapshotResponse(BaseModel):
    id: int
    name: Optional[str]
    description: Optional[str]
    status: str
    total_switches: int
    total_ports: int
    total_macs: int
    total_hosts: int
    total_links: int
    switches_discovered: int
    switches_failed: int
    discovery_duration_ms: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]
    is_locked: bool
    is_baseline: bool

    class Config:
        from_attributes = True


class SnapshotListResponse(BaseModel):
    items: list[SnapshotResponse]
    total: int


class SnapshotCreate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SnapshotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_locked: Optional[bool] = None
    is_baseline: Optional[bool] = None


class SnapshotCompareResult(BaseModel):
    snapshot1_id: int
    snapshot1_name: Optional[str]
    snapshot1_date: datetime
    snapshot2_id: int
    snapshot2_name: Optional[str]
    snapshot2_date: datetime
    added_macs: list[dict]
    removed_macs: list[dict]
    moved_macs: list[dict]
    stats: dict


class SnapshotMacResponse(BaseModel):
    mac_address: str
    ip_address: Optional[str]
    hostname: Optional[str]
    vendor_name: Optional[str]
    device_type: Optional[str]
    switch_hostname: str
    switch_ip: str
    port_name: str
    vlan_id: Optional[int]
    site_code: Optional[str]


@router.get("", response_model=SnapshotListResponse)
async def list_snapshots(
    status: Optional[str] = Query(None, description="Filter by status"),
    is_locked: Optional[bool] = Query(None),
    is_baseline: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all network snapshots."""
    query = db.query(NetworkSnapshot)

    if status:
        query = query.filter(NetworkSnapshot.status == status)
    if is_locked is not None:
        query = query.filter(NetworkSnapshot.is_locked == is_locked)
    if is_baseline is not None:
        query = query.filter(NetworkSnapshot.is_baseline == is_baseline)

    total = query.count()
    snapshots = query.order_by(NetworkSnapshot.started_at.desc()).offset(skip).limit(limit).all()

    return SnapshotListResponse(
        items=[SnapshotResponse.model_validate(s) for s in snapshots],
        total=total
    )


@router.post("", response_model=SnapshotResponse)
async def create_snapshot(data: SnapshotCreate, db: Session = Depends(get_db)):
    """Create a new snapshot from current network state.

    This captures the current MAC locations into an immutable snapshot.
    """
    # Create snapshot record
    snapshot = NetworkSnapshot(
        name=data.name or f"Snapshot {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        description=data.description,
        status="running",
        started_at=datetime.utcnow()
    )
    db.add(snapshot)
    db.flush()  # Get ID

    try:
        # Count current stats
        snapshot.total_switches = db.query(func.count(Switch.id)).filter(Switch.is_active == True).scalar() or 0
        snapshot.total_ports = db.query(func.count(Port.id)).scalar() or 0
        snapshot.total_links = db.query(func.count(TopologyLink.id)).scalar() or 0

        # Capture all current MAC locations
        mac_count = 0
        current_locations = db.query(
            MacAddress, MacLocation
        ).join(
            MacLocation, (MacAddress.id == MacLocation.mac_id) & (MacLocation.is_current == True)
        ).all()

        for mac, loc in current_locations:
            # Get switch and port info
            switch = db.query(Switch).filter(Switch.id == loc.switch_id).first()
            port = db.query(Port).filter(Port.id == loc.port_id).first()

            if switch and port:
                snapshot_mac = SnapshotMacLocation(
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
                    site_code=switch.site_code
                )
                db.add(snapshot_mac)
                mac_count += 1

        snapshot.total_macs = mac_count
        snapshot.status = "completed"
        snapshot.completed_at = datetime.utcnow()
        snapshot.discovery_duration_ms = int(
            (snapshot.completed_at - snapshot.started_at).total_seconds() * 1000
        )

        db.commit()
        db.refresh(snapshot)

        return SnapshotResponse.model_validate(snapshot)

    except Exception as e:
        snapshot.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Snapshot creation failed: {str(e)}")


@router.get("/{snapshot_id}", response_model=SnapshotResponse)
async def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """Get a specific snapshot."""
    snapshot = db.query(NetworkSnapshot).filter(NetworkSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return SnapshotResponse.model_validate(snapshot)


@router.put("/{snapshot_id}", response_model=SnapshotResponse)
async def update_snapshot(snapshot_id: int, data: SnapshotUpdate, db: Session = Depends(get_db)):
    """Update snapshot metadata (name, description, lock status)."""
    snapshot = db.query(NetworkSnapshot).filter(NetworkSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    if data.name is not None:
        snapshot.name = data.name
    if data.description is not None:
        snapshot.description = data.description
    if data.is_locked is not None:
        snapshot.is_locked = data.is_locked
    if data.is_baseline is not None:
        snapshot.is_baseline = data.is_baseline

    db.commit()
    db.refresh(snapshot)

    return SnapshotResponse.model_validate(snapshot)


@router.delete("/{snapshot_id}")
async def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """Delete a snapshot (unless locked)."""
    snapshot = db.query(NetworkSnapshot).filter(NetworkSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    if snapshot.is_locked:
        raise HTTPException(status_code=400, detail="Cannot delete locked snapshot")

    # Delete associated MAC locations first (cascade should handle this, but be explicit)
    db.query(SnapshotMacLocation).filter(SnapshotMacLocation.snapshot_id == snapshot_id).delete()
    db.delete(snapshot)
    db.commit()

    return {"message": "Snapshot deleted successfully"}


@router.get("/{snapshot_id}/macs", response_model=dict)
async def get_snapshot_macs(
    snapshot_id: int,
    search: Optional[str] = Query(None),
    switch_hostname: Optional[str] = Query(None),
    site_code: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get MAC addresses from a specific snapshot."""
    snapshot = db.query(NetworkSnapshot).filter(NetworkSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    query = db.query(SnapshotMacLocation).filter(SnapshotMacLocation.snapshot_id == snapshot_id)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (SnapshotMacLocation.mac_address.ilike(pattern)) |
            (SnapshotMacLocation.ip_address.ilike(pattern)) |
            (SnapshotMacLocation.hostname.ilike(pattern))
        )
    if switch_hostname:
        query = query.filter(SnapshotMacLocation.switch_hostname.ilike(f"%{switch_hostname}%"))
    if site_code:
        query = query.filter(SnapshotMacLocation.site_code == site_code)

    total = query.count()
    macs = query.offset(skip).limit(limit).all()

    return {
        "snapshot_id": snapshot_id,
        "snapshot_name": snapshot.name,
        "snapshot_date": snapshot.completed_at or snapshot.started_at,
        "total": total,
        "items": [
            SnapshotMacResponse(
                mac_address=m.mac_address,
                ip_address=m.ip_address,
                hostname=m.hostname,
                vendor_name=m.vendor_name,
                device_type=m.device_type,
                switch_hostname=m.switch_hostname,
                switch_ip=m.switch_ip,
                port_name=m.port_name,
                vlan_id=m.vlan_id,
                site_code=m.site_code
            ).model_dump() for m in macs
        ]
    }


@router.get("/compare/{snapshot1_id}/{snapshot2_id}", response_model=SnapshotCompareResult)
async def compare_snapshots(
    snapshot1_id: int,
    snapshot2_id: int,
    db: Session = Depends(get_db)
):
    """Compare two snapshots to find differences.

    Returns:
    - added_macs: MACs present in snapshot2 but not in snapshot1
    - removed_macs: MACs present in snapshot1 but not in snapshot2
    - moved_macs: MACs that changed location between snapshots
    """
    snapshot1 = db.query(NetworkSnapshot).filter(NetworkSnapshot.id == snapshot1_id).first()
    snapshot2 = db.query(NetworkSnapshot).filter(NetworkSnapshot.id == snapshot2_id).first()

    if not snapshot1:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot1_id} not found")
    if not snapshot2:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot2_id} not found")

    # Get MACs from both snapshots
    macs1 = {
        m.mac_address: m for m in
        db.query(SnapshotMacLocation).filter(SnapshotMacLocation.snapshot_id == snapshot1_id).all()
    }
    macs2 = {
        m.mac_address: m for m in
        db.query(SnapshotMacLocation).filter(SnapshotMacLocation.snapshot_id == snapshot2_id).all()
    }

    added_macs = []
    removed_macs = []
    moved_macs = []

    # Find added (in snapshot2 but not in snapshot1)
    for mac_addr in macs2:
        if mac_addr not in macs1:
            m = macs2[mac_addr]
            added_macs.append({
                "mac_address": m.mac_address,
                "ip_address": m.ip_address,
                "vendor_name": m.vendor_name,
                "switch_hostname": m.switch_hostname,
                "port_name": m.port_name,
                "vlan_id": m.vlan_id
            })

    # Find removed (in snapshot1 but not in snapshot2)
    for mac_addr in macs1:
        if mac_addr not in macs2:
            m = macs1[mac_addr]
            removed_macs.append({
                "mac_address": m.mac_address,
                "ip_address": m.ip_address,
                "vendor_name": m.vendor_name,
                "switch_hostname": m.switch_hostname,
                "port_name": m.port_name,
                "vlan_id": m.vlan_id
            })

    # Find moved (present in both but different location)
    for mac_addr in macs1:
        if mac_addr in macs2:
            m1 = macs1[mac_addr]
            m2 = macs2[mac_addr]
            if m1.switch_hostname != m2.switch_hostname or m1.port_name != m2.port_name:
                moved_macs.append({
                    "mac_address": mac_addr,
                    "vendor_name": m2.vendor_name,
                    "from_switch": m1.switch_hostname,
                    "from_port": m1.port_name,
                    "from_vlan": m1.vlan_id,
                    "to_switch": m2.switch_hostname,
                    "to_port": m2.port_name,
                    "to_vlan": m2.vlan_id
                })

    return SnapshotCompareResult(
        snapshot1_id=snapshot1_id,
        snapshot1_name=snapshot1.name,
        snapshot1_date=snapshot1.completed_at or snapshot1.started_at,
        snapshot2_id=snapshot2_id,
        snapshot2_name=snapshot2.name,
        snapshot2_date=snapshot2.completed_at or snapshot2.started_at,
        added_macs=added_macs,
        removed_macs=removed_macs,
        moved_macs=moved_macs,
        stats={
            "snapshot1_total": len(macs1),
            "snapshot2_total": len(macs2),
            "added_count": len(added_macs),
            "removed_count": len(removed_macs),
            "moved_count": len(moved_macs),
            "unchanged_count": len(macs1) - len(removed_macs) - len(moved_macs)
        }
    )


# ================================
# Snapshot Scheduler Endpoints
# ================================

class SchedulerConfigRequest(BaseModel):
    enabled: bool = False
    interval_hours: int = 6


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get snapshot scheduler status."""
    from app.services.snapshots.snapshot_scheduler import get_snapshot_scheduler

    scheduler = get_snapshot_scheduler()
    return scheduler.get_status()


@router.post("/scheduler/configure")
async def configure_scheduler(config: SchedulerConfigRequest):
    """Configure snapshot scheduler.

    Args:
        enabled: Whether automatic snapshots are enabled
        interval_hours: Hours between snapshots (default: 6)
    """
    from app.services.snapshots.snapshot_scheduler import get_snapshot_scheduler

    scheduler = get_snapshot_scheduler()
    scheduler.configure(enabled=config.enabled, interval_hours=config.interval_hours)

    return {
        "message": "Scheduler configured successfully",
        "config": scheduler.get_status()["config"]
    }


@router.post("/scheduler/run-now")
async def run_snapshot_now():
    """Run a snapshot immediately."""
    from app.services.snapshots.snapshot_scheduler import get_snapshot_scheduler

    scheduler = get_snapshot_scheduler()
    result = scheduler.run_manual_snapshot()

    return result
