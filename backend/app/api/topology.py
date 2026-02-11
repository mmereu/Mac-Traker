"""Topology API endpoints."""
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Switch, TopologyLink, Port, MacLocation
from app.services.mac_endpoint_tracer import MacEndpointTracer

router = APIRouter()


def _normalize_port_name(name: str) -> str:
    """Normalize Huawei port name variants to canonical form.
    GE0/0/1 == Gi0/0/1 (GigabitEthernet), XGE0/0/1 == XGi0/0/1 (10GE)."""
    if not name:
        return name
    return re.sub(r'^(X?)(?:GE|Gi)', r'\1GE', name)


class TopologyNode(BaseModel):
    id: int
    label: str
    hostname: str
    ip_address: str
    device_type: str
    is_active: bool
    mac_count: int
    site_code: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None


class TopologyEdge(BaseModel):
    from_node: int = Field(alias="from", serialization_alias="from")
    to: int
    local_port: str
    remote_port: Optional[str] = None
    protocol: str

    model_config = {"populate_by_name": True}


class TopologyResponse(BaseModel):
    nodes: List[TopologyNode]
    edges: List[TopologyEdge]
    last_updated: Optional[datetime] = None


class TopologyLinkResponse(BaseModel):
    id: int
    local_switch_id: int
    local_switch_hostname: str
    local_port_name: str
    remote_switch_id: int
    remote_switch_hostname: str
    remote_port_name: Optional[str]
    protocol: str
    last_seen: datetime


class SwitchMacsResponse(BaseModel):
    switch_id: int
    switch_hostname: str
    mac_count: int
    macs: List[dict]


class MacPathNode(BaseModel):
    """Node in MAC path."""
    switch_id: int
    hostname: str
    ip_address: str
    port_name: Optional[str] = None
    is_endpoint: bool = False


class MacPathResponse(BaseModel):
    """Response for MAC path."""
    mac_address: str
    ip_address: Optional[str] = None
    vendor_name: Optional[str] = None
    endpoint_switch_id: int
    endpoint_switch_hostname: str
    endpoint_port: str
    path: List[MacPathNode]
    path_node_ids: List[int]
    path_edge_keys: List[str]


@router.get("", response_model=TopologyResponse)
def get_topology(db: Session = Depends(get_db)):
    """Get network topology data for visualization."""
    # Get all active switches
    switches = db.query(Switch).filter(Switch.is_active == True).all()

    # Build nodes
    nodes = []
    for i, switch in enumerate(switches):
        # Count MACs on this switch
        mac_count = db.query(MacLocation).filter(
            MacLocation.switch_id == switch.id,
            MacLocation.is_current == True
        ).count()

        # Position nodes in a grid/circle pattern
        import math
        angle = (2 * math.pi * i) / max(len(switches), 1)
        radius = 200

        # Get site_code safely
        try:
            site_code = switch.site_code
        except Exception:
            site_code = None

        nodes.append(TopologyNode(
            id=switch.id,
            label=switch.hostname,
            hostname=switch.hostname,
            ip_address=switch.ip_address,
            device_type=switch.device_type,
            is_active=switch.is_active,
            mac_count=mac_count,
            site_code=site_code,
            x=radius * math.cos(angle),
            y=radius * math.sin(angle),
        ))

    # Get topology links
    links = db.query(TopologyLink).all()

    # Deduplicate edges - keep only one link per switch pair + port combination
    # Two-pass: first collect links with real ports, then add Unknown only if no real link exists
    edge_pairs: dict = {}
    unknown_pairs: list = []
    for link in links:
        local_port = db.query(Port).filter(Port.id == link.local_port_id).first()
        remote_port = db.query(Port).filter(Port.id == link.remote_port_id).first() if link.remote_port_id else None

        local_port_name = local_port.port_name if local_port else "Unknown"
        remote_port_name = remote_port.port_name if remote_port else None

        min_id = min(link.local_switch_id, link.remote_switch_id)
        max_id = max(link.local_switch_id, link.remote_switch_id)

        # Skip links with unknown ports for now, process them after real links
        if local_port_name == "Unknown" and not remote_port_name:
            unknown_pairs.append((min_id, max_id, link))
            continue

        # Normalize port names to handle GE/Gi and XGE/XGi duplicates
        norm_local = _normalize_port_name(local_port_name)
        norm_remote = _normalize_port_name(remote_port_name or "")

        if link.local_switch_id == min_id:
            port_key = (norm_local, norm_remote)
        else:
            port_key = (norm_remote, norm_local)

        key = (min_id, max_id, port_key[0], port_key[1])

        if key not in edge_pairs:
            edge_pairs[key] = {
                'from': link.local_switch_id,
                'to': link.remote_switch_id,
                'local_port': local_port_name,
                'remote_port': remote_port_name,
                'protocol': link.protocol,
            }

    # Add unknown-port links only if no real link exists for that switch pair
    switch_pairs_with_real_links = {(k[0], k[1]) for k in edge_pairs}
    for min_id, max_id, link in unknown_pairs:
        if (min_id, max_id) not in switch_pairs_with_real_links:
            key = (min_id, max_id, "Unknown", "")
            if key not in edge_pairs:
                edge_pairs[key] = {
                    'from': link.local_switch_id,
                    'to': link.remote_switch_id,
                    'local_port': "Unknown",
                    'remote_port': None,
                    'protocol': link.protocol,
                }

    edges = []
    for edge_data in edge_pairs.values():
        edges.append(TopologyEdge(
            from_node=edge_data['from'],
            to=edge_data['to'],
            local_port=edge_data['local_port'],
            remote_port=edge_data['remote_port'],
            protocol=edge_data['protocol'],
        ))

    # REMOVED: Simulated LLDP connections (Feature #126 - use real data only)
    # Topology will only show real LLDP/CDP links discovered from network devices.
    # If no links exist, the topology map will show disconnected nodes until
    # real link discovery is run.

    last_updated = None
    if links:
        last_updated = max(link.last_seen for link in links)

    return TopologyResponse(
        nodes=nodes,
        edges=edges,
        last_updated=last_updated or datetime.utcnow(),
    )


