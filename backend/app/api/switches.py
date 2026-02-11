"""Switch API endpoints."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import func, select, delete, or_

from app.db.database import get_db
from app.db.models import Switch, SwitchGroup, MacLocation, Port, Alert, MacHistory, TopologyLink, DiscoveryLog
from app.api.schemas import (
    SwitchCreate,
    SwitchUpdate,
    SwitchResponse,
    SwitchListResponse,
    SwitchGroupBasic,
    PortResponse,
    PortListResponse,
    DeleteResult,
    BulkDeleteRequest,
)

router = APIRouter()


def get_switch_with_mac_count(db: Session, switch: Switch) -> dict:
    """Get switch data with mac_count and SNMP-discovered system info."""
    mac_count = db.query(func.count(MacLocation.id)).filter(
        MacLocation.switch_id == switch.id,
        MacLocation.is_current == True
    ).scalar() or 0

    # Handle missing columns gracefully
    try:
        use_ssh_fallback = switch.use_ssh_fallback
    except Exception:
        use_ssh_fallback = False

    try:
        sys_name = switch.sys_name
    except Exception:
        sys_name = None

    try:
        ports_up_count = switch.ports_up_count or 0
    except Exception:
        ports_up_count = 0

    try:
        ports_down_count = switch.ports_down_count or 0
    except Exception:
        ports_down_count = 0

    try:
        vlan_count = switch.vlan_count or 0
    except Exception:
        vlan_count = 0

    # Get site_code
    try:
        site_code = switch.site_code
    except Exception:
        site_code = None

    result = {
        "id": switch.id,
        "hostname": switch.hostname,
        "ip_address": switch.ip_address,
        "device_type": switch.device_type,
        "snmp_community": switch.snmp_community,
        "group_id": switch.group_id,
        "location": switch.location,
        "model": switch.model,
        "serial_number": switch.serial_number,
        "is_active": switch.is_active,
        "use_ssh_fallback": use_ssh_fallback,
        "last_seen": switch.last_seen,
        "last_discovery": switch.last_discovery,
        "created_at": switch.created_at,
        "group": None,
        "mac_count": mac_count,
        # SNMP-discovered system information
        "sys_name": sys_name,
        "ports_up_count": ports_up_count,
        "ports_down_count": ports_down_count,
        "vlan_count": vlan_count,
        # Site code from hostname prefix
        "site_code": site_code,
    }

    if switch.group:
        result["group"] = SwitchGroupBasic(id=switch.group.id, name=switch.group.name)

    return result


@router.get("", response_model=SwitchListResponse)
def list_switches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    device_type: Optional[str] = None,
    group_id: Optional[int] = None,
    site_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """List all switches with optional filtering."""
    query = db.query(Switch)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Switch.hostname.ilike(search_term)) |
            (Switch.ip_address.ilike(search_term)) |
            (Switch.location.ilike(search_term))
        )

    if device_type:
        query = query.filter(Switch.device_type == device_type)

    if group_id is not None:
        query = query.filter(Switch.group_id == group_id)

    if site_code is not None:
        query = query.filter(Switch.site_code == site_code)

    if is_active is not None:
        query = query.filter(Switch.is_active == is_active)

    total = query.count()
    switches = query.order_by(Switch.hostname).offset(skip).limit(limit).all()

    items = [get_switch_with_mac_count(db, sw) for sw in switches]

    return SwitchListResponse(items=items, total=total)


import re


def extract_site_code(hostname: str) -> Optional[str]:
    """Extract site code from hostname prefix (e.g., '01' from '01_L2_switch').

    Supports formats:
    - XX_ (2 digits + underscore)
    - XXX_ (3 digits + underscore)
    """
    if not hostname:
        return None
    match = re.match(r'^(\d{2,3})_', hostname)
    if match:
        return match.group(1)
    return None


# IMPORTANT: Static routes MUST be defined BEFORE /{switch_id} routes
# Otherwise FastAPI will try to parse "site-codes" as switch_id integer

@router.get("/site-codes")
def get_site_codes(db: Session = Depends(get_db)):
    """Get all unique site codes from switch hostnames with counts."""
    switches = db.query(Switch).all()

    site_codes = {}
    for sw in switches:
        code = extract_site_code(sw.hostname)
        if code:
            if code not in site_codes:
                site_codes[code] = {"code": code, "count": 0}
            site_codes[code]["count"] += 1

    # Sort by code and return as list
    result = sorted(site_codes.values(), key=lambda x: x["code"])
    return result


@router.post("/auto-assign-site-codes")
def auto_assign_site_codes(db: Session = Depends(get_db)):
    """Automatically extract and assign site_code to all switches based on hostname prefix."""
    switches = db.query(Switch).all()

    updated = 0
    skipped = 0

    for sw in switches:
        code = extract_site_code(sw.hostname)
        if code:
            sw.site_code = code
            updated += 1
        else:
            skipped += 1

    db.commit()
    return {
        "success": True,
        "updated": updated,
        "skipped": skipped,
        "message": f"Assegnati {updated} site codes, {skipped} switch senza prefisso valido"
    }


@router.post("/auto-create-groups")
def auto_create_groups(db: Session = Depends(get_db)):
    """Automatically create groups based on site codes and assign switches to them."""
    # First, assign site codes
    switches = db.query(Switch).all()

    site_codes = {}
    for sw in switches:
        code = extract_site_code(sw.hostname)
        if code:
            sw.site_code = code
            if code not in site_codes:
                site_codes[code] = []
            site_codes[code].append(sw)

    created_groups = 0
    updated_groups = 0
    assigned_switches = 0

    for code, switch_list in site_codes.items():
        group_name = f"Sede {code}"

        # Check if group exists
        group = db.query(SwitchGroup).filter(SwitchGroup.name == group_name).first()

        if not group:
            # Create new group
            group = SwitchGroup(
                name=group_name,
                description=f"Gruppo auto-generato per sede {code}"
            )
            db.add(group)
            db.flush()
            created_groups += 1
        else:
            updated_groups += 1

        # Assign switches to group
        for sw in switch_list:
            sw.group_id = group.id
            assigned_switches += 1

    db.commit()

    return {
        "success": True,
        "created_groups": created_groups,
        "updated_groups": updated_groups,
        "assigned_switches": assigned_switches,
        "total_sites": len(site_codes),
        "message": f"Creati {created_groups} nuovi gruppi, aggiornati {updated_groups} esistenti, assegnati {assigned_switches} switch"
    }


@router.post("", response_model=SwitchResponse, status_code=201)
def create_switch(switch_data: SwitchCreate, db: Session = Depends(get_db)):
    """Create a new switch."""
    # Check for duplicate hostname
    existing = db.query(Switch).filter(Switch.hostname == switch_data.hostname).first()
    if existing:
        raise HTTPException(status_code=400, detail="Switch con questo hostname esiste gia'")

    # Check for duplicate IP
    existing_ip = db.query(Switch).filter(Switch.ip_address == switch_data.ip_address).first()
    if existing_ip:
        raise HTTPException(status_code=400, detail="Switch con questo IP esiste gia'")

    # Validate group_id if provided
    if switch_data.group_id:
        group = db.query(SwitchGroup).filter(SwitchGroup.id == switch_data.group_id).first()
        if not group:
            raise HTTPException(status_code=400, detail="Gruppo non trovato")

    switch = Switch(**switch_data.model_dump())
    db.add(switch)
    db.commit()
    db.refresh(switch)

    return get_switch_with_mac_count(db, switch)


# IMPORTANT: These bulk routes MUST be defined BEFORE /{switch_id} routes
# Otherwise FastAPI will try to parse "bulk" and "all" as switch_id integers

# POST alternative for bulk delete (to avoid route ordering issues)
@router.post("/bulk-delete", response_model=DeleteResult)
def bulk_delete_switches_post(
    request: BulkDeleteRequest,
    db: Session = Depends(get_db)
):
    """Delete multiple switches and all related data in cascade (POST version)."""
    switch_ids = request.switch_ids

    if not switch_ids:
        raise HTTPException(status_code=400, detail="Nessun ID switch fornito")

    try:
        # Delete related data in order (cascade)
        db.execute(delete(Alert).where(Alert.switch_id.in_(switch_ids)))
        db.execute(delete(MacHistory).where(MacHistory.switch_id.in_(switch_ids)))
        db.execute(delete(MacLocation).where(MacLocation.switch_id.in_(switch_ids)))
        db.execute(delete(TopologyLink).where(
            or_(
                TopologyLink.local_switch_id.in_(switch_ids),
                TopologyLink.remote_switch_id.in_(switch_ids)
            )
        ))
        db.execute(delete(DiscoveryLog).where(DiscoveryLog.switch_id.in_(switch_ids)))
        db.execute(delete(Port).where(Port.switch_id.in_(switch_ids)))
        result = db.execute(delete(Switch).where(Switch.id.in_(switch_ids)))
        deleted_count = result.rowcount

        db.commit()
        return DeleteResult(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")


# POST alternative for delete all
@router.post("/delete-all", response_model=DeleteResult)
def delete_all_switches_post(
    confirm_delete: str = Header(None, alias="X-Confirm-Delete-All"),
    db: Session = Depends(get_db)
):
    """Delete ALL switches and all related data (POST version)."""
    if confirm_delete != "true":
        raise HTTPException(
            status_code=400,
            detail="Richiesto header X-Confirm-Delete-All con valore 'true' per confermare"
        )

    try:
        db.execute(delete(Alert))
        db.execute(delete(MacHistory))
        db.execute(delete(MacLocation))
        db.execute(delete(TopologyLink))
        db.execute(delete(DiscoveryLog))
        db.execute(delete(Port))
        result = db.execute(delete(Switch))
        deleted_count = result.rowcount

        db.commit()
        return DeleteResult(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")


@router.delete("/bulk", response_model=DeleteResult)
def delete_switches_bulk(
    request: BulkDeleteRequest,
    db: Session = Depends(get_db)
):
    """Delete multiple switches and all related data in cascade."""
    switch_ids = request.switch_ids

    if not switch_ids:
        raise HTTPException(status_code=400, detail="Nessun ID switch fornito")

    try:
        # Delete related data in order (cascade)
        # 1. Alerts
        db.execute(delete(Alert).where(Alert.switch_id.in_(switch_ids)))

        # 2. MAC History
        db.execute(delete(MacHistory).where(MacHistory.switch_id.in_(switch_ids)))

        # 3. MAC Locations
        db.execute(delete(MacLocation).where(MacLocation.switch_id.in_(switch_ids)))

        # 4. Topology Links (both directions)
        db.execute(delete(TopologyLink).where(
            or_(
                TopologyLink.local_switch_id.in_(switch_ids),
                TopologyLink.remote_switch_id.in_(switch_ids)
            )
        ))

        # 5. Discovery Logs
        db.execute(delete(DiscoveryLog).where(DiscoveryLog.switch_id.in_(switch_ids)))

        # 6. Ports
        db.execute(delete(Port).where(Port.switch_id.in_(switch_ids)))

        # 7. Switches
        result = db.execute(delete(Switch).where(Switch.id.in_(switch_ids)))
        deleted_count = result.rowcount

        db.commit()
        return DeleteResult(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")


@router.delete("/all", response_model=DeleteResult)
def delete_all_switches(
    confirm_delete: str = Header(None, alias="X-Confirm-Delete-All"),
    db: Session = Depends(get_db)
):
    """Delete ALL switches and all related data. Requires confirmation header."""
    if confirm_delete != "true":
        raise HTTPException(
            status_code=400,
            detail="Richiesto header X-Confirm-Delete-All con valore 'true' per confermare"
        )

    try:
        # Delete all related data in order (cascade)
        # 1. Alerts
        db.execute(delete(Alert))

        # 2. MAC History
        db.execute(delete(MacHistory))

        # 3. MAC Locations
        db.execute(delete(MacLocation))

        # 4. Topology Links
        db.execute(delete(TopologyLink))

        # 5. Discovery Logs
        db.execute(delete(DiscoveryLog))

        # 6. Ports
        db.execute(delete(Port))

        # 7. Switches
        result = db.execute(delete(Switch))
        deleted_count = result.rowcount

        db.commit()
        return DeleteResult(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")


@router.get("/{switch_id}", response_model=SwitchResponse)
def get_switch(switch_id: int, db: Session = Depends(get_db)):
    """Get a specific switch by ID."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    return get_switch_with_mac_count(db, switch)


