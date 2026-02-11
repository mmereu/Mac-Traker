"""MAC address API endpoints."""
import csv
import io
import logging
import re
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db


def is_regex_pattern(s: str) -> bool:
    """Check if string contains regex metacharacters."""
    regex_chars = r'^$.*+?{}[]()|\\'
    return any(c in s for c in regex_chars)


def regex_to_sql_like(pattern: str) -> str:
    """Convert simple regex patterns to SQL LIKE pattern.

    Supports common patterns:
    - ^  -> start anchor (remove, implied by no leading %)
    - $  -> end anchor (remove, implied by no trailing %)
    - .* -> %
    - .  -> _
    - [0-9] -> _ (approximation)
    - [A-F] -> _ (approximation)
    """
    # Track anchors
    start_anchor = pattern.startswith('^')
    end_anchor = pattern.endswith('$')

    # Remove anchors
    if start_anchor:
        pattern = pattern[1:]
    if end_anchor:
        pattern = pattern[:-1]

    # Convert regex to LIKE
    result = pattern
    result = result.replace('.*', '%')
    result = result.replace('.+', '_%')
    result = result.replace('.', '_')

    # Handle character classes (approximation)
    result = re.sub(r'\[[^\]]+\]', '_', result)

    # Escape SQL wildcards that weren't converted
    # (already handled by our conversions)

    # Add wildcards if no anchors
    if not start_anchor:
        result = '%' + result
    if not end_anchor:
        result = result + '%'

    return result
from app.db.models import MacAddress, MacLocation, MacHistory, Switch, Port, TopologyLink
from app.services.mac_endpoint_tracer import MacEndpointTracer

router = APIRouter()

# OUI-based endpoint exceptions: these OUIs are ALWAYS treated as endpoints
# even when found on uplink ports (Access Points, IP Phones, etc.)
# Format: with colons for SQL LIKE comparison (XX:XX:XX%)
ENDPOINT_OUIS = [
    # === ACCESS POINTS ===
    # Extreme Networks
    '00:18:6E', '00:01:2E', '5C:0E:8B', 'B4:C7:99', '00:E6:0E',
    # Aruba / HPE
    '00:0B:86', '24:DE:9A', '6C:FD:B9', '9C:1C:12', 'AC:A3:1E', 'D8:C7:C8', '20:A6:CD', '94:B4:0F',
    # Cisco Access Points (Meraki)
    '00:18:BA', '00:24:A5', '88:15:5F', '0C:8B:FD',
    # Ubiquiti
    '00:27:5D', '04:18:D6', '24:A4:3C', '44:D9:E7', '68:D7:9A', '78:8A:20',
    '80:2A:A8', 'B4:FB:E4', 'DC:9F:DB', 'E0:63:DA', 'F0:9F:C2', 'FC:EC:DA',
    # Ruckus Wireless
    'C4:10:8A', '58:B6:33', '4C:1D:96', '84:2B:2B', 'EC:58:9F', '74:91:1A',
    # Cambium Networks
    '58:C1:7A',
    # === IP PHONES ===
    # Cisco IP Phones
    '00:07:0E', '00:0F:EE', '00:11:21', '00:1A:2F', '00:1B:D4', '00:22:6B',
    '00:24:90', '00:25:66', '00:26:CB', '10:BD:EC', '1C:E6:C7', '44:2B:03',
    '50:3D:E5', '5C:F9:DD', '64:00:F1', '6C:41:6A', '7C:1E:52', 'A8:A6:66',
    'C4:64:9B', 'DC:F8:98', 'F8:B7:E2',
    # Polycom IP Phones
    '00:04:F2', '64:16:7F',
    # Yealink IP Phones
    '00:15:65', '24:CF:11', '30:9E:65', '80:5E:0C', '80:5E:C0',
    # Grandstream IP Phones
    '00:0B:82',
    # Avaya IP Phones
    '00:04:0D', '00:1B:4F', '3C:E5:A6', '70:52:1C', '7C:57:BC',
    # Snom IP Phones
    '00:04:13',
    # Mitel IP Phones
    '08:00:0F',
]


