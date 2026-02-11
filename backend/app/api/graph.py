"""Network Graph API for offline path lookup.

Provides pre-calculated graph operations without SSH.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.network_graph import get_network_graph

router = APIRouter()


class GraphStatsResponse(BaseModel):
    """Graph statistics."""
    node_count: int
    edge_count: int
    core_switches: List[int]
    built_at: Optional[str]
    is_valid: bool


class PathNode(BaseModel):
    """Node in a path."""
    switch_id: int
    hostname: str
    ip_address: str
    port_name: Optional[str] = None
    is_endpoint: bool = False


class MacPathOfflineResponse(BaseModel):
    """Offline MAC path lookup response."""
    mac_address: str
    ip_address: Optional[str] = None
    vendor_name: Optional[str] = None
    endpoint_switch_id: int
    endpoint_switch_hostname: str
    endpoint_port: str
    path: List[PathNode]
    path_node_ids: List[int]
    path_edge_keys: List[str]
    lookup_type: str = "offline_graph"


class SwitchPathResponse(BaseModel):
    """Switch-to-switch path response."""
    from_switch_id: int
    to_switch_id: int
    path: List[int]
    hop_count: int


class NeighborInfo(BaseModel):
    """Switch neighbor information."""
    switch_id: int
    hostname: str
    ip_address: str
    local_port_id: Optional[int]
    remote_port_id: Optional[int]
    protocol: str


class SwitchNeighborsResponse(BaseModel):
    """Switch neighbors response."""
    switch_id: int
    neighbors: List[NeighborInfo]
    neighbor_count: int


@router.post("/build", response_model=GraphStatsResponse)
def build_graph(db: Session = Depends(get_db)):
    """
    Build or rebuild the network graph from topology data.

    Call this after LLDP discovery to update the cached graph.
    """
    graph = get_network_graph()
    stats = graph.build(db)
    return GraphStatsResponse(**stats)


@router.get("/stats", response_model=GraphStatsResponse)
def get_graph_stats():
    """Get current graph statistics."""
    graph = get_network_graph()
    stats = graph.get_stats()
    return GraphStatsResponse(**stats)


@router.get("/mac/{mac_address}", response_model=MacPathOfflineResponse)
def lookup_mac_path_offline(mac_address: str, db: Session = Depends(get_db)):
    """
    Lookup MAC address path using pre-calculated graph.

    This is the main offline lookup - no SSH required.
    Returns path from core to endpoint switch.
    """
    graph = get_network_graph()

    # Auto-build if not valid
    if not graph.is_valid:
        graph.build(db)

    result = graph.find_mac_path(mac_address, db)

    if not result:
        raise HTTPException(status_code=404, detail="MAC address non trovato o senza posizione corrente")

    return MacPathOfflineResponse(
        mac_address=result["mac_address"],
        ip_address=result.get("ip_address"),
        vendor_name=result.get("vendor_name"),
        endpoint_switch_id=result["endpoint_switch_id"],
        endpoint_switch_hostname=result["endpoint_switch_hostname"],
        endpoint_port=result["endpoint_port"],
        path=[PathNode(**n) for n in result["path"]],
        path_node_ids=result["path_node_ids"],
        path_edge_keys=result["path_edge_keys"],
        lookup_type=result.get("lookup_type", "offline_graph"),
    )


@router.get("/path/{from_switch_id}/{to_switch_id}", response_model=SwitchPathResponse)
def get_switch_path(from_switch_id: int, to_switch_id: int, db: Session = Depends(get_db)):
    """
    Find shortest path between two switches.

    Uses BFS on pre-calculated graph.
    """
    graph = get_network_graph()

    if not graph.is_valid:
        graph.build(db)

    path = graph.find_path(from_switch_id, to_switch_id)

    if not path:
        raise HTTPException(
            status_code=404,
            detail=f"Nessun percorso trovato tra switch {from_switch_id} e {to_switch_id}"
        )

    return SwitchPathResponse(
        from_switch_id=from_switch_id,
        to_switch_id=to_switch_id,
        path=path,
        hop_count=len(path) - 1,
    )


@router.get("/neighbors/{switch_id}", response_model=SwitchNeighborsResponse)
def get_switch_neighbors(switch_id: int, db: Session = Depends(get_db)):
    """Get all neighbors of a switch from the cached graph."""
    graph = get_network_graph()

    if not graph.is_valid:
        graph.build(db)

    neighbors = graph.get_switch_neighbors(switch_id)

    return SwitchNeighborsResponse(
        switch_id=switch_id,
        neighbors=[NeighborInfo(**n) for n in neighbors],
        neighbor_count=len(neighbors),
    )


@router.get("/core-switches")
def get_core_switches(db: Session = Depends(get_db)):
    """Get identified core switches (highest connectivity)."""
    graph = get_network_graph()

    if not graph.is_valid:
        graph.build(db)

    core_ids = graph.core_switch_ids
    core_info = []

    for sw_id in core_ids:
        sw_info = graph.switches.get(sw_id, {})
        neighbor_count = len(graph.adjacency.get(sw_id, {}))
        core_info.append({
            "switch_id": sw_id,
            "hostname": sw_info.get("hostname", "Unknown"),
            "ip_address": sw_info.get("ip_address", ""),
            "neighbor_count": neighbor_count,
        })

    return {
        "core_switches": core_info,
        "count": len(core_info),
    }


class PathSimulationRequest(BaseModel):
    """Request for path simulation between two endpoints."""
    source: str  # MAC or IP address
    destination: str  # MAC or IP address


class PathSimulationHop(BaseModel):
    """A hop in the simulated path."""
    hop_number: int
    switch_id: int
    switch_hostname: str
    switch_ip: str
    ingress_port: Optional[str] = None
    egress_port: Optional[str] = None
    vlan_id: Optional[int] = None
    latency_estimate_ms: float = 0.1  # Placeholder


class PathSimulationResponse(BaseModel):
    """Response for path simulation."""
    source: str
    source_mac: Optional[str] = None
    source_switch_id: Optional[int] = None
    source_switch: Optional[str] = None
    source_port: Optional[str] = None
    destination: str
    destination_mac: Optional[str] = None
    destination_switch_id: Optional[int] = None
    destination_switch: Optional[str] = None
    destination_port: Optional[str] = None
    path_found: bool
    hops: List[PathSimulationHop]
    total_hops: int
    estimated_latency_ms: float
    status: str  # "success", "destination_unreachable", "source_not_found", etc.
    notes: List[str]


@router.post("/simulate-path", response_model=PathSimulationResponse)
def simulate_path(request: PathSimulationRequest, db: Session = Depends(get_db)):
    """
    Simulate packet path between two endpoints (MAC or IP).

    This is a simplified simulation without ACL/firewall checks.
    Returns the L2 path through the network.
    """
    from app.db.models import MacAddress, MacLocation, Switch, Port

    graph = get_network_graph()
    if not graph.is_valid:
        graph.build(db)

    notes = []

    # Helper to find endpoint by MAC or IP
    def find_endpoint(identifier: str):
        # Normalize MAC
        mac_normalized = identifier.upper().replace("-", ":").replace(".", ":")

        # Try MAC first
        loc = db.query(MacLocation).join(MacAddress).filter(
            MacAddress.mac_address == mac_normalized,
            MacLocation.is_current == True
        ).first()

        if loc:
            mac = db.query(MacAddress).filter(MacAddress.id == loc.mac_id).first()
            sw = db.query(Switch).filter(Switch.id == loc.switch_id).first()
            pt = db.query(Port).filter(Port.id == loc.port_id).first()
            return {
                "mac": mac.mac_address if mac else None,
                "switch_id": sw.id if sw else None,
                "switch": sw.hostname if sw else None,
                "port": pt.port_name if pt else None,
            }

        # Try IP
        loc = db.query(MacLocation).filter(
            MacLocation.ip_address == identifier,
            MacLocation.is_current == True
        ).first()

        if loc:
            mac = db.query(MacAddress).filter(MacAddress.id == loc.mac_id).first()
            sw = db.query(Switch).filter(Switch.id == loc.switch_id).first()
            pt = db.query(Port).filter(Port.id == loc.port_id).first()
            return {
                "mac": mac.mac_address if mac else None,
                "switch_id": sw.id if sw else None,
                "switch": sw.hostname if sw else None,
                "port": pt.port_name if pt else None,
            }

        return None

    # Find source and destination
    source_info = find_endpoint(request.source)
    dest_info = find_endpoint(request.destination)

    if not source_info:
        return PathSimulationResponse(
            source=request.source,
            destination=request.destination,
            path_found=False,
            hops=[],
            total_hops=0,
            estimated_latency_ms=0,
            status="source_not_found",
            notes=[f"Source endpoint '{request.source}' not found in network"]
        )

    if not dest_info:
        return PathSimulationResponse(
            source=request.source,
            source_mac=source_info["mac"],
            source_switch_id=source_info["switch_id"],
            source_switch=source_info["switch"],
            source_port=source_info["port"],
            destination=request.destination,
            path_found=False,
            hops=[],
            total_hops=0,
            estimated_latency_ms=0,
            status="destination_not_found",
            notes=[f"Destination endpoint '{request.destination}' not found in network"]
        )

    # Same switch?
    if source_info["switch_id"] == dest_info["switch_id"]:
        sw = db.query(Switch).filter(Switch.id == source_info["switch_id"]).first()
        notes.append("Source and destination on same switch - direct L2 forwarding")
        return PathSimulationResponse(
            source=request.source,
            source_mac=source_info["mac"],
            source_switch_id=source_info["switch_id"],
            source_switch=source_info["switch"],
            source_port=source_info["port"],
            destination=request.destination,
            destination_mac=dest_info["mac"],
            destination_switch_id=dest_info["switch_id"],
            destination_switch=dest_info["switch"],
            destination_port=dest_info["port"],
            path_found=True,
            hops=[PathSimulationHop(
                hop_number=1,
                switch_id=sw.id,
                switch_hostname=sw.hostname,
                switch_ip=sw.ip_address,
                ingress_port=source_info["port"],
                egress_port=dest_info["port"],
                latency_estimate_ms=0.05
            )],
            total_hops=1,
            estimated_latency_ms=0.05,
            status="success",
            notes=notes
        )

    # Find path between switches
    path = graph.find_path(source_info["switch_id"], dest_info["switch_id"])

    if not path:
        notes.append("No L2 path exists between source and destination switches")
        return PathSimulationResponse(
            source=request.source,
            source_mac=source_info["mac"],
            source_switch_id=source_info["switch_id"],
            source_switch=source_info["switch"],
            source_port=source_info["port"],
            destination=request.destination,
            destination_mac=dest_info["mac"],
            destination_switch_id=dest_info["switch_id"],
            destination_switch=dest_info["switch"],
            destination_port=dest_info["port"],
            path_found=False,
            hops=[],
            total_hops=0,
            estimated_latency_ms=0,
            status="no_path",
            notes=notes
        )

    # Build hop list
    hops = []
    for i, sw_id in enumerate(path):
        sw = db.query(Switch).filter(Switch.id == sw_id).first()
        if sw:
            ingress = source_info["port"] if i == 0 else None
            egress = dest_info["port"] if i == len(path) - 1 else None
            hops.append(PathSimulationHop(
                hop_number=i + 1,
                switch_id=sw.id,
                switch_hostname=sw.hostname,
                switch_ip=sw.ip_address,
                ingress_port=ingress,
                egress_port=egress,
                latency_estimate_ms=0.1
            ))

    notes.append(f"L2 path found with {len(path)} hops")

    return PathSimulationResponse(
        source=request.source,
        source_mac=source_info["mac"],
        source_switch_id=source_info["switch_id"],
        source_switch=source_info["switch"],
        source_port=source_info["port"],
        destination=request.destination,
        destination_mac=dest_info["mac"],
        destination_switch_id=dest_info["switch_id"],
        destination_switch=dest_info["switch"],
        destination_port=dest_info["port"],
        path_found=True,
        hops=hops,
        total_hops=len(hops),
        estimated_latency_ms=len(hops) * 0.1,
        status="success",
        notes=notes
    )


@router.post("/invalidate")
def invalidate_graph():
    """Invalidate the cached graph (forces rebuild on next lookup)."""
    from app.services.network_graph import NetworkGraph
    NetworkGraph.invalidate()
    return {"status": "ok", "message": "Graph cache invalidated"}
