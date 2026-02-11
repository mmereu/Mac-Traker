"""MAC Path API endpoint for topology highlighting."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Switch, TopologyLink, Port, MacLocation, MacAddress

router = APIRouter()


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


@router.get("/{mac_address}", response_model=MacPathResponse)
def get_mac_path(mac_address: str, db: Session = Depends(get_db)):
    """
    Get the network path from core to endpoint for a MAC address.
    Returns the path of switches from core -> distribution -> access.
    """
    # Normalize MAC address format (support both : and - separators)
    mac_normalized = mac_address.upper().replace('-', ':')

    # Find the MAC address
    mac = db.query(MacAddress).filter(MacAddress.mac_address == mac_normalized).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC address non trovato")

    # Get current location
    location = db.query(MacLocation).filter(
        MacLocation.mac_id == mac.id,
        MacLocation.is_current == True
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="MAC non ha una posizione corrente")

    # Get endpoint switch and port
    endpoint_switch = db.query(Switch).filter(Switch.id == location.switch_id).first()
    endpoint_port = db.query(Port).filter(Port.id == location.port_id).first()

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