@router.get("/links", response_model=List[TopologyLinkResponse])
def get_topology_links(db: Session = Depends(get_db)):
    """Get list of all topology links."""
    links = db.query(TopologyLink).all()

    result = []
    for link in links:
        local_switch = db.query(Switch).filter(Switch.id == link.local_switch_id).first()
        remote_switch = db.query(Switch).filter(Switch.id == link.remote_switch_id).first()
        local_port = db.query(Port).filter(Port.id == link.local_port_id).first()
        remote_port = db.query(Port).filter(Port.id == link.remote_port_id).first() if link.remote_port_id else None

        if local_switch and remote_switch:
            result.append(TopologyLinkResponse(
                id=link.id,
                local_switch_id=link.local_switch_id,
                local_switch_hostname=local_switch.hostname,
                local_port_name=local_port.port_name if local_port else "Unknown",
                remote_switch_id=link.remote_switch_id,
                remote_switch_hostname=remote_switch.hostname,
                remote_port_name=remote_port.port_name if remote_port else None,
                protocol=link.protocol,
                last_seen=link.last_seen,
            ))

    return result


@router.post("/refresh")
async def refresh_topology(db: Session = Depends(get_db)):
    """Trigger topology refresh via LLDP discovery."""
    from app.services.discovery.lldp_discovery import LLDPDiscoveryService

    lldp_service = LLDPDiscoveryService(db)
    result = await lldp_service.refresh_topology()

    return result


