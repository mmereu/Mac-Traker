"""Discovery API endpoints."""
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Switch, DiscoveryLog, MacAddress, MacLocation, MacHistory, Port
from app.services.discovery import SNMPDiscoveryService, SSHDiscoveryService, MacProcessor

router = APIRouter()


class DiscoveryStatus(BaseModel):
    status: str  # idle, running, completed, error
    message: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    switches_processed: int = 0
    switches_total: int = 0
    macs_found: int = 0
    current_switch: Optional[str] = None


class DiscoveryStartResponse(BaseModel):
    message: str
    status: str


class DiscoveryLogResponse(BaseModel):
    id: int
    switch_hostname: Optional[str]
    discovery_type: str
    status: str
    mac_count: int
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]


class SwitchDiscoveryResult(BaseModel):
    switch_id: int
    hostname: str
    status: str
    mac_count: int
    error_message: Optional[str]


class DiscoverySummary(BaseModel):
    total_switches: int
    successful: int
    failed: int
    total_macs: int
    switch_results: List[SwitchDiscoveryResult]


# In-memory status tracking
_discovery_status = DiscoveryStatus(
    status="idle",
    message="Discovery non avviato"
)


def run_discovery_sync(db: Session):
    """Synchronous wrapper for async discovery task.

    Note: Creates a fresh database session to avoid SQLite locking issues
    when running in a background thread.
    """
    from app.db.database import SessionLocal
    # Create a fresh session for the background task
    fresh_db = SessionLocal()
    try:
        asyncio.run(run_discovery_task(fresh_db))
    finally:
        fresh_db.close()


async def run_discovery_task(db: Session):
    """Background task to run SNMP discovery with SSH fallback."""
    global _discovery_status

    try:
        _discovery_status.status = "running"
        _discovery_status.message = "Avvio discovery..."
        _discovery_status.started_at = datetime.utcnow()
        _discovery_status.switches_processed = 0
        _discovery_status.macs_found = 0

        # Get all active switches
        switches = db.query(Switch).filter(Switch.is_active == True).all()
        _discovery_status.switches_total = len(switches)

        if not switches:
            _discovery_status.status = "completed"
            _discovery_status.message = "Nessuno switch attivo da scansionare"
            _discovery_status.completed_at = datetime.utcnow()
            return

        # Initialize services
        snmp_service = SNMPDiscoveryService(db)
        ssh_service = SSHDiscoveryService(db)
        mac_processor = MacProcessor(db)

        total_macs = 0

        for i, switch in enumerate(switches):
            _discovery_status.current_switch = switch.hostname
            _discovery_status.message = f"Scanning {switch.hostname} ({i+1}/{len(switches)})..."

            # Run SNMP discovery first (unless SSH fallback is explicitly enabled)
            result = await snmp_service.discover_switch(switch)

            # If SNMP failed and SSH fallback is enabled, try SSH
            if result["status"] != "success" and switch.use_ssh_fallback:
                _discovery_status.message = f"SNMP fallito per {switch.hostname}, provo SSH..."
                result = await ssh_service.discover_switch(switch)

            if result["status"] == "success":
                total_macs += result["mac_count"]
                _discovery_status.switches_processed += 1

            _discovery_status.macs_found = total_macs

        # Enrich MACs with vendor info
        _discovery_status.message = "Aggiornamento informazioni vendor..."
        mac_processor.update_all_vendor_info()

        # Finalize
        _discovery_status.status = "completed"
        _discovery_status.completed_at = datetime.utcnow()
        _discovery_status.current_switch = None
        _discovery_status.message = f"Discovery completato: {_discovery_status.switches_processed}/{len(switches)} switch, {total_macs} MAC trovati"

        # Auto-rebuild network graph after discovery completes
        try:
            from app.services.network_graph import get_network_graph
            graph = get_network_graph()
            graph_result = graph.build(db)
            _discovery_status.message += f" | Grafo: {graph_result['node_count']} nodi, {graph_result['edge_count']} archi"
        except Exception as graph_error:
            _discovery_status.message += f" | Grafo non aggiornato: {str(graph_error)}"

    except Exception as e:
        _discovery_status.status = "error"
        _discovery_status.message = f"Errore: {str(e)}"
        _discovery_status.current_switch = None


