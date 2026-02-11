"""Seed Discovery API endpoint - Feature #119."""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Switch

router = APIRouter()


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

    if result.switches_added > 0:
        result.message = f"Seed discovery completato: {result.switches_added} nuovi switch aggiunti, {result.switches_already_exist} gia' presenti"
    else:
        result.message = f"Seed discovery completato: nessun nuovo switch trovato ({result.switches_already_exist} gia' presenti)"

    if result.errors:
        result.status = "completed_with_errors"

    return result