@router.get("/mac-path/{mac_address}", response_model=MacPathResponse)
def get_mac_path(mac_address: str, db: Session = Depends(get_db)):
    """
    Get the network path from core to endpoint for a MAC address.
    Returns the path of switches from core -> distribution -> access.

    Uses MacEndpointTracer (IP Fabric algorithm) to find the TRUE endpoint,
    not just the location with is_current=True.
    """
    from app.db.models import MacAddress

    # Normalize MAC address format (support both : and - separators)
    mac_normalized = mac_address.upper().replace('-', ':')

    # Find the MAC address
    mac = db.query(MacAddress).filter(MacAddress.mac_address == mac_normalized).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC address non trovato")

    # Use MacEndpointTracer to find the TRUE endpoint (IP Fabric algorithm)
    tracer = MacEndpointTracer(db)
    endpoint_info = tracer.trace_endpoint(mac_normalized)

    if not endpoint_info:
        # Fallback to is_current=True if tracer fails
        location = db.query(MacLocation).filter(
            MacLocation.mac_id == mac.id,
            MacLocation.is_current == True
        ).first()
        if not location:
            raise HTTPException(status_code=404, detail="MAC non ha una posizione corrente")
        endpoint_switch = db.query(Switch).filter(Switch.id == location.switch_id).first()
        endpoint_port = db.query(Port).filter(Port.id == location.port_id).first()
    else:
        # Use the traced endpoint (correct algorithm!)
        endpoint_switch = db.query(Switch).filter(Switch.id == endpoint_info.switch_id).first()
        endpoint_port = db.query(Port).filter(Port.id == endpoint_info.port_id).first()
        # Get location for IP address
        location = db.query(MacLocation).filter(
            MacLocation.mac_id == mac.id,
            MacLocation.switch_id == endpoint_info.switch_id,
            MacLocation.port_id == endpoint_info.port_id
        ).first()
        if not location:
            # Fallback to any current location for IP address
            location = db.query(MacLocation).filter(
                MacLocation.mac_id == mac.id,
                MacLocation.is_current == True
            ).first()

    if not endpoint_switch or not endpoint_port:
        raise HTTPException(status_code=404, detail="Switch o porta non trovati")

    # Build the path using BFS from endpoint to all reachable switches via topology links
    # This traces back through the network topology
    path = []
    path_node_ids = []
    path_edge_keys = []

    # Get all topology links to build adjacency
    links = db.query(TopologyLink).all()

    # Build adjacency map (bidirectional)
    adjacency = {}  # switch_id -> [(neighbor_id, link)]
    for link in links:
        if link.local_switch_id not in adjacency:
            adjacency[link.local_switch_id] = []
        if link.remote_switch_id not in adjacency:
            adjacency[link.remote_switch_id] = []

        adjacency[link.local_switch_id].append((link.remote_switch_id, link))
        adjacency[link.remote_switch_id].append((link.local_switch_id, link))

    # BFS to find path from endpoint back to "core" (switch with most connections)
    # Or find the longest path back (typically to core switches)
    visited = set()
    parent = {}  # child_id -> (parent_id, link)
    queue = [endpoint_switch.id]
    visited.add(endpoint_switch.id)

    # Find all reachable switches
    while queue:
        current = queue.pop(0)
        if current in adjacency:
            for neighbor_id, link in adjacency[current]:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    parent[neighbor_id] = (current, link)
                    queue.append(neighbor_id)

    # Find the "core" switch - the one with most connections or furthest from endpoint
    # In a typical network, core switch has many connections
    core_switch_id = endpoint_switch.id
    if adjacency:
        # Find switch with most connections that's reachable
        max_connections = 0
        for sw_id in visited:
            conn_count = len(adjacency.get(sw_id, []))
            if conn_count > max_connections:
                max_connections = conn_count
                core_switch_id = sw_id

    # Build path from core to endpoint
    # Reconstruct path from core to endpoint
    if core_switch_id != endpoint_switch.id:
        # Do BFS from core to endpoint to get proper path
        visited2 = set()
        parent2 = {}
        queue2 = [core_switch_id]
        visited2.add(core_switch_id)

        while queue2:
            current = queue2.pop(0)
            if current == endpoint_switch.id:
                break
            if current in adjacency:
                for neighbor_id, link in adjacency[current]:
                    if neighbor_id not in visited2:
                        visited2.add(neighbor_id)
                        parent2[neighbor_id] = (current, link)
                        queue2.append(neighbor_id)

        # Reconstruct path from core to endpoint
        current = endpoint_switch.id
        path_switches = []
        path_links = []

        while current in parent2:
            path_switches.append(current)
            prev_id, link = parent2[current]
            path_links.append(link)
            current = prev_id
        path_switches.append(core_switch_id)

        # Reverse to get core -> endpoint order
        path_switches.reverse()
        path_links.reverse()

        # Build path response
        for i, sw_id in enumerate(path_switches):
            sw = db.query(Switch).filter(Switch.id == sw_id).first()
            if sw:
                port_name = None
                if i < len(path_links):
                    # Get the outgoing port for this link
                    link = path_links[i]
                    port = db.query(Port).filter(Port.id == link.local_port_id).first()
                    if port:
                        port_name = port.port_name
                elif sw.id == endpoint_switch.id:
                    # Last node is endpoint - use the endpoint port where MAC is connected
                    port_name = endpoint_port.port_name

                path.append(MacPathNode(
                    switch_id=sw.id,
                    hostname=sw.hostname,
                    ip_address=sw.ip_address,
                    port_name=port_name,
                    is_endpoint=(sw.id == endpoint_switch.id)
                ))
                path_node_ids.append(sw.id)

        # Build edge keys (format: "from-to" for vis.js)
        for link in path_links:
            # Edge key can be either direction
            path_edge_keys.append(f"{link.local_switch_id}-{link.remote_switch_id}")
            path_edge_keys.append(f"{link.remote_switch_id}-{link.local_switch_id}")
    else:
        # Only one switch in path (endpoint is core or isolated)
        path.append(MacPathNode(
            switch_id=endpoint_switch.id,
            hostname=endpoint_switch.hostname,
            ip_address=endpoint_switch.ip_address,
            port_name=endpoint_port.port_name,
            is_endpoint=True
        ))
        path_node_ids.append(endpoint_switch.id)

    return MacPathResponse(
        mac_address=mac.mac_address,
        ip_address=location.ip_address,
        vendor_name=mac.vendor_name,
        endpoint_switch_id=endpoint_switch.id,
        endpoint_switch_hostname=endpoint_switch.hostname,
        endpoint_port=endpoint_port.port_name,
        path=path,
        path_node_ids=path_node_ids,
        path_edge_keys=path_edge_keys
    )


