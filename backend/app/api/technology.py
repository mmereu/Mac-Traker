"""Technology Tables API - IP Fabric-like views for VLANs, Switchports, etc."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, case
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.db.database import get_db
from app.db.models import MacLocation, Switch, Port, MacAddress

router = APIRouter()


# =============================================================================
# VLAN TABLE
# =============================================================================

class VlanSummary(BaseModel):
    vlan_id: int
    mac_count: int
    switch_count: int
    port_count: int
    sites: List[str]
    top_vendors: List[dict]


class VlanListResponse(BaseModel):
    items: List[VlanSummary]
    total: int


@router.get("/vlans", response_model=VlanListResponse, tags=["Technology Tables"])
async def list_vlans(
    site_code: Optional[str] = Query(None, description="Filter by site code"),
    min_macs: Optional[int] = Query(None, description="Minimum MAC count"),
    db: Session = Depends(get_db)
):
    """Get VLAN summary table with MAC counts per VLAN.

    Returns aggregated view of VLANs showing:
    - Total MAC addresses per VLAN
    - Number of switches using each VLAN
    - Number of ports with MACs in each VLAN
    - Sites where VLAN is present
    - Top vendors per VLAN
    """
    # Base query for VLAN aggregation
    query = db.query(
        MacLocation.vlan_id,
        func.count(distinct(MacLocation.mac_id)).label('mac_count'),
        func.count(distinct(MacLocation.switch_id)).label('switch_count'),
        func.count(distinct(MacLocation.port_id)).label('port_count')
    ).filter(
        MacLocation.vlan_id.isnot(None),
        MacLocation.is_current == True
    )

    if site_code:
        query = query.join(Switch, MacLocation.switch_id == Switch.id).filter(
            Switch.site_code == site_code
        )

    query = query.group_by(MacLocation.vlan_id)

    if min_macs:
        query = query.having(func.count(distinct(MacLocation.mac_id)) >= min_macs)

    query = query.order_by(func.count(distinct(MacLocation.mac_id)).desc())

    results = query.all()

    items = []
    for row in results:
        vlan_id = row.vlan_id

        # Get sites for this VLAN
        sites_query = db.query(distinct(Switch.site_code)).join(
            MacLocation, MacLocation.switch_id == Switch.id
        ).filter(
            MacLocation.vlan_id == vlan_id,
            MacLocation.is_current == True,
            Switch.site_code.isnot(None)
        ).all()
        sites = [s[0] for s in sites_query if s[0]]

        # Get top vendors for this VLAN
        vendors_query = db.query(
            MacAddress.vendor_name,
            func.count(MacAddress.id).label('count')
        ).join(
            MacLocation, MacLocation.mac_id == MacAddress.id
        ).filter(
            MacLocation.vlan_id == vlan_id,
            MacLocation.is_current == True,
            MacAddress.vendor_name.isnot(None)
        ).group_by(
            MacAddress.vendor_name
        ).order_by(
            func.count(MacAddress.id).desc()
        ).limit(5).all()

        top_vendors = [{"vendor": v[0], "count": v[1]} for v in vendors_query]

        items.append(VlanSummary(
            vlan_id=vlan_id,
            mac_count=row.mac_count,
            switch_count=row.switch_count,
            port_count=row.port_count,
            sites=sorted(sites),
            top_vendors=top_vendors
        ))

    return VlanListResponse(items=items, total=len(items))


# =============================================================================
# SWITCHPORT TABLE
# =============================================================================

class SwitchportSummary(BaseModel):
    switch_id: int
    switch_hostname: str
    switch_ip: str
    site_code: Optional[str]
    port_id: int
    port_name: str
    vlan_id: Optional[int]
    mac_count: int
    is_uplink: bool
    top_macs: List[dict]


class SwitchportListResponse(BaseModel):
    items: List[SwitchportSummary]
    total: int


@router.get("/switchports", response_model=SwitchportListResponse, tags=["Technology Tables"])
async def list_switchports(
    switch_id: Optional[int] = Query(None, description="Filter by switch ID"),
    site_code: Optional[str] = Query(None, description="Filter by site code"),
    vlan_id: Optional[int] = Query(None, description="Filter by VLAN ID"),
    min_macs: Optional[int] = Query(None, description="Minimum MAC count per port"),
    is_uplink: Optional[bool] = Query(None, description="Filter uplink/access ports"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get switchport table with MAC counts per port.

    Returns detailed view of switchports showing:
    - Switch and port information
    - VLAN assignment
    - MAC count on port
    - Uplink detection
    - Top MACs on each port
    """
    # Build query for ports with MAC counts
    query = db.query(
        Port.id.label('port_id'),
        Port.name.label('port_name'),
        Port.is_uplink,
        Switch.id.label('switch_id'),
        Switch.hostname.label('switch_hostname'),
        Switch.ip_address.label('switch_ip'),
        Switch.site_code,
        func.count(distinct(MacLocation.mac_id)).label('mac_count'),
        func.max(MacLocation.vlan_id).label('vlan_id')
    ).join(
        Switch, Port.switch_id == Switch.id
    ).outerjoin(
        MacLocation, (MacLocation.port_id == Port.id) & (MacLocation.is_current == True)
    )

    if switch_id:
        query = query.filter(Switch.id == switch_id)
    if site_code:
        query = query.filter(Switch.site_code == site_code)
    if vlan_id:
        query = query.filter(MacLocation.vlan_id == vlan_id)
    if is_uplink is not None:
        query = query.filter(Port.is_uplink == is_uplink)

    query = query.group_by(
        Port.id, Port.name, Port.is_uplink,
        Switch.id, Switch.hostname, Switch.ip_address, Switch.site_code
    )

    if min_macs:
        query = query.having(func.count(distinct(MacLocation.mac_id)) >= min_macs)

    # Get total count
    total_query = query.subquery()
    total = db.query(func.count()).select_from(total_query).scalar()

    # Apply pagination and ordering
    query = query.order_by(func.count(distinct(MacLocation.mac_id)).desc())
    query = query.offset(skip).limit(limit)

    results = query.all()

    items = []
    for row in results:
        # Get top MACs for this port
        top_macs_query = db.query(
            MacAddress.mac_address,
            MacAddress.vendor_name
        ).join(
            MacLocation, MacLocation.mac_id == MacAddress.id
        ).filter(
            MacLocation.port_id == row.port_id,
            MacLocation.is_current == True
        ).limit(5).all()

        top_macs = [{"mac": m[0], "vendor": m[1]} for m in top_macs_query]

        items.append(SwitchportSummary(
            switch_id=row.switch_id,
            switch_hostname=row.switch_hostname,
            switch_ip=row.switch_ip,
            site_code=row.site_code,
            port_id=row.port_id,
            port_name=row.port_name,
            vlan_id=row.vlan_id,
            mac_count=row.mac_count,
            is_uplink=row.is_uplink or False,
            top_macs=top_macs
        ))

    return SwitchportListResponse(items=items, total=total or 0)


