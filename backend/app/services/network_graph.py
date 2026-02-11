"""Network Graph Service for offline path lookup.

Pre-calculates and caches the network topology graph for fast MAC path tracing
without requiring SSH connections.
"""
import threading
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any

from sqlalchemy.orm import Session

from app.db.models import Switch, TopologyLink, Port, MacLocation, MacAddress


class NetworkGraph:
    """
    Pre-calculated network topology graph.

    Provides O(V+E) path lookups using cached adjacency lists.
    Thread-safe singleton pattern for app-wide caching.
    """

    _instance: Optional["NetworkGraph"] = None
    _lock = threading.Lock()

    def __init__(self):
        # Graph structure: switch_id -> {neighbor_id: link_data}
        self.adjacency: Dict[int, Dict[int, Dict]] = {}
        # Switch metadata cache
        self.switches: Dict[int, Dict] = {}
        # Port metadata cache
        self.ports: Dict[int, Dict] = {}
        # Core switches (highest connectivity)
        self.core_switch_ids: List[int] = []
        # Graph metadata
        self.node_count: int = 0
        self.edge_count: int = 0
        self.built_at: Optional[datetime] = None
        self.is_valid: bool = False

    @classmethod
    def get_instance(cls) -> "NetworkGraph":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def invalidate(cls):
        """Invalidate the cached graph (call after topology changes)."""
        with cls._lock:
            if cls._instance:
                cls._instance.is_valid = False

    def build(self, db: Session) -> Dict[str, Any]:
        """
        Build/rebuild the network graph from database.

        Returns stats about the built graph.
        """
        with self._lock:
            # Clear existing data
            self.adjacency.clear()
            self.switches.clear()
            self.ports.clear()
            self.core_switch_ids.clear()

            # Load all switches
            switches = db.query(Switch).all()
            for sw in switches:
                self.switches[sw.id] = {
                    "id": sw.id,
                    "hostname": sw.hostname,
                    "ip_address": sw.ip_address,
                    "site_code": self._extract_site_code(sw.hostname),
                }
                self.adjacency[sw.id] = {}

            # Load all ports
            ports = db.query(Port).all()
            for port in ports:
                self.ports[port.id] = {
                    "id": port.id,
                    "switch_id": port.switch_id,
                    "port_name": port.port_name,
                    "is_uplink": port.is_uplink,
                }

            # Load topology links and build bidirectional adjacency
            links = db.query(TopologyLink).all()
            for link in links:
                # Ensure both switches exist in adjacency
                if link.local_switch_id not in self.adjacency:
                    self.adjacency[link.local_switch_id] = {}
                if link.remote_switch_id not in self.adjacency:
                    self.adjacency[link.remote_switch_id] = {}

                # Add bidirectional edges
                link_data = {
                    "link_id": link.id,
                    "local_port_id": link.local_port_id,
                    "remote_port_id": link.remote_port_id,
                    "protocol": link.protocol,
                }

                self.adjacency[link.local_switch_id][link.remote_switch_id] = link_data
                # Reverse direction
                self.adjacency[link.remote_switch_id][link.local_switch_id] = {
                    "link_id": link.id,
                    "local_port_id": link.remote_port_id,
                    "remote_port_id": link.local_port_id,
                    "protocol": link.protocol,
                }

            # Identify core switches (top 5 by connectivity)
            connectivity = [
                (sw_id, len(neighbors))
                for sw_id, neighbors in self.adjacency.items()
            ]
            connectivity.sort(key=lambda x: x[1], reverse=True)
            self.core_switch_ids = [sw_id for sw_id, _ in connectivity[:5]]

            # Update metadata
            self.node_count = len(self.switches)
            self.edge_count = len(links)
            self.built_at = datetime.utcnow()
            self.is_valid = True

            return self.get_stats()

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "core_switches": self.core_switch_ids,
            "built_at": self.built_at.isoformat() if self.built_at else None,
            "is_valid": self.is_valid,
        }

    def find_path(self, from_switch_id: int, to_switch_id: int) -> Optional[List[int]]:
        """
        Find shortest path between two switches using BFS.

        Returns list of switch IDs from start to end, or None if no path.
        """
        if from_switch_id not in self.adjacency or to_switch_id not in self.adjacency:
            return None

        if from_switch_id == to_switch_id:
            return [from_switch_id]

        # BFS
        visited: Set[int] = {from_switch_id}
        queue: deque = deque([(from_switch_id, [from_switch_id])])

        while queue:
            current, path = queue.popleft()

            for neighbor_id in self.adjacency.get(current, {}).keys():
                if neighbor_id == to_switch_id:
                    return path + [neighbor_id]

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_id]))

        return None

    def find_path_to_core(self, switch_id: int) -> Optional[List[int]]:
        """
        Find path from a switch to the nearest core switch.

        Returns path from switch to core, or None if isolated.
        """
        if not self.core_switch_ids:
            return None

        # Try to reach any core switch
        shortest_path: Optional[List[int]] = None

        for core_id in self.core_switch_ids:
            path = self.find_path(switch_id, core_id)
            if path:
                if shortest_path is None or len(path) < len(shortest_path):
                    shortest_path = path

        return shortest_path

    def find_mac_path(self, mac_address: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        Find the network path for a MAC address from core to endpoint.

        This is the main offline lookup function.
        """
        # Normalize MAC
        mac_normalized = mac_address.upper().replace('-', ':')

        # Find MAC in database
        mac = db.query(MacAddress).filter(MacAddress.mac_address == mac_normalized).first()
        if not mac:
            return None

        # Get current location
        location = db.query(MacLocation).filter(
            MacLocation.mac_id == mac.id,
            MacLocation.is_current == True
        ).first()

        if not location:
            return None

        endpoint_switch_id = location.switch_id
        endpoint_port_id = location.port_id

        # Get endpoint switch info
        endpoint_switch = self.switches.get(endpoint_switch_id)
        if not endpoint_switch:
            # Switch not in graph - try to load
            sw = db.query(Switch).filter(Switch.id == endpoint_switch_id).first()
            if sw:
                endpoint_switch = {
                    "id": sw.id,
                    "hostname": sw.hostname,
                    "ip_address": sw.ip_address,
                }

        # Get endpoint port info
        endpoint_port = self.ports.get(endpoint_port_id)
        if not endpoint_port:
            port = db.query(Port).filter(Port.id == endpoint_port_id).first()
            if port:
                endpoint_port = {
                    "id": port.id,
                    "port_name": port.port_name,
                }

        # Find path from core to endpoint
        path_switch_ids: List[int] = []

        if self.core_switch_ids:
            # Find which core can reach endpoint
            for core_id in self.core_switch_ids:
                path = self.find_path(core_id, endpoint_switch_id)
                if path:
                    path_switch_ids = path
                    break

        if not path_switch_ids:
            # Endpoint is isolated or IS the core
            path_switch_ids = [endpoint_switch_id]

        # Build detailed path with switch info
        path_details = []
        edge_keys = []

        for i, sw_id in enumerate(path_switch_ids):
            sw_info = self.switches.get(sw_id)
            if sw_info:
                node = {
                    "switch_id": sw_id,
                    "hostname": sw_info.get("hostname", "Unknown"),
                    "ip_address": sw_info.get("ip_address", ""),
                    "is_endpoint": sw_id == endpoint_switch_id,
                }

                # Add outgoing port if not last node
                if i < len(path_switch_ids) - 1:
                    next_sw_id = path_switch_ids[i + 1]
                    link_data = self.adjacency.get(sw_id, {}).get(next_sw_id)
                    if link_data:
                        port_info = self.ports.get(link_data.get("local_port_id"))
                        if port_info:
                            node["port_name"] = port_info.get("port_name")
                        # Add edge keys for visualization
                        edge_keys.append(f"{sw_id}-{next_sw_id}")
                        edge_keys.append(f"{next_sw_id}-{sw_id}")

                path_details.append(node)

        return {
            "mac_address": mac_normalized,
            "ip_address": location.ip_address,
            "vendor_name": mac.vendor_name,
            "endpoint_switch_id": endpoint_switch_id,
            "endpoint_switch_hostname": endpoint_switch.get("hostname", "Unknown") if endpoint_switch else "Unknown",
            "endpoint_port": endpoint_port.get("port_name", "Unknown") if endpoint_port else "Unknown",
            "path": path_details,
            "path_node_ids": path_switch_ids,
            "path_edge_keys": edge_keys,
            "lookup_type": "offline_graph",
        }

    def get_switch_neighbors(self, switch_id: int) -> List[Dict[str, Any]]:
        """Get all neighbors of a switch with link details."""
        neighbors = []
        for neighbor_id, link_data in self.adjacency.get(switch_id, {}).items():
            sw_info = self.switches.get(neighbor_id, {})
            neighbors.append({
                "switch_id": neighbor_id,
                "hostname": sw_info.get("hostname", "Unknown"),
                "ip_address": sw_info.get("ip_address", ""),
                "local_port_id": link_data.get("local_port_id"),
                "remote_port_id": link_data.get("remote_port_id"),
                "protocol": link_data.get("protocol"),
            })
        return neighbors

    def _extract_site_code(self, hostname: str) -> Optional[str]:
        """Extract site code from hostname (e.g., L2_CED_29 -> 29)."""
        if not hostname:
            return None
        parts = hostname.split('_')
        if len(parts) >= 3:
            return parts[-1]
        return None


# Singleton accessor
def get_network_graph() -> NetworkGraph:
    """Get the global network graph instance."""
    return NetworkGraph.get_instance()