# Pydantic models for MAC API
from pydantic import BaseModel


class MacLocationResponse(BaseModel):
    switch_hostname: str
    switch_ip: str
    port_name: str
    vlan_id: Optional[int] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    seen_at: datetime
    is_current: bool


class MacSearchResult(BaseModel):
    id: int
    mac_address: str
    vendor_name: Optional[str] = None
    device_type: Optional[str] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    switch_hostname: Optional[str] = None
    switch_ip: Optional[str] = None
    port_name: Optional[str] = None
    vlan_id: Optional[int] = None
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    is_uplink: bool = False  # True if MAC is on an uplink port (not an endpoint)

    class Config:
        from_attributes = True


class MacSearchResponse(BaseModel):
    items: List[MacSearchResult]
    total: int


class MacHistoryItem(BaseModel):
    event_type: str
    event_at: datetime
    switch_id: int
    port_id: int
    vlan_id: Optional[int] = None
    ip_address: Optional[str] = None
    previous_switch_id: Optional[int] = None
    previous_port_id: Optional[int] = None


class MacDetailResponse(BaseModel):
    id: int
    mac_address: str
    vendor_oui: Optional[str] = None
    vendor_name: Optional[str] = None
    device_type: Optional[str] = None
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    current_location: Optional[MacLocationResponse] = None
    history: List[MacHistoryItem] = []

    class Config:
        from_attributes = True