# =============================================================================
# VLAN DETAIL
# =============================================================================

class VlanDetailResponse(BaseModel):
    vlan_id: int
    total_macs: int
    total_switches: int
    total_ports: int
    sites: List[str]
    switches: List[dict]
    vendors: List[dict]
    device_types: List[dict]


@router.get("/vlans/{vlan_id}", response_model=VlanDetailResponse, tags=["Technology Tables"])
async def get_vlan_detail(vlan_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific VLAN."""

    # Get aggregates
    stats = db.query(
        func.count(distinct(MacLocation.mac_id)).label('mac_count'),
        func.count(distinct(MacLocation.switch_id)).label('switch_count'),
        func.count(distinct(MacLocation.port_id)).label('port_count')
    ).filter(
        MacLocation.vlan_id == vlan_id,
        MacLocation.is_current == True
    ).first()

    # Get sites
    sites_query = db.query(distinct(Switch.site_code)).join(
        MacLocation, MacLocation.switch_id == Switch.id
    ).filter(
        MacLocation.vlan_id == vlan_id,
        MacLocation.is_current == True,
        Switch.site_code.isnot(None)
    ).all()
    sites = sorted([s[0] for s in sites_query if s[0]])

    # Get switches with MAC counts
    switches_query = db.query(
        Switch.id,
        Switch.hostname,
        Switch.ip_address,
        Switch.site_code,
        func.count(distinct(MacLocation.mac_id)).label('mac_count')
    ).join(
        MacLocation, MacLocation.switch_id == Switch.id
    ).filter(
        MacLocation.vlan_id == vlan_id,
        MacLocation.is_current == True
    ).group_by(
        Switch.id, Switch.hostname, Switch.ip_address, Switch.site_code
    ).order_by(
        func.count(distinct(MacLocation.mac_id)).desc()
    ).limit(20).all()

    switches = [{
        "id": s[0],
        "hostname": s[1],
        "ip_address": s[2],
        "site_code": s[3],
        "mac_count": s[4]
    } for s in switches_query]

    # Get vendor distribution
    vendors_query = db.query(
        MacAddress.vendor_name,
        func.count(MacAddress.id).label('count')
    ).join(
        MacLocation, MacLocation.mac_id == MacAddress.id
    ).filter(
        MacLocation.vlan_id == vlan_id,
        MacLocation.is_current == True
    ).group_by(
        MacAddress.vendor_name
    ).order_by(
        func.count(MacAddress.id).desc()
    ).limit(10).all()

    vendors = [{"name": v[0] or "Unknown", "count": v[1]} for v in vendors_query]

    # Get device type distribution
    device_types_query = db.query(
        MacAddress.device_type,
        func.count(MacAddress.id).label('count')
    ).join(
        MacLocation, MacLocation.mac_id == MacAddress.id
    ).filter(
        MacLocation.vlan_id == vlan_id,
        MacLocation.is_current == True
    ).group_by(
        MacAddress.device_type
    ).order_by(
        func.count(MacAddress.id).desc()
    ).all()

    device_types = [{"type": d[0] or "unknown", "count": d[1]} for d in device_types_query]

    return VlanDetailResponse(
        vlan_id=vlan_id,
        total_macs=stats.mac_count if stats else 0,
        total_switches=stats.switch_count if stats else 0,
        total_ports=stats.port_count if stats else 0,
        sites=sites,
        switches=switches,
        vendors=vendors,
        device_types=device_types
    )


# =============================================================================
# TECHNOLOGY STATS
# =============================================================================

class TechnologyStats(BaseModel):
    total_vlans: int
    total_switchports: int
    uplink_ports: int
    access_ports: int
    ports_with_macs: int
    top_vlans: List[dict]


@router.get("/stats", response_model=TechnologyStats, tags=["Technology Tables"])
async def get_technology_stats(db: Session = Depends(get_db)):
    """Get overall technology statistics."""

    # Count distinct VLANs
    vlan_count = db.query(func.count(distinct(MacLocation.vlan_id))).filter(
        MacLocation.vlan_id.isnot(None),
        MacLocation.is_current == True
    ).scalar() or 0

    # Count ports
    total_ports = db.query(func.count(Port.id)).scalar() or 0
    uplink_ports = db.query(func.count(Port.id)).filter(Port.is_uplink == True).scalar() or 0
    access_ports = total_ports - uplink_ports

    # Ports with MACs
    ports_with_macs = db.query(func.count(distinct(MacLocation.port_id))).filter(
        MacLocation.is_current == True
    ).scalar() or 0

    # Top VLANs by MAC count
    top_vlans_query = db.query(
        MacLocation.vlan_id,
        func.count(distinct(MacLocation.mac_id)).label('mac_count')
    ).filter(
        MacLocation.vlan_id.isnot(None),
        MacLocation.is_current == True
    ).group_by(
        MacLocation.vlan_id
    ).order_by(
        func.count(distinct(MacLocation.mac_id)).desc()
    ).limit(10).all()

    top_vlans = [{"vlan_id": v[0], "mac_count": v[1]} for v in top_vlans_query]

    return TechnologyStats(
        total_vlans=vlan_count,
        total_switchports=total_ports,
        uplink_ports=uplink_ports,
        access_ports=access_ports,
        ports_with_macs=ports_with_macs,
        top_vlans=top_vlans
    )