@router.put("/{switch_id}", response_model=SwitchResponse)
def update_switch(switch_id: int, switch_data: SwitchUpdate, db: Session = Depends(get_db)):
    """Update a switch."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    update_data = switch_data.model_dump(exclude_unset=True)

    # Check for duplicate hostname if updating
    if "hostname" in update_data and update_data["hostname"] != switch.hostname:
        existing = db.query(Switch).filter(
            Switch.hostname == update_data["hostname"],
            Switch.id != switch_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Switch con questo hostname esiste gia'")

    # Check for duplicate IP if updating
    if "ip_address" in update_data and update_data["ip_address"] != switch.ip_address:
        existing = db.query(Switch).filter(
            Switch.ip_address == update_data["ip_address"],
            Switch.id != switch_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Switch con questo IP esiste gia'")

    # Validate group_id if provided
    if "group_id" in update_data and update_data["group_id"]:
        group = db.query(SwitchGroup).filter(SwitchGroup.id == update_data["group_id"]).first()
        if not group:
            raise HTTPException(status_code=400, detail="Gruppo non trovato")

    for field, value in update_data.items():
        setattr(switch, field, value)

    db.commit()
    db.refresh(switch)

    return get_switch_with_mac_count(db, switch)


@router.delete("/{switch_id}", status_code=204)
def delete_switch(switch_id: int, db: Session = Depends(get_db)):
    """Delete a switch."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    db.delete(switch)
    db.commit()
    return None


