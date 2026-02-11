"""API endpoints for Host management (IP Fabric-like host table)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Host, MacAddress, MacLocation, Switch, Port

router = APIRouter(prefix="/hosts", tags=["hosts"])


# Pydantic schemas
class HostResponse(BaseModel):
    id: int
    mac_address: str
    ip_address: Optional[str]
    hostname: Optional[str]
    vendor_oui: Optional[str]
    vendor_name: Optional[str]
    device_type: Optional[str]
    device_model: Optional[str]
    os_type: Optional[str]
    edge_switch_id: Optional[int]
    edge_switch_hostname: Optional[str]
    edge_switch_ip: Optional[str]
    edge_port_id: Optional[int]
    edge_port_name: Optional[str]
    vlan_id: Optional[int]
    vrf: Optional[str]
    site_code: Optional[str]
    is_infrastructure: bool
    is_virtual: bool
    is_critical: bool
    discovery_attempted: bool
    discovery_result: Optional[str]
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


class HostListResponse(BaseModel):
    items: list[HostResponse]
    total: int


class HostUpdate(BaseModel):
    hostname: Optional[str] = None
    device_type: Optional[str] = None
    is_critical: Optional[bool] = None
    notes: Optional[str] = None


class HostStats(BaseModel):
    total_hosts: int
    active_hosts: int
    infrastructure_devices: int
    virtual_devices: int
    critical_devices: int
    by_device_type: dict
    by_vendor: dict
    by_site: dict


@router.get("", response_model=HostListResponse)
async def list_hosts(
    search: Optional[str] = Query(None, description="Search by MAC, IP, hostname"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    site_code: Optional[str] = Query(None, description="Filter by site code"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_critical: Optional[bool] = Query(None, description="Filter by critical flag"),
    is_infrastructure: Optional[bool] = Query(None, description="Filter infrastructure devices"),
    edge_switch_id: Optional[int] = Query(None, description="Filter by edge switch"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """List hosts with filtering and pagination."""
    query = db.query(Host)

    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Host.mac_address.ilike(search_pattern),
                Host.ip_address.ilike(search_pattern),
                Host.hostname.ilike(search_pattern),
                Host.vendor_name.ilike(search_pattern)
            )
        )

    if device_type:
        query = query.filter(Host.device_type == device_type)
    if site_code:
        query = query.filter(Host.site_code == site_code)
    if is_active is not None:
        query = query.filter(Host.is_active == is_active)
    if is_critical is not None:
        query = query.filter(Host.is_critical == is_critical)
    if is_infrastructure is not None:
        query = query.filter(Host.is_infrastructure == is_infrastructure)
    if edge_switch_id:
        query = query.filter(Host.edge_switch_id == edge_switch_id)

    total = query.count()
    hosts = query.order_by(Host.last_seen.desc()).offset(skip).limit(limit).all()

    # Enrich with switch/port names
    items = []
    for host in hosts:
        host_dict = {
            "id": host.id,
            "mac_address": host.mac_address,
            "ip_address": host.ip_address,
            "hostname": host.hostname,
            "vendor_oui": host.vendor_oui,
            "vendor_name": host.vendor_name,
            "device_type": host.device_type,
            "device_model": host.device_model,
            "os_type": host.os_type,
            "edge_switch_id": host.edge_switch_id,
            "edge_switch_hostname": None,
            "edge_switch_ip": None,
            "edge_port_id": host.edge_port_id,
            "edge_port_name": None,
            "vlan_id": host.vlan_id,
            "vrf": host.vrf,
            "site_code": host.site_code,
            "is_infrastructure": host.is_infrastructure,
            "is_virtual": host.is_virtual,
            "is_critical": host.is_critical,
            "discovery_attempted": host.discovery_attempted,
            "discovery_result": host.discovery_result,
            "first_seen": host.first_seen,
            "last_seen": host.last_seen,
            "is_active": host.is_active,
            "notes": host.notes
        }

        # Get switch info
        if host.edge_switch_id:
            switch = db.query(Switch).filter(Switch.id == host.edge_switch_id).first()
            if switch:
                host_dict["edge_switch_hostname"] = switch.hostname
                host_dict["edge_switch_ip"] = switch.ip_address

        # Get port info
        if host.edge_port_id:
            port = db.query(Port).filter(Port.id == host.edge_port_id).first()
            if port:
                host_dict["edge_port_name"] = port.port_name

        items.append(HostResponse(**host_dict))

    return HostListResponse(items=items, total=total)


@router.get("/stats", response_model=HostStats)
async def get_host_stats(db: Session = Depends(get_db)):
    """Get host statistics."""
    total = db.query(func.count(Host.id)).scalar() or 0
    active = db.query(func.count(Host.id)).filter(Host.is_active == True).scalar() or 0
    infrastructure = db.query(func.count(Host.id)).filter(Host.is_infrastructure == True).scalar() or 0
    virtual = db.query(func.count(Host.id)).filter(Host.is_virtual == True).scalar() or 0
    critical = db.query(func.count(Host.id)).filter(Host.is_critical == True).scalar() or 0

    # By device type
    type_counts = db.query(
        Host.device_type, func.count(Host.id)
    ).group_by(Host.device_type).all()
    by_type = {t or "unknown": c for t, c in type_counts}

    # By vendor (top 10)
    vendor_counts = db.query(
        Host.vendor_name, func.count(Host.id)
    ).group_by(Host.vendor_name).order_by(func.count(Host.id).desc()).limit(10).all()
    by_vendor = {v or "unknown": c for v, c in vendor_counts}

    # By site
    site_counts = db.query(
        Host.site_code, func.count(Host.id)
    ).group_by(Host.site_code).all()
    by_site = {s or "unknown": c for s, c in site_counts}

    return HostStats(
        total_hosts=total,
        active_hosts=active,
        infrastructure_devices=infrastructure,
        virtual_devices=virtual,
        critical_devices=critical,
        by_device_type=by_type,
        by_vendor=by_vendor,
        by_site=by_site
    )


@router.get("/sync", response_model=dict)
async def sync_hosts_from_macs(db: Session = Depends(get_db)):
    """Synchronize hosts table from MAC addresses and locations.

    This creates/updates Host records based on current MAC address data.
    """
    created = 0
    updated = 0

    # Get all MAC addresses with their current locations
    macs_with_locations = db.query(MacAddress, MacLocation).outerjoin(
        MacLocation, (MacAddress.id == MacLocation.mac_id) & (MacLocation.is_current == True)
    ).all()

    for mac, location in macs_with_locations:
        # Check if host exists
        host = db.query(Host).filter(Host.mac_address == mac.mac_address).first()

        if not host:
            # Create new host
            host = Host(
                mac_address=mac.mac_address,
                vendor_oui=mac.vendor_oui,
                vendor_name=mac.vendor_name,
                device_type=mac.device_type,
                first_seen=mac.first_seen,
                last_seen=mac.last_seen,
                is_active=mac.is_active
            )

            # Detect virtual by OUI
            if mac.vendor_name and any(v in mac.vendor_name.lower() for v in ['vmware', 'virtual', 'hyperv', 'kvm', 'xen']):
                host.is_virtual = True

            # Detect infrastructure by OUI
            if mac.vendor_name and any(v in mac.vendor_name.lower() for v in ['cisco', 'huawei', 'juniper', 'arista', 'extreme', 'hp networking', 'dell networking']):
                host.is_infrastructure = True

            db.add(host)
            db.flush()  # Flush immediately to avoid duplicates
            created += 1
        else:
            # Update existing host
            host.vendor_oui = mac.vendor_oui
            host.vendor_name = mac.vendor_name
            if mac.device_type:
                host.device_type = mac.device_type
            host.last_seen = mac.last_seen
            host.is_active = mac.is_active
            updated += 1

        # Update location from MacLocation if available
        if location:
            host.ip_address = location.ip_address
            host.hostname = location.hostname
            host.edge_switch_id = location.switch_id
            host.edge_port_id = location.port_id
            host.vlan_id = location.vlan_id

            # Get site code from switch
            switch = db.query(Switch).filter(Switch.id == location.switch_id).first()
            if switch:
                host.site_code = switch.site_code

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "message": f"Synchronized {created + updated} hosts ({created} new, {updated} updated)"
    }


@router.get("/{host_id}", response_model=HostResponse)
async def get_host(host_id: int, db: Session = Depends(get_db)):
    """Get a specific host by ID."""
    host = db.query(Host).filter(Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    host_dict = {
        "id": host.id,
        "mac_address": host.mac_address,
        "ip_address": host.ip_address,
        "hostname": host.hostname,
        "vendor_oui": host.vendor_oui,
        "vendor_name": host.vendor_name,
        "device_type": host.device_type,
        "device_model": host.device_model,
        "os_type": host.os_type,
        "edge_switch_id": host.edge_switch_id,
        "edge_switch_hostname": None,
        "edge_switch_ip": None,
        "edge_port_id": host.edge_port_id,
        "edge_port_name": None,
        "vlan_id": host.vlan_id,
        "vrf": host.vrf,
        "site_code": host.site_code,
        "is_infrastructure": host.is_infrastructure,
        "is_virtual": host.is_virtual,
        "is_critical": host.is_critical,
        "discovery_attempted": host.discovery_attempted,
        "discovery_result": host.discovery_result,
        "first_seen": host.first_seen,
        "last_seen": host.last_seen,
        "is_active": host.is_active,
        "notes": host.notes
    }

    # Get switch info
    if host.edge_switch_id:
        switch = db.query(Switch).filter(Switch.id == host.edge_switch_id).first()
        if switch:
            host_dict["edge_switch_hostname"] = switch.hostname
            host_dict["edge_switch_ip"] = switch.ip_address

    # Get port info
    if host.edge_port_id:
        port = db.query(Port).filter(Port.id == host.edge_port_id).first()
        if port:
            host_dict["edge_port_name"] = port.port_name

    return HostResponse(**host_dict)


@router.put("/{host_id}", response_model=HostResponse)
async def update_host(host_id: int, data: HostUpdate, db: Session = Depends(get_db)):
    """Update host information (user-editable fields only)."""
    host = db.query(Host).filter(Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    if data.hostname is not None:
        host.hostname = data.hostname
    if data.device_type is not None:
        host.device_type = data.device_type
    if data.is_critical is not None:
        host.is_critical = data.is_critical
    if data.notes is not None:
        host.notes = data.notes

    db.commit()
    db.refresh(host)

    return await get_host(host_id, db)


@router.delete("/{host_id}")
async def delete_host(host_id: int, db: Session = Depends(get_db)):
    """Delete a host record."""
    host = db.query(Host).filter(Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    db.delete(host)
    db.commit()

    return {"message": "Host deleted successfully"}


# ===============================
# Active Host Discovery Endpoints
# ===============================

class PingSweepRequest(BaseModel):
    subnet: str  # e.g., "10.1.1.0/24"
    timeout: int = 1  # seconds per host
    concurrent: int = 50  # max concurrent pings


class PingSweepResult(BaseModel):
    subnet: str
    total_scanned: int
    hosts_up: int
    hosts_down: int
    new_hosts: int
    updated_hosts: int
    results: list[dict]


class ARPScanRequest(BaseModel):
    switch_id: int  # Switch to query ARP table from
    vlan_id: Optional[int] = None


@router.post("/discovery/ping-sweep", response_model=PingSweepResult)
async def ping_sweep(request: PingSweepRequest, db: Session = Depends(get_db)):
    """
    Perform a ping sweep on a subnet to discover active hosts.

    This actively probes IP addresses and updates the host table
    with discovery results.
    """
    import asyncio
    import ipaddress
    import subprocess
    import platform

    try:
        network = ipaddress.ip_network(request.subnet, strict=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid subnet: {e}")

    hosts_list = list(network.hosts())
    if len(hosts_list) > 1024:
        raise HTTPException(status_code=400, detail="Subnet too large (max /22)")

    # Platform-specific ping command
    is_windows = platform.system().lower() == "windows"
    ping_cmd = ["ping", "-n" if is_windows else "-c", "1",
                "-w" if is_windows else "-W", str(request.timeout * 1000 if is_windows else request.timeout)]

    results = []
    hosts_up = 0
    hosts_down = 0
    new_hosts = 0
    updated_hosts = 0

    # Semaphore to limit concurrency
    semaphore = asyncio.Semaphore(request.concurrent)

    async def ping_host(ip: str):
        nonlocal hosts_up, hosts_down, new_hosts, updated_hosts

        async with semaphore:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *ping_cmd, ip,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await asyncio.wait_for(proc.wait(), timeout=request.timeout + 2)
                is_up = proc.returncode == 0
            except asyncio.TimeoutError:
                is_up = False
            except Exception:
                is_up = False

            if is_up:
                hosts_up += 1
            else:
                hosts_down += 1

            # Update host record if IP exists
            host = db.query(Host).filter(Host.ip_address == ip).first()
            if host:
                host.discovery_attempted = True
                host.discovery_result = "reachable" if is_up else "unreachable"
                host.last_seen = datetime.utcnow() if is_up else host.last_seen
                host.is_active = is_up
                updated_hosts += 1
            elif is_up:
                # Create placeholder host for discovered IP without MAC
                new_host = Host(
                    mac_address=f"DISCOVERED-{ip.replace('.', '-')}",
                    ip_address=ip,
                    discovery_attempted=True,
                    discovery_result="reachable",
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    is_active=True,
                )
                db.add(new_host)
                new_hosts += 1

            results.append({
                "ip": ip,
                "status": "up" if is_up else "down"
            })

    # Run ping sweep
    tasks = [ping_host(str(ip)) for ip in hosts_list]
    await asyncio.gather(*tasks)

    db.commit()

    return PingSweepResult(
        subnet=request.subnet,
        total_scanned=len(hosts_list),
        hosts_up=hosts_up,
        hosts_down=hosts_down,
        new_hosts=new_hosts,
        updated_hosts=updated_hosts,
        results=results[:100]  # Limit results in response
    )


@router.post("/discovery/arp-scan")
async def arp_scan(request: ARPScanRequest, db: Session = Depends(get_db)):
    """
    Query ARP table from a switch to enrich host information.

    This retrieves MAC-IP mappings from the switch's ARP cache
    and updates the host table.
    """
    from app.services.discovery.snmp_discovery import SNMPDiscoveryService

    switch = db.query(Switch).filter(Switch.id == request.switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    # Use SNMP to get ARP table
    snmp_service = SNMPDiscoveryService(db)

    try:
        # Get ARP entries from switch
        arp_entries = await snmp_service.get_arp_table(switch)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SNMP error: {str(e)}")

    updated = 0
    for entry in arp_entries:
        mac = entry.get("mac_address")
        ip = entry.get("ip_address")
        vlan = entry.get("vlan_id")

        if not mac or not ip:
            continue

        if request.vlan_id and vlan != request.vlan_id:
            continue

        # Find or create host
        host = db.query(Host).filter(Host.mac_address == mac.upper()).first()
        if host:
            host.ip_address = ip
            if vlan:
                host.vlan_id = vlan
            host.last_seen = datetime.utcnow()
            host.is_active = True
            updated += 1

    db.commit()

    return {
        "switch_id": switch.id,
        "switch_hostname": switch.hostname,
        "arp_entries_found": len(arp_entries),
        "hosts_updated": updated,
    }


@router.get("/discovery/status")
async def discovery_status(db: Session = Depends(get_db)):
    """Get active discovery statistics."""
    total = db.query(func.count(Host.id)).scalar()
    attempted = db.query(func.count(Host.id)).filter(Host.discovery_attempted == True).scalar()
    reachable = db.query(func.count(Host.id)).filter(Host.discovery_result == "reachable").scalar()
    unreachable = db.query(func.count(Host.id)).filter(Host.discovery_result == "unreachable").scalar()

    return {
        "total_hosts": total,
        "discovery_attempted": attempted,
        "reachable": reachable,
        "unreachable": unreachable,
        "not_tested": total - attempted,
    }