@router.post("/start", response_model=DiscoveryStartResponse)
def start_discovery(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start manual discovery process."""
    global _discovery_status

    if _discovery_status.status == "running":
        return DiscoveryStartResponse(
            message="Discovery gia' in esecuzione",
            status="running"
        )

    # Check if there are switches to discover
    switch_count = db.query(Switch).filter(Switch.is_active == True).count()
    if switch_count == 0:
        return DiscoveryStartResponse(
            message="Nessuno switch configurato. Aggiungi almeno uno switch prima di avviare il discovery.",
            status="idle"
        )

    # Reset status
    _discovery_status = DiscoveryStatus(
        status="running",
        message="Avvio discovery...",
        started_at=datetime.utcnow()
    )

    # Run discovery in background
    background_tasks.add_task(run_discovery_sync, db)

    return DiscoveryStartResponse(
        message=f"Discovery avviato per {switch_count} switch",
        status="running"
    )


@router.get("/status", response_model=DiscoveryStatus)
def get_discovery_status():
    """Get current discovery status."""
    return _discovery_status


@router.get("/logs", response_model=List[DiscoveryLogResponse])
def get_discovery_logs(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get recent discovery logs."""
    logs = db.query(DiscoveryLog).order_by(
        DiscoveryLog.started_at.desc()
    ).limit(limit).all()

    result = []
    for log in logs:
        switch_hostname = None
        if log.switch:
            switch_hostname = log.switch.hostname

        result.append(DiscoveryLogResponse(
            id=log.id,
            switch_hostname=switch_hostname,
            discovery_type=log.discovery_type,
            status=log.status,
            mac_count=log.mac_count,
            error_message=log.error_message,
            started_at=log.started_at,
            completed_at=log.completed_at,
            duration_ms=log.duration_ms,
        ))

    return result


@router.post("/switch/{switch_id}", response_model=SwitchDiscoveryResult)
async def discover_single_switch(
    switch_id: int,
    use_ssh: bool = False,
    db: Session = Depends(get_db)
):
    """Run discovery on a single switch. Use use_ssh=true to force SSH discovery."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    # Use SSH if explicitly requested or if switch has SSH fallback enabled
    if use_ssh or switch.use_ssh_fallback:
        ssh_service = SSHDiscoveryService(db)
        result = await ssh_service.discover_switch(switch)
    else:
        snmp_service = SNMPDiscoveryService(db)
        result = await snmp_service.discover_switch(switch)

        # If SNMP failed and SSH fallback is enabled, try SSH
        if result["status"] != "success" and switch.use_ssh_fallback:
            ssh_service = SSHDiscoveryService(db)
            result = await ssh_service.discover_switch(switch)

    # Auto-rebuild network graph after single switch discovery
    try:
        from app.services.network_graph import get_network_graph
        graph = get_network_graph()
        graph.build(db)
    except Exception:
        pass  # Non-critical, grafo si ricostruirà al prossimo full discovery

    return SwitchDiscoveryResult(
        switch_id=result["switch_id"],
        hostname=result["hostname"],
        status=result["status"],
        mac_count=result["mac_count"],
        error_message=result.get("error_message"),
    )


@router.post("/update-mac-hostname")
def update_mac_hostname(
    mac_id: int,
    hostname: str,
    db: Session = Depends(get_db)
):
    """Update a MAC address's hostname for testing. Development only."""
    mac = db.query(MacAddress).filter(MacAddress.id == mac_id).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC non trovato")

    location = db.query(MacLocation).filter(
        MacLocation.mac_id == mac_id,
        MacLocation.is_current == True
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location non trovata per questo MAC")

    old_hostname = location.hostname
    location.hostname = hostname
    db.commit()

    return {
        "message": f"Hostname aggiornato da '{old_hostname}' a '{hostname}'",
        "mac_id": mac_id,
        "mac_address": mac.mac_address,
        "hostname": hostname
    }


# === Scheduler Endpoints ===

class SchedulerStatusResponse(BaseModel):
    is_running: bool
    enabled: bool
    interval_minutes: int
    next_scheduled_discovery: Optional[str]
    last_discovery_result: Optional[dict]


class SchedulerConfigRequest(BaseModel):
    enabled: bool
    interval_minutes: int  # 5-60 minutes


@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
def get_scheduler_status():
    """Get current discovery scheduler status."""
    from app.services.discovery.discovery_scheduler import get_discovery_scheduler

    scheduler = get_discovery_scheduler()
    status = scheduler.get_status()

    return SchedulerStatusResponse(
        is_running=status["is_running"],
        enabled=status["config"]["enabled"],
        interval_minutes=status["config"]["interval_minutes"],
        next_scheduled_discovery=status["next_scheduled_discovery"],
        last_discovery_result=status["last_discovery_result"]
    )


@router.post("/scheduler/configure", response_model=SchedulerStatusResponse)
def configure_scheduler(config: SchedulerConfigRequest):
    """Configure the discovery scheduler interval and enabled status."""
    from app.services.discovery.discovery_scheduler import get_discovery_scheduler

    scheduler = get_discovery_scheduler()
    scheduler.configure(
        enabled=config.enabled,
        interval_minutes=config.interval_minutes
    )

    status = scheduler.get_status()

    return SchedulerStatusResponse(
        is_running=status["is_running"],
        enabled=status["config"]["enabled"],
        interval_minutes=status["config"]["interval_minutes"],
        next_scheduled_discovery=status["next_scheduled_discovery"],
        last_discovery_result=status["last_discovery_result"]
    )


@router.post("/simulate-mac-move")
def simulate_mac_move(
    mac_id: int,
    new_switch_id: int,
    new_port_id: int,
    db: Session = Depends(get_db)
):
    """
    Simulate a MAC address movement for testing alert generation.
    This endpoint moves an existing MAC to a different switch/port and generates the movement alert.
    """
    from app.services.alerts.alert_service import AlertService

    # Get the MAC address
    mac = db.query(MacAddress).filter(MacAddress.id == mac_id).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC non trovato")

    # Get the new switch and port
    new_switch = db.query(Switch).filter(Switch.id == new_switch_id).first()
    if not new_switch:
        raise HTTPException(status_code=404, detail="Nuovo switch non trovato")

    new_port = db.query(Port).filter(Port.id == new_port_id).first()
    if not new_port:
        raise HTTPException(status_code=404, detail="Nuova porta non trovata")

    # Get current location
    current_location = db.query(MacLocation).filter(
        MacLocation.mac_id == mac_id,
        MacLocation.is_current == True
    ).first()

    if not current_location:
        raise HTTPException(status_code=404, detail="Location corrente non trovata per questo MAC")

    # Check if it's actually a move (different switch or port)
    if current_location.switch_id == new_switch_id and current_location.port_id == new_port_id:
        return {
            "message": "MAC gia' presente su questa switch/porta",
            "moved": False
        }

    # Get old switch and port for alert
    old_switch = db.query(Switch).filter(Switch.id == current_location.switch_id).first()
    old_port = db.query(Port).filter(Port.id == current_location.port_id).first()

    # Create history entry for the move
    history_entry = MacHistory(
        mac_id=mac.id,
        switch_id=new_switch.id,
        port_id=new_port.id,
        vlan_id=current_location.vlan_id,
        event_type="move",
        event_at=datetime.utcnow(),
        previous_switch_id=current_location.switch_id,
        previous_port_id=current_location.port_id,
    )
    db.add(history_entry)

    # Generate the movement alert
    alert_service = AlertService(db)
    if old_switch and old_port:
        alert = alert_service.create_mac_move_alert(
            mac=mac,
            new_switch=new_switch,
            new_port=new_port,
            old_switch=old_switch,
            old_port=old_port,
            vlan_id=current_location.vlan_id
        )

    # Mark old location as not current
    current_location.is_current = False

    # Create new location
    new_location = MacLocation(
        mac_id=mac.id,
        switch_id=new_switch.id,
        port_id=new_port.id,
        vlan_id=current_location.vlan_id,
        ip_address=current_location.ip_address,
        hostname=current_location.hostname,
        seen_at=datetime.utcnow(),
        is_current=True,
    )
    db.add(new_location)

    db.commit()

    return {
        "message": f"MAC {mac.mac_address} spostato da {old_switch.hostname}:{old_port.port_name} a {new_switch.hostname}:{new_port.port_name}",
        "moved": True,
        "mac_id": mac.id,
        "mac_address": mac.mac_address,
        "old_location": {
            "switch": old_switch.hostname,
            "port": old_port.port_name
        },
        "new_location": {
            "switch": new_switch.hostname,
            "port": new_port.port_name
        },
        "alert_generated": True
    }


# === Seed Discovery Endpoint ===

class SeedDiscoveryRequest(BaseModel):
    """Request to start seed discovery from a single device."""
    seed_ip: Optional[str] = None  # IP address of seed device
    seed_switch_id: Optional[int] = None  # Or existing switch ID
    snmp_community: str = "public"  # SNMP community string for new devices
    device_type: str = "huawei"  # Default device type for new devices
    max_depth: int = 3  # Maximum recursion depth
    group_id: Optional[int] = None  # Optional group to assign new switches


class SeedDiscoveryResult(BaseModel):
    """Result of seed discovery operation."""
    status: str
    message: str
    seed_switch: Optional[str]
    switches_discovered: int
    switches_added: int
    switches_already_exist: int
    discovered_switches: List[dict]
    errors: List[str]


@router.post("/seed", response_model=SeedDiscoveryResult)
async def seed_discovery(
    request: SeedDiscoveryRequest,
    db: Session = Depends(get_db)
):
    """
    Discover network devices starting from a single seed device via LLDP.

    This endpoint recursively discovers switches by querying LLDP neighbors
    starting from a seed device. New switches are automatically added to the database.

    Args:
        request: Contains seed device info (IP or switch ID) and discovery parameters

    Returns:
        Summary of discovered devices
    """
    from app.services.discovery.lldp_discovery import LLDPDiscoveryService

    result = SeedDiscoveryResult(
        status="success",
        message="",
        seed_switch=None,
        switches_discovered=0,
        switches_added=0,
        switches_already_exist=0,
        discovered_switches=[],
        errors=[]
    )

    # Validate input - need either seed_ip or seed_switch_id
    if not request.seed_ip and not request.seed_switch_id:
        raise HTTPException(
            status_code=400,
            detail="Deve specificare seed_ip o seed_switch_id"
        )

    # Get or create the seed switch
    seed_switch = None

    if request.seed_switch_id:
        # Use existing switch
        seed_switch = db.query(Switch).filter(Switch.id == request.seed_switch_id).first()
        if not seed_switch:
            raise HTTPException(status_code=404, detail="Switch seed non trovato")
    elif request.seed_ip:
        # Check if switch already exists
        seed_switch = db.query(Switch).filter(Switch.ip_address == request.seed_ip).first()

        if not seed_switch:
            # Create new seed switch
            seed_switch = Switch(
                hostname=f"SEED-{request.seed_ip.replace('.', '-')}",
                ip_address=request.seed_ip,
                device_type=request.device_type,
                snmp_community=request.snmp_community,
                group_id=request.group_id,
                is_active=True
            )
            db.add(seed_switch)
            db.flush()
            result.switches_added += 1

    result.seed_switch = seed_switch.hostname

    # Initialize LLDP discovery service
    lldp_service = LLDPDiscoveryService(db)

    # Track discovered and processed switches to avoid loops
    discovered_ips = set()
    discovered_ips.add(seed_switch.ip_address)
    to_process = [seed_switch]
    current_depth = 0

    # Process switches level by level (BFS)
    while to_process and current_depth < request.max_depth:
        next_level = []

        for switch in to_process:
            try:
                # Discover LLDP neighbors for this switch
                neighbors = await lldp_service.discover_neighbors(switch)

                for neighbor in neighbors:
                    result.switches_discovered += 1
                    neighbor_info = {
                        "hostname": neighbor.remote_system_name,
                        "ip": neighbor.remote_mgmt_address,
                        "local_port": neighbor.local_port_name,
                        "remote_port": neighbor.remote_port_id,
                        "added": False
                    }

                    # Try to identify the neighbor
                    neighbor_switch = None
                    neighbor_ip = neighbor.remote_mgmt_address

                    if neighbor_ip and neighbor_ip not in discovered_ips:
                        discovered_ips.add(neighbor_ip)

                        # Check if switch already exists by IP
                        neighbor_switch = db.query(Switch).filter(
                            Switch.ip_address == neighbor_ip
                        ).first()

                        if not neighbor_switch and neighbor.remote_system_name:
                            # Check by hostname
                            neighbor_switch = db.query(Switch).filter(
                                Switch.hostname == neighbor.remote_system_name
                            ).first()

                        if neighbor_switch:
                            result.switches_already_exist += 1
                            neighbor_info["added"] = False
                            neighbor_info["exists"] = True
                            next_level.append(neighbor_switch)
                        else:
                            # Create new switch from discovered neighbor
                            new_hostname = neighbor.remote_system_name or f"DISCOVERED-{neighbor_ip.replace('.', '-')}"

                            new_switch = Switch(
                                hostname=new_hostname,
                                ip_address=neighbor_ip,
                                device_type=request.device_type,
                                snmp_community=request.snmp_community,
                                group_id=request.group_id,
                                is_active=True
                            )
                            db.add(new_switch)
                            db.flush()

                            result.switches_added += 1
                            neighbor_info["added"] = True
                            neighbor_info["new_switch_id"] = new_switch.id
                            next_level.append(new_switch)

                    result.discovered_switches.append(neighbor_info)

            except Exception as e:
                error_msg = f"Errore durante discovery di {switch.hostname}: {str(e)}"
                result.errors.append(error_msg)

        to_process = next_level
        current_depth += 1

    db.commit()

    # Auto-rebuild network graph after seed discovery
    try:
        from app.services.network_graph import get_network_graph
        graph = get_network_graph()
        graph.build(db)
    except Exception:
        pass  # Non-critical

    if result.switches_added > 0:
        result.message = f"Seed discovery completato: {result.switches_added} nuovi switch aggiunti, {result.switches_already_exist} gia' presenti"
    else:
        result.message = f"Seed discovery completato: nessun nuovo switch trovato ({result.switches_already_exist} gia' presenti)"

    if result.errors:
        result.status = "completed_with_errors"

    return result


# Scheduler endpoints added - with seed discovery
# Reload trigger 2026-01-24 15:38