@router.get("/by-site/{site_code}", response_model=TopologyResponse)
def get_topology_by_site(site_code: str, db: Session = Depends(get_db)):
    """Get network topology data for a specific site (filtered by site_code).

    Includes links to external switches (core/upstream) and shows them as additional nodes.
    """
    import math
    from sqlalchemy import or_

    # Get switches for this site
    site_switches = db.query(Switch).filter(
        Switch.is_active == True,
        Switch.site_code == site_code
    ).all()

    if not site_switches:
        return TopologyResponse(nodes=[], edges=[], last_updated=datetime.utcnow())

    site_switch_ids = [sw.id for sw in site_switches]

    # Get topology links where AT LEAST ONE endpoint is in this site
    # This includes links to external switches (core, other sites)
    links = db.query(TopologyLink).filter(
        or_(
            TopologyLink.local_switch_id.in_(site_switch_ids),
            TopologyLink.remote_switch_id.in_(site_switch_ids)
        )
    ).all()

    # Find external switches that are connected to this site
    external_switch_ids = set()
    for link in links:
        if link.local_switch_id not in site_switch_ids:
            external_switch_ids.add(link.local_switch_id)
        if link.remote_switch_id not in site_switch_ids:
            external_switch_ids.add(link.remote_switch_id)

    # Fetch external switches
    external_switches = []
    if external_switch_ids:
        external_switches = db.query(Switch).filter(
            Switch.id.in_(list(external_switch_ids))
        ).all()

    # Combine site switches + external switches
    all_switches = site_switches + external_switches

    # Build nodes
    nodes = []
    for i, switch in enumerate(all_switches):
        mac_count = db.query(MacLocation).filter(
            MacLocation.switch_id == switch.id,
            MacLocation.is_current == True
        ).count()

        angle = (2 * math.pi * i) / max(len(all_switches), 1)
        radius = 200

        # External switches get a different label prefix to distinguish them
        is_external = switch.id not in site_switch_ids
        label = f"[EXT] {switch.hostname}" if is_external else switch.hostname

        nodes.append(TopologyNode(
            id=switch.id,
            label=label,
            hostname=switch.hostname,
            ip_address=switch.ip_address,
            device_type=switch.device_type,
            is_active=switch.is_active,
            mac_count=mac_count,
            site_code=switch.site_code,
            x=radius * math.cos(angle),
            y=radius * math.sin(angle),
        ))

    # Deduplicate edges - keep only one link per switch pair + port combination
    # Two-pass: first collect links with real ports, then add Unknown only if no real link exists
    edge_pairs: dict = {}
    unknown_pairs: list = []
    for link in links:
        local_port = db.query(Port).filter(Port.id == link.local_port_id).first()
        remote_port = db.query(Port).filter(Port.id == link.remote_port_id).first() if link.remote_port_id else None

        local_port_name = local_port.port_name if local_port else "Unknown"
        remote_port_name = remote_port.port_name if remote_port else None

        min_id = min(link.local_switch_id, link.remote_switch_id)
        max_id = max(link.local_switch_id, link.remote_switch_id)

        # Skip links with unknown ports for now, process them after real links
        if local_port_name == "Unknown" and not remote_port_name:
            unknown_pairs.append((min_id, max_id, link))
            continue

        # Normalize port names to handle GE/Gi and XGE/XGi duplicates
        norm_local = _normalize_port_name(local_port_name)
        norm_remote = _normalize_port_name(remote_port_name or "")

        if link.local_switch_id == min_id:
            port_key = (norm_local, norm_remote)
        else:
            port_key = (norm_remote, norm_local)

        key = (min_id, max_id, port_key[0], port_key[1])

        if key not in edge_pairs:
            edge_pairs[key] = {
                'from': link.local_switch_id,
                'to': link.remote_switch_id,
                'local_port': local_port_name,
                'remote_port': remote_port_name,
                'protocol': link.protocol,
            }

    # Add unknown-port links only if no real link exists for that switch pair
    switch_pairs_with_real_links = {(k[0], k[1]) for k in edge_pairs}
    for min_id, max_id, link in unknown_pairs:
        if (min_id, max_id) not in switch_pairs_with_real_links:
            key = (min_id, max_id, "Unknown", "")
            if key not in edge_pairs:
                edge_pairs[key] = {
                    'from': link.local_switch_id,
                    'to': link.remote_switch_id,
                    'local_port': "Unknown",
                    'remote_port': None,
                    'protocol': link.protocol,
                }

    edges = []
    for edge_data in edge_pairs.values():
        edges.append(TopologyEdge(
            from_node=edge_data['from'],
            to=edge_data['to'],
            local_port=edge_data['local_port'],
            remote_port=edge_data['remote_port'],
            protocol=edge_data['protocol'],
        ))

    last_updated = None
    if links:
        last_updated = max(link.last_seen for link in links)

    return TopologyResponse(
        nodes=nodes,
        edges=edges,
        last_updated=last_updated or datetime.utcnow(),
    )