@router.get("", response_model=MacSearchResponse)
def search_macs(
    q: str = Query("", description="Search query (MAC, IP, hostname, switch)"),
    switch_id: Optional[int] = None,
    vlan_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    include_uplinks: bool = Query(False, description="Include MACs on uplink ports (default: exclude)"),
    use_regex: bool = Query(False, description="Interpret query as regex pattern (e.g., ^00:18.*, .*:AB:CD$)"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Search MAC addresses by query string.

    By default, excludes MACs found on uplink ports since those are not endpoints.
    Set include_uplinks=true to include all MACs including those on uplink ports.

    RegEx support (use_regex=true):
    - ^pattern  -> starts with
    - pattern$  -> ends with
    - .*        -> any characters
    - .         -> any single character
    - [0-9A-F]  -> character class (approximated)
    Example: ^00:18:6E.*  -> all MACs starting with 00:18:6E
    """
    # Base query with current location info
    query = (
        db.query(
            MacAddress,
            MacLocation.ip_address.label("loc_ip"),
            MacLocation.hostname.label("loc_hostname"),
            MacLocation.vlan_id.label("loc_vlan"),
            Switch.hostname.label("switch_hostname"),
            Switch.ip_address.label("switch_ip"),
            Port.port_name.label("port_name"),
            Port.is_uplink.label("is_uplink"),
        )
        .outerjoin(
            MacLocation,
            (MacAddress.id == MacLocation.mac_id) & (MacLocation.is_current == True),
        )
        .outerjoin(Switch, MacLocation.switch_id == Switch.id)
        .outerjoin(Port, MacLocation.port_id == Port.id)
    )

    if not include_uplinks:
        # Show MACs on non-uplink ports (endpoint locations).
        # Exception: MACs from known endpoint OUIs (APs, IP Phones) are shown
        # even on uplink ports, because their MACs often only appear on uplinks
        # in the bridge MIB (the AP is connected to a switch port but its MAC
        # traverses through uplinks to the core).
        endpoint_oui_filters = [MacAddress.mac_address.ilike(f"{oui}%") for oui in ENDPOINT_OUIS]
        query = query.filter(
            or_(
                Port.is_uplink == False,
                Port.is_uplink.is_(None),
                *endpoint_oui_filters,
            )
        )

    # Apply search filter (with regex support)
    if q:
        if use_regex or is_regex_pattern(q):
            # Convert regex to SQL LIKE pattern
            search_term = regex_to_sql_like(q)
        else:
            # Standard substring search
            search_term = f"%{q}%"

        query = query.filter(
            or_(
                MacAddress.mac_address.ilike(search_term),
                MacLocation.ip_address.ilike(search_term),
                MacLocation.hostname.ilike(search_term),
                Switch.hostname.ilike(search_term),
                MacAddress.vendor_name.ilike(search_term),
            )
        )

    # Apply additional filters
    if switch_id:
        query = query.filter(MacLocation.switch_id == switch_id)
    if vlan_id:
        query = query.filter(MacLocation.vlan_id == vlan_id)
    if is_active is not None:
        query = query.filter(MacAddress.is_active == is_active)

    # Get total count
    total = query.count()

    # Get paginated results
    results = query.offset(skip).limit(limit).all()

    # Format response
    items = []
    for row in results:
        mac = row[0]  # MacAddress object
        items.append(
            MacSearchResult(
                id=mac.id,
                mac_address=mac.mac_address,
                vendor_name=mac.vendor_name,
                device_type=mac.device_type,
                ip_address=row.loc_ip,
                hostname=row.loc_hostname,
                switch_hostname=row.switch_hostname,
                switch_ip=row.switch_ip,
                port_name=row.port_name,
                vlan_id=row.loc_vlan,
                first_seen=mac.first_seen,
                last_seen=mac.last_seen,
                is_active=mac.is_active,
                is_uplink=row.is_uplink or False,  # Include uplink status
            )
        )

    return MacSearchResponse(items=items, total=total)


@router.get("/export")
def export_macs_csv(
    q: str = Query("", description="Search query (MAC, IP, hostname, switch)"),
    switch_id: Optional[int] = None,
    vlan_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    include_uplinks: bool = Query(False, description="Include MACs on uplink ports (default: exclude)"),
    db: Session = Depends(get_db),
):
    """Export MAC search results to CSV file.

    By default, excludes MACs found on uplink ports since those are not endpoints.
    Set include_uplinks=true to include all MACs including those on uplink ports.
    """
    # Base query with current location info (same as search)
    query = (
        db.query(
            MacAddress,
            MacLocation.ip_address.label("loc_ip"),
            MacLocation.hostname.label("loc_hostname"),
            MacLocation.vlan_id.label("loc_vlan"),
            Switch.hostname.label("switch_hostname"),
            Switch.ip_address.label("switch_ip"),
            Port.port_name.label("port_name"),
            Port.is_uplink.label("is_uplink"),
        )
        .outerjoin(
            MacLocation,
            (MacAddress.id == MacLocation.mac_id) & (MacLocation.is_current == True),
        )
        .outerjoin(Switch, MacLocation.switch_id == Switch.id)
        .outerjoin(Port, MacLocation.port_id == Port.id)
    )

    # Filter out uplink ports by default (for endpoint search)
    if not include_uplinks:
        endpoint_oui_filters = [MacAddress.mac_address.ilike(f"{oui}%") for oui in ENDPOINT_OUIS]
        query = query.filter(
            or_(
                Port.is_uplink == False,
                Port.is_uplink.is_(None),
                *endpoint_oui_filters,
            )
        )

    # Apply search filter
    if q:
        search_term = f"%{q}%"
        query = query.filter(
            or_(
                MacAddress.mac_address.ilike(search_term),
                MacLocation.ip_address.ilike(search_term),
                MacLocation.hostname.ilike(search_term),
                Switch.hostname.ilike(search_term),
                MacAddress.vendor_name.ilike(search_term),
            )
        )

    # Apply additional filters
    if switch_id:
        query = query.filter(MacLocation.switch_id == switch_id)
    if vlan_id:
        query = query.filter(MacLocation.vlan_id == vlan_id)
    if is_active is not None:
        query = query.filter(MacAddress.is_active == is_active)

    # Get all results (no pagination for export)
    results = query.all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Write header row in Italian
    writer.writerow([
        'MAC Address',
        'Indirizzo IP',
        'Hostname',
        'Switch',
        'IP Switch',
        'Porta',
        'VLAN',
        'Vendor',
        'Tipo Dispositivo',
        'Primo Avvistamento',
        'Ultimo Avvistamento',
        'Attivo'
    ])

    # Write data rows
    for row in results:
        mac = row[0]  # MacAddress object
        writer.writerow([
            mac.mac_address,
            row.loc_ip or '',
            row.loc_hostname or '',
            row.switch_hostname or '',
            row.switch_ip or '',
            row.port_name or '',
            row.loc_vlan or '',
            mac.vendor_name or '',
            mac.device_type or '',
            mac.first_seen.strftime('%d/%m/%Y %H:%M') if mac.first_seen else '',
            mac.last_seen.strftime('%d/%m/%Y %H:%M') if mac.last_seen else '',
            'Si' if mac.is_active else 'No'
        ])

    # Prepare response
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"mac_export_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


# REMOVED: create-test-mac endpoint
# Test/demo endpoints were removed as part of Feature #126 to ensure
# the application only uses real data from SNMP/SSH discovery


class SnapshotCompareResult(BaseModel):
    """Response model for snapshot comparison."""
    date1: datetime
    date2: datetime
    added: List[dict]  # MACs present at date2 but not at date1
    removed: List[dict]  # MACs present at date1 but not at date2
    moved: List[dict]  # MACs that changed location between dates
    stats: dict  # Summary statistics


@router.get("/compare-snapshots")
def compare_mac_snapshots(
    date1: datetime = Query(..., description="First date (older)"),
    date2: datetime = Query(..., description="Second date (newer)"),
    db: Session = Depends(get_db),
):
    """
    Compare MAC address snapshots between two dates.

    Returns:
    - added: MACs that appeared after date1
    - removed: MACs that disappeared after date1
    - moved: MACs that changed switch/port between dates

    Uses MacHistory events to reconstruct the state at each date.
    """

    def get_snapshot_at_date(target_date: datetime) -> dict:
        """Reconstruct MAC locations as of a specific date."""
        # Get all MAC history up to target_date
        history = (
            db.query(MacHistory, Switch, Port, MacAddress)
            .join(MacAddress, MacHistory.mac_id == MacAddress.id)
            .outerjoin(Switch, MacHistory.switch_id == Switch.id)
            .outerjoin(Port, MacHistory.port_id == Port.id)
            .filter(MacHistory.event_at <= target_date)
            .order_by(MacHistory.event_at.asc())
            .all()
        )

        # Reconstruct state by replaying events
        mac_state = {}  # mac_address -> {switch, port, vlan, last_event}

        for h, switch, port, mac in history:
            mac_addr = mac.mac_address
            if h.event_type == 'new':
                mac_state[mac_addr] = {
                    'mac_address': mac_addr,
                    'switch_hostname': switch.hostname if switch else None,
                    'switch_ip': switch.ip_address if switch else None,
                    'port_name': port.port_name if port else None,
                    'vlan_id': h.vlan_id,
                    'vendor_name': mac.vendor_name,
                    'device_type': mac.device_type,
                    'event_at': h.event_at
                }
            elif h.event_type == 'move':
                if mac_addr in mac_state:
                    mac_state[mac_addr].update({
                        'switch_hostname': switch.hostname if switch else None,
                        'switch_ip': switch.ip_address if switch else None,
                        'port_name': port.port_name if port else None,
                        'vlan_id': h.vlan_id,
                        'event_at': h.event_at
                    })
                else:
                    mac_state[mac_addr] = {
                        'mac_address': mac_addr,
                        'switch_hostname': switch.hostname if switch else None,
                        'switch_ip': switch.ip_address if switch else None,
                        'port_name': port.port_name if port else None,
                        'vlan_id': h.vlan_id,
                        'vendor_name': mac.vendor_name,
                        'device_type': mac.device_type,
                        'event_at': h.event_at
                    }
            elif h.event_type == 'disappear':
                if mac_addr in mac_state:
                    del mac_state[mac_addr]

        return mac_state

    # Get snapshots at both dates
    snapshot1 = get_snapshot_at_date(date1)
    snapshot2 = get_snapshot_at_date(date2)

    macs1 = set(snapshot1.keys())
    macs2 = set(snapshot2.keys())

    # Calculate differences
    added_macs = macs2 - macs1
    removed_macs = macs1 - macs2
    common_macs = macs1 & macs2

    # Find moved MACs (changed switch or port)
    moved = []
    for mac in common_macs:
        s1 = snapshot1[mac]
        s2 = snapshot2[mac]
        if s1['switch_hostname'] != s2['switch_hostname'] or s1['port_name'] != s2['port_name']:
            moved.append({
                'mac_address': mac,
                'vendor_name': s2.get('vendor_name'),
                'device_type': s2.get('device_type'),
                'from_switch': s1['switch_hostname'],
                'from_port': s1['port_name'],
                'to_switch': s2['switch_hostname'],
                'to_port': s2['port_name'],
                'from_vlan': s1.get('vlan_id'),
                'to_vlan': s2.get('vlan_id')
            })

    return {
        'date1': date1,
        'date2': date2,
        'added': [snapshot2[mac] for mac in added_macs],
        'removed': [snapshot1[mac] for mac in removed_macs],
        'moved': moved,
        'stats': {
            'total_at_date1': len(macs1),
            'total_at_date2': len(macs2),
            'added_count': len(added_macs),
            'removed_count': len(removed_macs),
            'moved_count': len(moved),
            'unchanged_count': len(common_macs) - len(moved)
        }
    }


class VendorLookupResponse(BaseModel):
    mac_address: str
    oui: str
    vendor_name: Optional[str] = None
    device_type: Optional[str] = None
    source: str  # "database", "builtin", "api", or "not_found"


@router.get("/vendor-lookup/{mac_address}", response_model=VendorLookupResponse)
def lookup_vendor(mac_address: str, db: Session = Depends(get_db)):
    """
    Look up vendor information for a MAC address.

    This endpoint demonstrates the three-tier vendor lookup:
    1. Database (OuiVendor table)
    2. Built-in common OUI list
    3. External API fallback (macvendors.com)

    The result is cached in the database for future lookups.
    """
    from app.services.discovery.mac_processor import MacProcessor, COMMON_OUI
    from app.db.models import OuiVendor

    # Normalize MAC address
    mac_clean = mac_address.upper().replace("-", ":").replace(".", ":")
    if len(mac_clean.replace(":", "")) < 6:
        raise HTTPException(status_code=400, detail="Invalid MAC address format")

    oui = mac_clean.replace(":", "")[:6]

    # Check database first
    oui_entry = db.query(OuiVendor).filter(OuiVendor.oui_prefix == oui).first()
    if oui_entry:
        return VendorLookupResponse(
            mac_address=mac_clean,
            oui=oui,
            vendor_name=oui_entry.vendor_name,
            device_type=oui_entry.device_type_hint,
            source="database"
        )

    # Check built-in database
    if oui in COMMON_OUI:
        vendor_name, device_type = COMMON_OUI[oui]
        return VendorLookupResponse(
            mac_address=mac_clean,
            oui=oui,
            vendor_name=vendor_name,
            device_type=device_type,
            source="builtin"
        )

    # Try API fallback
    processor = MacProcessor(db)
    vendor_name, device_type = processor.get_vendor_info(mac_clean)

    if vendor_name:
        return VendorLookupResponse(
            mac_address=mac_clean,
            oui=oui,
            vendor_name=vendor_name,
            device_type=device_type,
            source="api"
        )

    return VendorLookupResponse(
        mac_address=mac_clean,
        oui=oui,
        vendor_name=None,
        device_type=None,
        source="not_found"
    )


@router.get("/{mac_id}/history")
def get_mac_history(mac_id: int, db: Session = Depends(get_db)):
    """Get movement history for a MAC address sorted chronologically (oldest first)."""
    mac = db.query(MacAddress).filter(MacAddress.id == mac_id).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC address not found")

    # Get history ordered chronologically (ascending - oldest first for timeline view)
    history_records = (
        db.query(MacHistory, Switch, Port)
        .outerjoin(Switch, MacHistory.switch_id == Switch.id)
        .outerjoin(Port, MacHistory.port_id == Port.id)
        .filter(MacHistory.mac_id == mac_id)
        .order_by(MacHistory.event_at.asc())  # Chronological order (oldest first)
        .limit(100)
        .all()
    )

    history = []
    for h, switch, port in history_records:
        history.append({
            "id": h.id,
            "event_type": h.event_type,
            "event_at": h.event_at,
            "switch_id": h.switch_id,
            "switch_hostname": switch.hostname if switch else None,
            "switch_ip": switch.ip_address if switch else None,
            "port_id": h.port_id,
            "port_name": port.port_name if port else None,
            "vlan_id": h.vlan_id,
            "ip_address": h.ip_address,
            "previous_switch_id": h.previous_switch_id,
            "previous_port_id": h.previous_port_id,
        })

    return {
        "mac_id": mac_id,
        "mac_address": mac.mac_address,
        "history": history,
        "total": len(history)
    }


@router.get("/{mac_id}/history/export")
def export_mac_history_csv(mac_id: int, db: Session = Depends(get_db)):
    """Export MAC address history to CSV file."""
    mac = db.query(MacAddress).filter(MacAddress.id == mac_id).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC address not found")

    # Get history ordered chronologically with switch and port info
    history_records = (
        db.query(MacHistory, Switch, Port)
        .outerjoin(Switch, MacHistory.switch_id == Switch.id)
        .outerjoin(Port, MacHistory.port_id == Port.id)
        .filter(MacHistory.mac_id == mac_id)
        .order_by(MacHistory.event_at.asc())
        .all()
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Write header row in Italian
    writer.writerow([
        'Data Evento',
        'Tipo Evento',
        'Switch',
        'IP Switch',
        'Porta',
        'VLAN',
        'Indirizzo IP',
        'Switch Precedente',
        'Porta Precedente'
    ])

    # Event type labels in Italian
    event_labels = {
        'new': 'Nuovo MAC',
        'move': 'Spostamento',
        'disappear': 'Scomparsa'
    }

    # Write data rows
    for h, switch, port in history_records:
        # Get previous switch/port info if available
        prev_switch_name = ''
        prev_port_name = ''
        if h.previous_switch_id:
            prev_switch = db.query(Switch).filter(Switch.id == h.previous_switch_id).first()
            prev_switch_name = prev_switch.hostname if prev_switch else f'ID: {h.previous_switch_id}'
        if h.previous_port_id:
            prev_port = db.query(Port).filter(Port.id == h.previous_port_id).first()
            prev_port_name = prev_port.port_name if prev_port else f'ID: {h.previous_port_id}'

        writer.writerow([
            h.event_at.strftime('%d/%m/%Y %H:%M:%S') if h.event_at else '',
            event_labels.get(h.event_type, h.event_type),
            switch.hostname if switch else '',
            switch.ip_address if switch else '',
            port.port_name if port else '',
            h.vlan_id or '',
            h.ip_address or '',
            prev_switch_name,
            prev_port_name
        ])

    # Prepare response
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Sanitize MAC address for filename (replace colons with underscores)
    safe_mac = mac.mac_address.replace(':', '_')
    filename = f"mac_history_{safe_mac}_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


@router.get("/{mac_id}", response_model=MacDetailResponse)
def get_mac_detail(mac_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a MAC address."""
    mac = db.query(MacAddress).filter(MacAddress.id == mac_id).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC address not found")

    # Get current location
    current_loc = (
        db.query(MacLocation, Switch, Port)
        .outerjoin(Switch, MacLocation.switch_id == Switch.id)
        .outerjoin(Port, MacLocation.port_id == Port.id)
        .filter(MacLocation.mac_id == mac_id, MacLocation.is_current == True)
        .first()
    )

    current_location = None
    if current_loc:
        loc, switch, port = current_loc
        current_location = MacLocationResponse(
            switch_hostname=switch.hostname if switch else "Unknown",
            switch_ip=switch.ip_address if switch else "",
            port_name=port.port_name if port else "Unknown",
            vlan_id=loc.vlan_id,
            ip_address=loc.ip_address,
            hostname=loc.hostname,
            seen_at=loc.seen_at,
            is_current=loc.is_current,
        )

    # Get history
    history_records = (
        db.query(MacHistory)
        .filter(MacHistory.mac_id == mac_id)
        .order_by(MacHistory.event_at.desc())
        .limit(100)
        .all()
    )

    history = [
        MacHistoryItem(
            event_type=h.event_type,
            event_at=h.event_at,
            switch_id=h.switch_id,
            port_id=h.port_id,
            vlan_id=h.vlan_id,
            ip_address=h.ip_address,
            previous_switch_id=h.previous_switch_id,
            previous_port_id=h.previous_port_id,
        )
        for h in history_records
    ]

    return MacDetailResponse(
        id=mac.id,
        mac_address=mac.mac_address,
        vendor_oui=mac.vendor_oui,
        vendor_name=mac.vendor_name,
        device_type=mac.device_type,
        first_seen=mac.first_seen,
        last_seen=mac.last_seen,
        is_active=mac.is_active,
        current_location=current_location,
        history=history,
    )


# REMOVED: seed-demo-data endpoint
# Demo/seed endpoints were removed as part of Feature #126 to ensure
# the application only uses real data from SNMP/SSH discovery


# REMOVED: seed-history-data endpoint
# Demo/seed endpoints were removed as part of Feature #126 to ensure
# the application only uses real data from SNMP/SSH discovery


class EndpointTraceResponse(BaseModel):
    """Response model for MAC endpoint trace."""
    mac_address: str
    endpoint_switch_hostname: str
    endpoint_switch_ip: str
    endpoint_port_name: str
    vlan_id: Optional[int] = None
    lldp_device_name: Optional[str] = None
    is_endpoint: bool
    trace_path: List[str] = []
    vendor_name: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/trace/{mac_address}", response_model=EndpointTraceResponse)
async def trace_mac_endpoint(
    mac_address: str,
    method: str = Query(default="ssh", description="Trace method: 'ssh' for real-time SSH, 'db' for database-only"),
    site: Optional[str] = Query(default=None, description="Site code (e.g., '07', '09') - required if MAC has no location in DB"),
    db: Session = Depends(get_db)
):
    """
    Trace a MAC address to find its physical endpoint.

    This endpoint follows the network topology to find the actual switch
    and port where the device is directly connected.

    CORRECT Algorithm (method=ssh, default):
    1. Start from Core switch (xxx_L3_xxx_251)
    2. SSH: `dis mac-ad <mac>` to find port/Eth-Trunk
    3. If Eth-Trunk: `dis eth-trunk X` to get physical members
    4. SSH: `dis lldp neighbor interface <port>` to find downstream switch
    5. Repeat until access port found (no LLDP neighbor)

    Parameters:
    - method: 'ssh' (real-time SSH trace) or 'db' (database-only, faster but may be stale)
    - site: Site code for trace (e.g., '07', '09') - use when MAC has no location in DB
    """
    # Normalize MAC address format
    mac_clean = mac_address.upper().replace("-", ":").replace(".", ":")

    # Also handle Huawei format (xxxx-xxxx-xxxx)
    if "-" in mac_address and len(mac_address) == 14:
        # Huawei format: 0040-c137-8cc5
        mac_no_dash = mac_address.replace("-", "").upper()
        mac_clean = ":".join([mac_no_dash[i:i+2] for i in range(0, 12, 2)])

    # Create tracer
    tracer = MacEndpointTracer(db)
    endpoint = None

    if method == "ssh":
        # Use SSH-based follow-the-trail (CORRECT algorithm)
        try:
            endpoint = await tracer.trace_via_ssh(mac_clean, site_code=site)
        except Exception as e:
            logger.warning(f"SSH trace failed for {mac_clean}: {e}, falling back to DB")

        # Fallback to DB methods if SSH trace returned None or raised exception
        if not endpoint:
            endpoint = tracer.trace_from_core(mac_clean)
            if not endpoint:
                endpoint = tracer.trace_endpoint(mac_clean)
    else:
        # Use database-only tracing (faster but may be stale)
        endpoint = tracer.trace_from_core(mac_clean)
        if not endpoint:
            endpoint = tracer.trace_endpoint(mac_clean)

    if not endpoint:
        raise HTTPException(
            status_code=404,
            detail=f"MAC address {mac_clean} not found or endpoint could not be traced. Try specifying site parameter (e.g., ?site=09)"
        )

    # Get vendor info
    mac_obj = db.query(MacAddress).filter(MacAddress.mac_address == mac_clean).first()
    vendor_name = mac_obj.vendor_name if mac_obj else None

    return EndpointTraceResponse(
        mac_address=mac_clean,
        endpoint_switch_hostname=endpoint.switch_hostname,
        endpoint_switch_ip=endpoint.switch_ip,
        endpoint_port_name=endpoint.port_name,
        vlan_id=endpoint.vlan_id,
        lldp_device_name=endpoint.lldp_device_name,
        is_endpoint=endpoint.is_endpoint,
        trace_path=endpoint.trace_path,
        vendor_name=vendor_name
    )


@router.get("/endpoints/{mac_address}")
def get_mac_endpoints(mac_address: str, db: Session = Depends(get_db)):
    """
    Get all endpoint locations for a MAC address.

    Returns only the actual endpoints (ports without LLDP neighbors),
    filtering out uplink ports where the MAC appears due to traffic flow.

    Useful for devices that appear on multiple VLANs or have multiple interfaces.
    """
    # Normalize MAC address format
    mac_clean = mac_address.upper().replace("-", ":").replace(".", ":")

    # Handle Huawei/Extreme format (xxxx-xxxx-xxxx)
    if "-" in mac_address and len(mac_address) == 14:
        mac_no_dash = mac_address.replace("-", "").upper()
        mac_clean = ":".join([mac_no_dash[i:i+2] for i in range(0, 12, 2)])

    # Create tracer and find all endpoints
    tracer = MacEndpointTracer(db)
    endpoints = tracer.get_all_endpoints_for_mac(mac_clean)

    if not endpoints:
        raise HTTPException(
            status_code=404,
            detail=f"No endpoints found for MAC address {mac_clean}"
        )

    # Get vendor info
    mac_obj = db.query(MacAddress).filter(MacAddress.mac_address == mac_clean).first()
    vendor_name = mac_obj.vendor_name if mac_obj else None

    return {
        "mac_address": mac_clean,
        "vendor_name": vendor_name,
        "endpoints": [
            {
                "switch_hostname": ep.switch_hostname,
                "switch_ip": ep.switch_ip,
                "port_name": ep.port_name,
                "vlan_id": ep.vlan_id,
                "lldp_device_name": ep.lldp_device_name,
                "is_endpoint": ep.is_endpoint,
                "trace_path": ep.trace_path
            }
            for ep in endpoints
        ],
        "total": len(endpoints)
    }


class VendorUpdateResponse(BaseModel):
    """Response model for vendor update operation."""
    total: int
    updated: int
    not_found: int
    message: str


@router.post("/update-vendors", response_model=VendorUpdateResponse)
def update_all_vendors(db: Session = Depends(get_db)):
    """
    Update vendor information for all MAC addresses that don't have vendor data.

    Uses three-tier lookup:
    1. Local database (OuiVendor table)
    2. Built-in OUI database (expanded with WiFi, handheld, IP Phone vendors)
    3. External API fallback (macvendors.com)

    This is useful after importing new MACs or if the built-in OUI database
    has been expanded with new vendors.
    """
    from app.services.discovery.mac_processor import MacProcessor

    processor = MacProcessor(db)
    stats = processor.update_all_vendor_info()

    return VendorUpdateResponse(
        total=stats["total"],
        updated=stats["updated"],
        not_found=stats["not_found"],
        message=f"Aggiornati {stats['updated']} MAC su {stats['total']} senza vendor info"
    )