@router.get("/{switch_id}/ports-debug")
def get_switch_ports_debug(switch_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to test port MAC counts."""
    port_ids = [p.id for p in db.query(Port).filter(Port.switch_id == switch_id).all()]
    raw_counts = (
        db.query(MacLocation.port_id, func.count(MacLocation.id))
        .filter(
            MacLocation.port_id.in_(port_ids),
            MacLocation.is_current == True
        )
        .group_by(MacLocation.port_id)
        .all()
    )
    total_locs = db.query(MacLocation).filter(MacLocation.switch_id == switch_id, MacLocation.is_current == True).count()
    return {
        "port_ids_count": len(port_ids),
        "raw_counts": list(raw_counts),
        "total_current_locations": total_locs,
        "version": "v2"
    }


@router.get("/{switch_id}/ports")
def get_switch_ports(switch_id: int, db: Session = Depends(get_db)):
    """Get all ports for a switch with live MAC counts."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    ports = db.query(Port).filter(Port.switch_id == switch_id).order_by(Port.port_name).all()

    # Calculate live MAC counts per port - count ALL current locations, not filtered by switch
    # because MacLocation already has the port_id which is unique
    port_ids = [p.id for p in ports]
    port_mac_counts_raw = (
        db.query(MacLocation.port_id, func.count(MacLocation.id))
        .filter(
            MacLocation.port_id.in_(port_ids),
            MacLocation.is_current == True
        )
        .group_by(MacLocation.port_id)
        .all()
    )
    port_mac_counts = dict(port_mac_counts_raw)

    # Build response with live MAC counts
    port_items = []
    for port in ports:
        port_dict = {
            "id": port.id,
            "switch_id": port.switch_id,
            "port_name": port.port_name,
            "port_index": port.port_index,
            "port_description": port.port_description,
            "port_type": port.port_type,
            "vlan_id": port.vlan_id,
            "admin_status": port.admin_status,
            "oper_status": port.oper_status,
            "speed": port.speed,
            "is_uplink": port.is_uplink,
            "last_mac_count": port_mac_counts.get(port.id, 0),  # Live count!
            "updated_at": port.updated_at.isoformat() if port.updated_at else None,
        }
        port_items.append(port_dict)

    return {"items": port_items, "total": len(port_items)}


@router.post("/{switch_id}/ports/recalculate-mac-counts")
def recalculate_port_mac_counts(switch_id: int, db: Session = Depends(get_db)):
    """Recalculate MAC counts for all ports of a switch."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    # Count current MAC locations per port
    port_mac_counts = (
        db.query(Port.id, func.count(MacLocation.id).label('mac_count'))
        .outerjoin(MacLocation, (MacLocation.port_id == Port.id) & (MacLocation.is_current == True))
        .filter(Port.switch_id == switch_id)
        .group_by(Port.id)
        .all()
    )

    # Update last_mac_count for each port
    updated_count = 0
    for port_id, mac_count in port_mac_counts:
        port = db.query(Port).filter(Port.id == port_id).first()
        if port:
            port.last_mac_count = mac_count
            updated_count += 1

    db.commit()

    return {"message": f"Aggiornati {updated_count} porte", "ports_updated": updated_count}


@router.post("/recalculate-all-mac-counts")
def recalculate_all_port_mac_counts(db: Session = Depends(get_db)):
    """Recalculate MAC counts for all ports of all switches."""
    # Count current MAC locations per port
    port_mac_counts = (
        db.query(Port.id, func.count(MacLocation.id).label('mac_count'))
        .outerjoin(MacLocation, (MacLocation.port_id == Port.id) & (MacLocation.is_current == True))
        .group_by(Port.id)
        .all()
    )

    # Update last_mac_count for each port
    updated_count = 0
    for port_id, mac_count in port_mac_counts:
        port = db.query(Port).filter(Port.id == port_id).first()
        if port:
            port.last_mac_count = mac_count
            updated_count += 1

    db.commit()

    return {"message": f"Aggiornati {updated_count} porte su tutti gli switch", "ports_updated": updated_count}
# reload trigger sab 24 gen 2026 15:27:39
# reload trigger sab 24 gen 2026 16:44:50
# reload trigger sab 24 gen 2026 22:17:15