@router.get("/sites-summary")
def get_topology_sites_summary(db: Session = Depends(get_db)):
    """Get summary of topology by site code."""
    from sqlalchemy import func

    results = (
        db.query(
            Switch.site_code,
            func.count(Switch.id).label("switch_count")
        )
        .filter(Switch.is_active == True, Switch.site_code.isnot(None))
        .group_by(Switch.site_code)
        .order_by(Switch.site_code)
        .all()
    )

    sites = []
    for r in results:
        # Count links within this site
        switch_ids = [sw.id for sw in db.query(Switch.id).filter(Switch.site_code == r.site_code).all()]
        link_count = db.query(TopologyLink).filter(
            TopologyLink.local_switch_id.in_(switch_ids),
            TopologyLink.remote_switch_id.in_(switch_ids)
        ).count()

        sites.append({
            "site_code": r.site_code,
            "site_name": f"Sede {r.site_code}",
            "switch_count": r.switch_count,
            "link_count": link_count
        })

    return {"sites": sites, "total_sites": len(sites)}


@router.get("/switch/{switch_id}/macs", response_model=SwitchMacsResponse)
def get_switch_macs(switch_id: int, db: Session = Depends(get_db)):
    """Get MAC addresses connected to a specific switch."""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch non trovato")

    # Get MAC locations for this switch
    from app.db.models import MacAddress
    locations = (
        db.query(MacLocation, MacAddress, Port)
        .join(MacAddress, MacLocation.mac_id == MacAddress.id)
        .join(Port, MacLocation.port_id == Port.id)
        .filter(
            MacLocation.switch_id == switch_id,
            MacLocation.is_current == True
        )
        .all()
    )

    macs = []
    for loc, mac, port in locations:
        macs.append({
            "mac_address": mac.mac_address,
            "ip_address": loc.ip_address,
            "port_name": port.port_name,
            "vlan_id": loc.vlan_id,
            "vendor_name": mac.vendor_name,
            "last_seen": loc.seen_at.isoformat(),
        })

    return SwitchMacsResponse(
        switch_id=switch.id,
        switch_hostname=switch.hostname,
        mac_count=len(macs),
        macs=macs,
    )
