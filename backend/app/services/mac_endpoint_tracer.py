"""MAC Endpoint Tracer Service.

This service traces a MAC address through the network topology to find the
actual physical endpoint (the port where the device is directly connected).

CORRECT Algorithm (start from Core, go downstream):
1. Find the CORE switch for the site where MAC is seen
2. Query MAC table on Core to find which port/Eth-Trunk has the MAC
3. If MAC is on Eth-Trunk:
   a) Resolve Eth-Trunk members (physical ports) via SNMP or CLI
   b) Query LLDP on trunk member ports to find downstream switch
4. Follow LLDP chain downstream until:
   a) Port has NO LLDP neighbor = ENDPOINT FOUND
   b) Port is connected to unmanaged device = ENDPOINT FOUND

Key insight:
- MAC addresses flow FROM endpoint TOWARD Core (source learning)
- To find endpoint, start at Core and follow the path backward (downstream)
- Eth-Trunk must be resolved to physical member ports to follow LLDP

WRONG approach (what we were doing before):
- Starting from random switches and trying to score locations
- Not resolving Eth-Trunk to physical ports
- Not following LLDP chain systematically from Core
"""

from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass
from sqlalchemy.orm import Session
import logging
import re
import asyncio

from app.db.models import (
    MacAddress, MacLocation, Switch, Port, TopologyLink, SwitchGroup
)

logger = logging.getLogger(__name__)


@dataclass
class TraceStep:
    """A single step in the MAC trace path."""
    switch_hostname: str
    switch_ip: str
    port_name: str
    port_type: str  # 'eth-trunk', 'physical', 'access'
    lldp_neighbor: Optional[str] = None
    mac_found: bool = True


@dataclass
class EndpointInfo:
    """Information about the physical endpoint of a MAC address."""
    mac_address: str
    switch_id: int
    switch_hostname: str
    switch_ip: str
    port_id: int
    port_name: str
    vlan_id: Optional[int]
    lldp_device_name: Optional[str] = None  # Device name from LLDP if available
    is_endpoint: bool = True  # True if this is the final endpoint (no LLDP neighbor)
    trace_path: List[str] = None  # Path taken to reach this endpoint

    def __post_init__(self):
        if self.trace_path is None:
            self.trace_path = []


class MacEndpointTracer:
    """Service to trace MAC addresses to their physical endpoints.

    CORRECT Algorithm (follow-the-trail via SSH):
    1. Start from Core switch (xxx_L3_xxx_251)
    2. Run `dis mac-ad <mac>` to find which port/Eth-Trunk has the MAC
    3. If Eth-Trunk: run `dis eth-trunk X` to get physical member ports
    4. Run `dis lldp neighbor interface <port>` to find downstream switch
    5. SSH to downstream switch and repeat until access port found
    """

    # Threshold: ports with more than this many MACs are likely uplinks
    UPLINK_MAC_THRESHOLD = 5

    def __init__(self, db: Session):
        self.db = db
        self._topology_cache: Dict[Tuple[int, int], TopologyLink] = {}
        self._switch_cache: Dict[int, Switch] = {}
        self._port_cache: Dict[int, Port] = {}
        self._port_name_to_ids: Dict[Tuple[int, str], List[int]] = {}  # (switch_id, normalized_name) -> [port_ids]
        self._port_mac_count_cache: Dict[Tuple[int, int], int] = {}  # (switch_id, port_id) -> mac_count
        self._snmp_service = None  # Lazy load SNMP service
        self._ssh_connections: Dict[str, any] = {}  # Cache SSH connections by IP

    def _get_snmp_service(self):
        """Lazy load SNMP service to avoid circular imports."""
        if self._snmp_service is None:
            try:
                from app.services.discovery.snmp_discovery import SNMPDiscoveryService
                self._snmp_service = SNMPDiscoveryService(self.db)
            except ImportError:
                logger.warning("SNMPDiscoveryService not available")
            except Exception as e:
                logger.warning(f"Cannot initialize SNMPDiscoveryService: {e}")
        return self._snmp_service

    # =========================================================================
    # SSH-BASED FOLLOW-THE-TRAIL ALGORITHM
    # =========================================================================

    def _get_ssh_credentials(self, switch: Switch) -> Dict[str, str]:
        """Get SSH credentials for a switch from its group."""
        credentials = {
            "username": "admin",
            "password": "",
            "port": 22,
        }

        if switch.group_id:
            group = self.db.query(SwitchGroup).filter(SwitchGroup.id == switch.group_id).first()
            if group:
                if group.ssh_username:
                    credentials["username"] = group.ssh_username
                if group.ssh_password_encrypted:
                    credentials["password"] = group.ssh_password_encrypted
                if group.ssh_port:
                    credentials["port"] = group.ssh_port

        return credentials

    def _get_ssh_connection(self, switch: Switch):
        """Get or create SSH connection to a switch."""
        from netmiko import ConnectHandler

        if switch.ip_address in self._ssh_connections:
            conn = self._ssh_connections[switch.ip_address]
            # Check if connection is still alive
            try:
                conn.find_prompt()
                return conn
            except Exception:
                # Connection dead, remove from cache
                try:
                    conn.disconnect()
                except:
                    pass
                del self._ssh_connections[switch.ip_address]

        credentials = self._get_ssh_credentials(switch)
        device_type = (switch.device_type or "huawei").lower()
        netmiko_type = {
            "huawei": "huawei",
            "cisco": "cisco_ios",
            "extreme": "extreme",
        }.get(device_type, "huawei")

        logger.info(f"SSH connecting to {switch.hostname} ({switch.ip_address})")

        device = {
            'device_type': netmiko_type,
            'ip': switch.ip_address,
            'username': credentials['username'],
            'password': credentials['password'],
            'port': credentials['port'],
            'timeout': 30,
            'auth_timeout': 30,
            'banner_timeout': 30,
        }

        conn = ConnectHandler(**device)
        self._ssh_connections[switch.ip_address] = conn
        return conn

    def _close_ssh_connections(self):
        """Close all cached SSH connections."""
        for ip, conn in self._ssh_connections.items():
            try:
                conn.disconnect()
            except:
                pass
        self._ssh_connections.clear()

    def _ssh_find_mac_port(self, connection, mac_address: str) -> Optional[str]:
        """Run 'dis mac-ad <mac>' and return the port where MAC is learned.

        Returns port name like 'Eth-Trunk81' or 'GigabitEthernet0/0/5'.
        """
        # Convert MAC to Huawei format: xxxx-xxxx-xxxx
        mac_clean = mac_address.replace(':', '').replace('-', '').upper()
        mac_huawei = f"{mac_clean[0:4]}-{mac_clean[4:8]}-{mac_clean[8:12]}"

        cmd = f"display mac-address {mac_huawei}"
        logger.debug(f"SSH command: {cmd}")

        output = connection.send_command(cmd)
        logger.debug(f"MAC lookup output:\n{output}")

        # Parse output to find port
        # Example output:
        # MAC Address       VLAN/VSI/BD   Learned-From        Type
        # -------------------------------------------------------------------------------
        # 0018-6e35-7631    100           Eth-Trunk81         dynamic
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith('-') or 'MAC Address' in line:
                continue

            # Look for the MAC in the line
            if mac_huawei.lower() in line.lower() or mac_clean.lower() in line.lower():
                parts = line.split()
                if len(parts) >= 3:
                    # Port is typically the 3rd column
                    port_name = parts[2]
                    logger.info(f"MAC {mac_address} found on port {port_name}")
                    return port_name

        logger.warning(f"MAC {mac_address} not found in output")
        return None

    def _ssh_get_eth_trunk_members(self, connection, trunk_name: str) -> List[str]:
        """Run 'dis eth-trunk X' and return list of physical member ports.

        Returns list like ['XGigabitEthernet1/0/8', 'XGigabitEthernet2/0/8'].
        """
        # Extract trunk number from name
        trunk_match = re.search(r'(\d+)$', trunk_name)
        if not trunk_match:
            logger.warning(f"Cannot parse trunk number from {trunk_name}")
            return []

        trunk_num = trunk_match.group(1)
        cmd = f"display eth-trunk {trunk_num}"
        logger.debug(f"SSH command: {cmd}")

        output = connection.send_command(cmd)
        logger.debug(f"Eth-Trunk output:\n{output}")

        members = []

        # Parse output to find member interfaces
        # Example output:
        # Eth-Trunk81's state information is:
        # ...
        # PortName                      Status      Weight
        # XGigabitEthernet1/0/8         Up          1
        # XGigabitEthernet2/0/8         Up          1
        # XGigabitEthernet3/0/8         Up          1
        in_port_section = False
        for line in output.split('\n'):
            line = line.strip()

            if 'PortName' in line and 'Status' in line:
                in_port_section = True
                continue

            if in_port_section and line:
                parts = line.split()
                if parts and ('Ethernet' in parts[0] or 'XGE' in parts[0] or 'GE' in parts[0]):
                    members.append(parts[0])

        logger.info(f"Eth-Trunk {trunk_name} members: {members}")
        return members

    def _ssh_get_lldp_neighbor(self, connection, port_name: str) -> Optional[Tuple[str, str]]:
        """Run 'dis lldp neighbor interface <port>' and return neighbor info.

        Returns (neighbor_hostname, neighbor_port) or None.
        """
        # Normalize port name for Huawei CLI
        # XGE2/0/1 -> XGigabitEthernet2/0/1
        # GE0/0/1 -> GigabitEthernet0/0/1
        normalized_port = port_name
        if port_name.upper().startswith('XGE') and not port_name.upper().startswith('XGIGABIT'):
            normalized_port = 'XGigabitEthernet' + port_name[3:]
        elif port_name.upper().startswith('GE') and not port_name.upper().startswith('GIGABIT'):
            normalized_port = 'GigabitEthernet' + port_name[2:]

        cmd = f"display lldp neighbor interface {normalized_port}"
        logger.debug(f"SSH command: {cmd}")

        output = connection.send_command(cmd)
        logger.debug(f"LLDP output:\n{output}")

        # Parse LLDP output
        # Example:
        # LLDP neighbor-information of interface XGigabitEthernet1/0/8:
        #   Neighbor index :1
        #   ...
        #   System name     :07_L2_RACK01_Formaggi_NEW_181
        #   Port ID         :XGigabitEthernet0/0/50
        neighbor_name = None
        neighbor_port = None

        for line in output.split('\n'):
            line = line.strip()

            if 'System name' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    neighbor_name = parts[1].strip()

            if 'Port ID' in line and 'subtype' not in line.lower():
                parts = line.split(':')
                if len(parts) >= 2:
                    neighbor_port = parts[1].strip()

        if neighbor_name:
            logger.info(f"LLDP on {port_name} -> {neighbor_name}:{neighbor_port}")
            return (neighbor_name, neighbor_port or "unknown")

        logger.debug(f"No LLDP neighbor on {port_name}")
        return None

    def _find_switch_by_hostname(self, hostname: str) -> Optional[Switch]:
        """Find switch in DB by hostname (exact or partial match)."""
        # Try exact match first
        switch = self.db.query(Switch).filter(Switch.hostname == hostname).first()
        if switch:
            return switch

        # Try partial match (hostname might be truncated in LLDP)
        switch = self.db.query(Switch).filter(Switch.hostname.ilike(f"%{hostname}%")).first()
        return switch

    async def trace_via_ssh(self, mac_address: str, site_code: Optional[str] = None) -> Optional[EndpointInfo]:
        """
        CORRECT follow-the-trail algorithm using SSH commands.

        Steps:
        1. Find the Core switch for the site where MAC is seen (or use provided site_code)
        2. SSH to Core, run `dis mac-ad <mac>` to find port/Eth-Trunk
        3. If Eth-Trunk, run `dis eth-trunk X` to get physical members
        4. For each member, run `dis lldp neighbor interface <port>`
        5. SSH to downstream switch, find MAC port, repeat
        6. Stop when port has NO LLDP neighbor = ENDPOINT FOUND

        Args:
            mac_address: MAC address in format XX:XX:XX:XX:XX:XX
            site_code: Optional site code (e.g., '07', '09'). If not provided, determined from DB.

        Returns EndpointInfo with complete trace path.
        """
        trace_path: List[TraceStep] = []

        try:
            # Step 1: Determine site code
            mac = None
            if site_code is None:
                # Try to find MAC in database to determine site
                mac = (
                    self.db.query(MacAddress)
                    .filter(MacAddress.mac_address == mac_address)
                    .first()
                )

                if mac:
                    # Get any location to determine site
                    any_location = (
                        self.db.query(MacLocation)
                        .join(Switch)
                        .filter(MacLocation.mac_id == mac.id)
                        .first()
                    )
                    if any_location:
                        any_switch = self._get_switch(any_location.switch_id)
                        if any_switch:
                            site_code = self._extract_site_code(any_switch.hostname)

                if not site_code:
                    # MAC not in DB and no site specified - try ALL Core switches
                    logger.info(f"MAC {mac_address} not in DB, searching all Core switches...")
                    all_cores = self._get_all_core_switches()
                    if not all_cores:
                        logger.warning(f"No Core switches found in database")
                        return None

                    # Try each Core switch until we find the MAC
                    for core in all_cores:
                        logger.info(f"Trying Core {core.hostname} for MAC {mac_address}...")
                        result = await self._trace_from_single_core(mac_address, core, trace_path)
                        if result:
                            logger.info(f"Found MAC {mac_address} via Core {core.hostname}")
                            return result
                        trace_path.clear()  # Reset for next attempt

                    logger.warning(f"MAC {mac_address} not found on any Core switch")
                    return None
            else:
                logger.info(f"Using provided site code: {site_code}")

            # Step 2: Find Core switch for this site
            core_switch = self._find_core_switch_for_site(site_code)
            if not core_switch:
                logger.warning(f"No Core switch found for site {site_code}")
                return None

            # Use the single-core trace helper
            return await self._trace_from_single_core(mac_address, core_switch, trace_path)

        except Exception as e:
            logger.error(f"Error tracing MAC {mac_address}: {e}", exc_info=True)
            return None

    async def _trace_from_single_core(self, mac_address: str, core_switch: Switch, trace_path: List[TraceStep]) -> Optional[EndpointInfo]:
        """Trace MAC starting from a specific Core switch.

        This is the main tracing logic extracted to allow multi-site search.
        """
        try:
            logger.info(f"=== TRACE START: MAC {mac_address} from Core {core_switch.hostname} ===")

            # Step 3: SSH trace loop
            current_switch = core_switch
            visited_switches: Set[str] = set()
            max_hops = 10  # Safety limit

            for hop in range(max_hops):
                if current_switch.hostname in visited_switches:
                    logger.warning(f"Loop detected at {current_switch.hostname}")
                    break
                visited_switches.add(current_switch.hostname)

                logger.info(f"Hop {hop + 1}: Checking {current_switch.hostname}")

                # SSH connect to current switch
                try:
                    conn = self._get_ssh_connection(current_switch)
                except Exception as e:
                    logger.error(f"SSH connection failed to {current_switch.hostname}: {e}")
                    break

                # Find MAC port on this switch
                port_name = self._ssh_find_mac_port(conn, mac_address)
                if not port_name:
                    logger.info(f"MAC not found on {current_switch.hostname} - possibly behind this switch")
                    break

                port_type = "eth-trunk" if "trunk" in port_name.lower() else "physical"

                # Check if this is an Eth-Trunk
                if "trunk" in port_name.lower():
                    logger.info(f"MAC on Eth-Trunk {port_name}, resolving members...")

                    members = self._ssh_get_eth_trunk_members(conn, port_name)
                    if not members:
                        logger.warning(f"Cannot get trunk members for {port_name}")
                        trace_path.append(TraceStep(
                            switch_hostname=current_switch.hostname,
                            switch_ip=current_switch.ip_address,
                            port_name=port_name,
                            port_type="eth-trunk",
                            lldp_neighbor=None
                        ))
                        break

                    # Try each trunk member for LLDP
                    found_next = False
                    for member_port in members:
                        neighbor = self._ssh_get_lldp_neighbor(conn, member_port)
                        if neighbor:
                            neighbor_name, neighbor_port = neighbor

                            trace_path.append(TraceStep(
                                switch_hostname=current_switch.hostname,
                                switch_ip=current_switch.ip_address,
                                port_name=f"{port_name} -> {member_port}",
                                port_type="eth-trunk",
                                lldp_neighbor=neighbor_name
                            ))

                            # Find next switch in DB
                            next_switch = self._find_switch_by_hostname(neighbor_name)
                            if next_switch:
                                current_switch = next_switch
                                found_next = True
                                break
                            else:
                                logger.warning(f"Neighbor {neighbor_name} not found in DB")

                    if not found_next:
                        logger.warning(f"No valid LLDP path from trunk members")
                        break

                else:
                    # Regular physical port - check for LLDP neighbor
                    neighbor = self._ssh_get_lldp_neighbor(conn, port_name)

                    if neighbor is None:
                        # NO LLDP = ENDPOINT FOUND!
                        logger.info(f"=== ENDPOINT FOUND: {current_switch.hostname}:{port_name} ===")

                        trace_path.append(TraceStep(
                            switch_hostname=current_switch.hostname,
                            switch_ip=current_switch.ip_address,
                            port_name=port_name,
                            port_type="access",
                            lldp_neighbor=None
                        ))

                        # Get port from DB for complete info
                        port = (
                            self.db.query(Port)
                            .filter(
                                Port.switch_id == current_switch.id,
                                Port.port_name == port_name
                            )
                            .first()
                        )

                        # Get VLAN from location if available (try to find MAC in DB)
                        loc = None
                        mac_obj = self.db.query(MacAddress).filter(MacAddress.mac_address == mac_address).first()
                        if mac_obj:
                            loc = (
                                self.db.query(MacLocation)
                                .filter(
                                    MacLocation.mac_id == mac_obj.id,
                                    MacLocation.switch_id == current_switch.id
                                )
                                .first()
                            )

                        return EndpointInfo(
                            mac_address=mac_address,
                            switch_id=current_switch.id,
                            switch_hostname=current_switch.hostname,
                            switch_ip=current_switch.ip_address,
                            port_id=port.id if port else 0,
                            port_name=port_name,
                            vlan_id=loc.vlan_id if loc else None,
                            is_endpoint=True,
                            trace_path=[f"{s.switch_hostname}:{s.port_name}" for s in trace_path]
                        )

                    else:
                        # Has LLDP neighbor - follow the trail
                        neighbor_name, neighbor_port = neighbor

                        trace_path.append(TraceStep(
                            switch_hostname=current_switch.hostname,
                            switch_ip=current_switch.ip_address,
                            port_name=port_name,
                            port_type="uplink",
                            lldp_neighbor=neighbor_name
                        ))

                        # Find next switch in DB
                        next_switch = self._find_switch_by_hostname(neighbor_name)
                        if next_switch:
                            current_switch = next_switch
                        else:
                            logger.warning(f"Neighbor {neighbor_name} not found in DB - end of trace")
                            break

            # Trace ended without finding clear endpoint
            if trace_path:
                last_step = trace_path[-1]
                return EndpointInfo(
                    mac_address=mac_address,
                    switch_id=current_switch.id,
                    switch_hostname=last_step.switch_hostname,
                    switch_ip=last_step.switch_ip if hasattr(last_step, 'switch_ip') else current_switch.ip_address,
                    port_id=0,
                    port_name=last_step.port_name,
                    vlan_id=None,
                    is_endpoint=False,
                    trace_path=[f"{s.switch_hostname}:{s.port_name}" for s in trace_path]
                )

            return None

        finally:
            # Don't close connections - keep them cached for reuse
            pass

    def trace_sync(self, mac_address: str, site_code: Optional[str] = None) -> Optional[EndpointInfo]:
        """Synchronous wrapper for trace_via_ssh for non-async contexts."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new loop
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.trace_via_ssh(mac_address, site_code))
            else:
                return loop.run_until_complete(self.trace_via_ssh(mac_address, site_code))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.trace_via_ssh(mac_address, site_code))

    def _find_core_switch_for_site(self, site_code: str) -> Optional[Switch]:
        """Find the Core/L3 switch for a given site code.

        Site code is extracted from hostname (e.g., '10' from '10_L2_Rack0_25').
        Core switches typically have 'L3' or 'Core' in hostname and .251 IP.
        """
        # Try to find L3 switch for this site
        core = (
            self.db.query(Switch)
            .filter(
                Switch.hostname.like(f"{site_code}_%"),
                Switch.hostname.like("%L3%")
            )
            .first()
        )
        if core:
            return core

        # Try to find switch with .251 IP (typical Core)
        core = (
            self.db.query(Switch)
            .filter(
                Switch.hostname.like(f"{site_code}_%"),
                Switch.ip_address.like(f"%.{site_code}.%.251")
            )
            .first()
        )
        if core:
            return core

        # Fallback: any switch with 'Core' in name
        core = (
            self.db.query(Switch)
            .filter(
                Switch.hostname.like(f"{site_code}_%"),
                Switch.hostname.ilike("%core%")
            )
            .first()
        )
        return core

    def _get_all_core_switches(self) -> List[Switch]:
        """Get all Core/L3 switches from the database.

        Used when site is not specified to search across all sites.
        Returns switches with 'L3' in hostname or '.251' IP.
        """
        # Find all L3 switches
        cores = (
            self.db.query(Switch)
            .filter(Switch.hostname.like("%L3%"))
            .all()
        )

        # Also include switches with Core in name
        cores_by_name = (
            self.db.query(Switch)
            .filter(Switch.hostname.ilike("%core%"))
            .all()
        )

        # Combine and deduplicate
        all_cores = {s.id: s for s in cores}
        for s in cores_by_name:
            all_cores[s.id] = s

        result = list(all_cores.values())
        logger.info(f"Found {len(result)} Core switches for multi-site search")
        return result

    def _extract_site_code(self, hostname: str) -> Optional[str]:
        """Extract site code from hostname (e.g., '10' from '10_L2_Rack0_25')."""
        match = re.match(r'^(\d+)_', hostname)
        if match:
            return match.group(1)
        return None

    def _get_eth_trunk_members(self, switch: Switch, trunk_name: str) -> List[str]:
        """Get physical port members of an Eth-Trunk via SNMP.

        Uses Huawei-specific OID or standard LAG MIB to find trunk members.
        Returns list of physical port names (e.g., ['XGigabitEthernet1/0/19', 'XGigabitEthernet2/0/19'])
        """
        members = []

        # Extract trunk number from name (Eth-Trunk25 -> 25)
        trunk_match = re.search(r'(\d+)$', trunk_name)
        if not trunk_match:
            logger.warning(f"Cannot extract trunk number from {trunk_name}")
            return members

        trunk_num = int(trunk_match.group(1))

        # Try to find members via LLDP data in DB
        # Trunk members typically have LLDP neighbors pointing to same remote switch
        all_links = (
            self.db.query(TopologyLink)
            .filter(TopologyLink.local_switch_id == switch.id)
            .all()
        )

        # Group links by remote switch - trunk members go to same switch
        links_by_remote: Dict[int, List[TopologyLink]] = {}
        for link in all_links:
            if link.remote_switch_id not in links_by_remote:
                links_by_remote[link.remote_switch_id] = []
            links_by_remote[link.remote_switch_id].append(link)

        # Find groups with multiple links (potential LAG members)
        for remote_id, links in links_by_remote.items():
            if len(links) >= 2:
                # Multiple links to same switch = likely trunk
                port_names = []
                for link in links:
                    port = self._get_port(link.local_port_id)
                    if port:
                        port_names.append(port.port_name)

                if port_names:
                    logger.info(f"Trunk {trunk_name} potential members via LLDP: {port_names}")
                    members.extend(port_names)
                    break  # Found a LAG group

        # If no members found via DB, try SNMP query
        if not members and switch.snmp_community:
            snmp = self._get_snmp_service()
            if snmp:
                try:
                    # Query ifName for all interfaces, look for ones in the trunk
                    # This is a simplified approach - actual trunk membership
                    # would need Huawei-specific MIB
                    logger.info(f"Trying SNMP to find trunk {trunk_name} members on {switch.ip_address}")
                except Exception as e:
                    logger.warning(f"SNMP query failed for trunk members: {e}")

        return members

    def _get_lldp_neighbor_for_port_name(self, switch_id: int, port_name: str) -> Optional[Tuple[Switch, str]]:
        """Get LLDP neighbor for a port by name, handling name variations.

        Returns (remote_switch, remote_port_name) or None.
        """
        # Find port in DB with this name or similar names
        normalized = self._normalize_port_name(port_name)

        ports = (
            self.db.query(Port)
            .filter(Port.switch_id == switch_id)
            .all()
        )

        matching_port_ids = []
        for p in ports:
            if self._normalize_port_name(p.port_name) == normalized:
                matching_port_ids.append(p.id)

        # Check LLDP for each matching port
        for port_id in matching_port_ids:
            link = self._get_lldp_neighbor(switch_id, port_id)
            if link:
                remote_switch = self._get_switch(link.remote_switch_id)
                remote_port = self._get_port(link.remote_port_id) if link.remote_port_id else None
                if remote_switch:
                    return (remote_switch, remote_port.port_name if remote_port else "unknown")

        return None

    def trace_from_core(self, mac_address: str) -> Optional[EndpointInfo]:
        """
        CORRECT tracing algorithm: Start from Core switch and follow downstream.

        Steps:
        1. Find site code from any switch that sees this MAC
        2. Get the Core switch for that site
        3. Find MAC location on Core (usually on Eth-Trunk)
        4. If on Eth-Trunk, resolve physical member ports
        5. Follow LLDP from trunk members to downstream switch
        6. Repeat until port has no LLDP neighbor = ENDPOINT

        Returns EndpointInfo with the actual physical endpoint.
        """
        # Find MAC in database
        mac = (
            self.db.query(MacAddress)
            .filter(MacAddress.mac_address == mac_address)
            .first()
        )
        if not mac:
            logger.warning(f"MAC {mac_address} not found in database")
            return None

        # Get any location to determine site
        any_location = (
            self.db.query(MacLocation)
            .join(Switch)
            .filter(MacLocation.mac_id == mac.id)
            .first()
        )
        if not any_location:
            logger.warning(f"No location found for MAC {mac_address}")
            return None

        any_switch = self._get_switch(any_location.switch_id)
        if not any_switch:
            return None

        site_code = self._extract_site_code(any_switch.hostname)
        if not site_code:
            logger.warning(f"Cannot extract site code from {any_switch.hostname}")
            return None

        logger.info(f"Tracing MAC {mac_address} starting from site {site_code}")

        # Find Core switch for this site
        core_switch = self._find_core_switch_for_site(site_code)
        if not core_switch:
            logger.warning(f"No Core switch found for site {site_code}")
            # Fall back to old algorithm
            return self.trace_endpoint(mac_address)

        logger.info(f"Core switch for site {site_code}: {core_switch.hostname} ({core_switch.ip_address})")

        # Find MAC location on Core
        core_location = (
            self.db.query(MacLocation)
            .join(Port)
            .filter(
                MacLocation.mac_id == mac.id,
                MacLocation.switch_id == core_switch.id
            )
            .first()
        )

        if not core_location:
            logger.info(f"MAC not found on Core {core_switch.hostname} in DB - Core may need discovery")
            # Fall back to old algorithm
            return self.trace_endpoint(mac_address)

        core_port = self._get_port(core_location.port_id)
        if not core_port:
            return None

        logger.info(f"MAC {mac_address} on Core {core_switch.hostname} port {core_port.port_name}")

        # Start tracing from Core
        visited: Set[int] = set()
        trace_path: List[str] = []

        return self._trace_downstream(
            mac_id=mac.id,
            mac_address=mac_address,
            current_switch=core_switch,
            current_port_name=core_port.port_name,
            vlan_id=core_location.vlan_id,
            visited=visited,
            trace_path=trace_path
        )

    def _trace_downstream(
        self,
        mac_id: int,
        mac_address: str,
        current_switch: Switch,
        current_port_name: str,
        vlan_id: Optional[int],
        visited: Set[int],
        trace_path: List[str]
    ) -> Optional[EndpointInfo]:
        """
        Recursively trace downstream from current switch/port until finding endpoint.

        An endpoint is a port with:
        1. No LLDP neighbor to a managed switch, OR
        2. LLDP neighbor that doesn't see this MAC (unmanaged device behind)
        """
        if current_switch.id in visited:
            logger.warning(f"Loop detected at {current_switch.hostname}, stopping")
            return None
        visited.add(current_switch.id)

        trace_path = trace_path + [f"{current_switch.hostname}:{current_port_name}"]
        logger.info(f"Tracing: {' -> '.join(trace_path)}")

        port_name_lower = current_port_name.lower()

        # Case 1: Eth-Trunk - need to resolve members and follow LLDP
        if 'trunk' in port_name_lower or 'eth-trunk' in port_name_lower:
            logger.info(f"Port {current_port_name} is a trunk, resolving members...")

            # Get trunk members
            members = self._get_eth_trunk_members(current_switch, current_port_name)

            if not members:
                # Try to find any LLDP neighbor from this switch to L2 switch in same site
                site_code = self._extract_site_code(current_switch.hostname)
                all_links = (
                    self.db.query(TopologyLink)
                    .filter(TopologyLink.local_switch_id == current_switch.id)
                    .all()
                )

                for link in all_links:
                    remote_switch = self._get_switch(link.remote_switch_id)
                    if remote_switch and site_code:
                        remote_site = self._extract_site_code(remote_switch.hostname)
                        if remote_site == site_code and 'L2' in remote_switch.hostname:
                            # Found L2 switch in same site - check if it has the MAC
                            mac_on_remote = (
                                self.db.query(MacLocation)
                                .filter(
                                    MacLocation.mac_id == mac_id,
                                    MacLocation.switch_id == remote_switch.id
                                )
                                .first()
                            )
                            if mac_on_remote:
                                remote_port = self._get_port(mac_on_remote.port_id)
                                if remote_port:
                                    logger.info(f"Following to {remote_switch.hostname}:{remote_port.port_name}")
                                    return self._trace_downstream(
                                        mac_id, mac_address, remote_switch,
                                        remote_port.port_name, mac_on_remote.vlan_id,
                                        visited, trace_path
                                    )

                logger.warning(f"Cannot resolve trunk {current_port_name} members")
                return EndpointInfo(
                    mac_address=mac_address,
                    switch_id=current_switch.id,
                    switch_hostname=current_switch.hostname,
                    switch_ip=current_switch.ip_address,
                    port_id=0,
                    port_name=current_port_name,
                    vlan_id=vlan_id,
                    is_endpoint=False,
                    trace_path=trace_path + [f"UNRESOLVED: Cannot follow trunk {current_port_name}"]
                )

            # Follow first trunk member with LLDP neighbor
            for member_port in members:
                neighbor = self._get_lldp_neighbor_for_port_name(current_switch.id, member_port)
                if neighbor:
                    remote_switch, remote_port_name = neighbor
                    logger.info(f"Trunk member {member_port} -> {remote_switch.hostname}:{remote_port_name}")

                    # Find MAC on remote switch
                    mac_on_remote = (
                        self.db.query(MacLocation)
                        .filter(
                            MacLocation.mac_id == mac_id,
                            MacLocation.switch_id == remote_switch.id
                        )
                        .first()
                    )

                    if mac_on_remote:
                        remote_port = self._get_port(mac_on_remote.port_id)
                        if remote_port:
                            return self._trace_downstream(
                                mac_id, mac_address, remote_switch,
                                remote_port.port_name, mac_on_remote.vlan_id,
                                visited, trace_path
                            )

            logger.warning(f"No trunk member LLDP leads to MAC")
            return None

        # Case 2: Regular port - check LLDP neighbor
        neighbor = self._get_lldp_neighbor_for_port_name(current_switch.id, current_port_name)

        if neighbor is None:
            # No LLDP neighbor = ENDPOINT FOUND!
            logger.info(f"ENDPOINT FOUND: {current_switch.hostname}:{current_port_name} (no LLDP)")

            # Find port ID
            port = (
                self.db.query(Port)
                .filter(
                    Port.switch_id == current_switch.id,
                    Port.port_name == current_port_name
                )
                .first()
            )

            return EndpointInfo(
                mac_address=mac_address,
                switch_id=current_switch.id,
                switch_hostname=current_switch.hostname,
                switch_ip=current_switch.ip_address,
                port_id=port.id if port else 0,
                port_name=current_port_name,
                vlan_id=vlan_id,
                is_endpoint=True,
                trace_path=trace_path
            )

        # Has LLDP neighbor - check if neighbor sees the MAC
        remote_switch, remote_port_name = neighbor

        mac_on_remote = (
            self.db.query(MacLocation)
            .filter(
                MacLocation.mac_id == mac_id,
                MacLocation.switch_id == remote_switch.id
            )
            .first()
        )

        if mac_on_remote is None:
            # Neighbor doesn't see MAC = we are the endpoint (MAC is behind unmanaged device)
            logger.info(f"ENDPOINT FOUND: {current_switch.hostname}:{current_port_name} "
                       f"(neighbor {remote_switch.hostname} doesn't see MAC)")

            port = (
                self.db.query(Port)
                .filter(
                    Port.switch_id == current_switch.id,
                    Port.port_name == current_port_name
                )
                .first()
            )

            return EndpointInfo(
                mac_address=mac_address,
                switch_id=current_switch.id,
                switch_hostname=current_switch.hostname,
                switch_ip=current_switch.ip_address,
                port_id=port.id if port else 0,
                port_name=current_port_name,
                vlan_id=vlan_id,
                lldp_device_name=remote_switch.hostname,
                is_endpoint=True,
                trace_path=trace_path + [f"(neighbor {remote_switch.hostname} doesn't see MAC)"]
            )

        # Neighbor also sees MAC - continue downstream
        remote_port = self._get_port(mac_on_remote.port_id)
        if remote_port:
            logger.info(f"Following to {remote_switch.hostname}:{remote_port.port_name}")
            return self._trace_downstream(
                mac_id, mac_address, remote_switch,
                remote_port.port_name, mac_on_remote.vlan_id,
                visited, trace_path
            )

        return None

    def _extract_port_number(self, port_name: str) -> Optional[int]:
        """Extract the main port number for comparison.

        Examples:
        - XGigabitEthernet1/0/44 -> 44
        - XGE1/0/44 -> 44
        - GigabitEthernet0/0/9 -> 9
        - GE0/0/9 -> 9
        - Port144 -> 144
        - Eth-Trunk1 -> None (special case)
        """
        import re
        name = port_name.lower()

        # Skip Eth-Trunk ports - they are always uplinks
        if 'trunk' in name:
            return None

        # Try to extract last number from slot/port format (1/0/44 -> 44)
        match = re.search(r'/(\d+)$', port_name)
        if match:
            return int(match.group(1))

        # Try to extract number from PortNNN format
        match = re.search(r'port(\d+)$', name)
        if match:
            return int(match.group(1))

        return None

    def _normalize_port_name(self, port_name: str) -> str:
        """Normalize port name for comparison.

        Examples:
        - XGigabitEthernet1/0/44 -> 1/0/44
        - XGE1/0/44 -> 1/0/44
        - GigabitEthernet0/0/9 -> 0/0/9
        - GE0/0/9 -> 0/0/9
        - Port144 -> port144
        - Eth-Trunk1 -> eth-trunk1
        """
        name = port_name.lower()
        # Remove common prefixes
        prefixes = ['xgigabitethernet', 'gigabitethernet', 'xge', 'ge', 'port']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        return name.strip()

    def _get_equivalent_port_ids(self, switch_id: int, port_id: int) -> List[int]:
        """Get all port IDs that might be the same physical port.

        Due to different naming conventions, the same physical port might have
        multiple entries: XGigabitEthernet1/0/44, XGE1/0/44, Port104, etc.

        Strategy:
        1. Match by normalized name (1/0/44 == 1/0/44)
        2. Match by port number (XGE1/0/44 matches Port144 via slot 1 + port 44 = 144)
        """
        port = self._get_port(port_id)
        if not port:
            return [port_id]

        normalized = self._normalize_port_name(port.port_name)
        port_num = self._extract_port_number(port.port_name)

        cache_key = (switch_id, normalized)

        if cache_key not in self._port_name_to_ids:
            # Find all ports on this switch with similar names
            all_ports = (
                self.db.query(Port)
                .filter(Port.switch_id == switch_id)
                .all()
            )
            equivalent_ids = set()
            equivalent_ids.add(port_id)

            for p in all_ports:
                # Match by normalized name
                if self._normalize_port_name(p.port_name) == normalized:
                    equivalent_ids.add(p.id)

                # Match by port number (for XGE/GE ports)
                if port_num is not None:
                    p_num = self._extract_port_number(p.port_name)
                    if p_num == port_num:
                        equivalent_ids.add(p.id)

                    # Special case: XGE1/0/44 might match Port144 (slot*100 + port)
                    # or Port104 (ifIndex mapping)
                    if p.port_name.lower().startswith('port'):
                        try:
                            port_idx = int(p.port_name[4:])
                            # Check if this could be slot*100+port or direct match
                            if port_idx == port_num or port_idx == (100 + port_num) or port_idx == (200 + port_num):
                                equivalent_ids.add(p.id)
                        except ValueError:
                            pass

            self._port_name_to_ids[cache_key] = list(equivalent_ids)

        return self._port_name_to_ids[cache_key]

    def _get_switch(self, switch_id: int) -> Optional[Switch]:
        """Get switch by ID with caching."""
        if switch_id not in self._switch_cache:
            self._switch_cache[switch_id] = (
                self.db.query(Switch).filter(Switch.id == switch_id).first()
            )
        return self._switch_cache[switch_id]

    def _get_port(self, port_id: int) -> Optional[Port]:
        """Get port by ID with caching."""
        if port_id not in self._port_cache:
            self._port_cache[port_id] = (
                self.db.query(Port).filter(Port.id == port_id).first()
            )
        return self._port_cache[port_id]

    def _get_lldp_neighbor(self, switch_id: int, port_id: int) -> Optional[TopologyLink]:
        """Check if a port has an LLDP neighbor (is an uplink to another switch).

        Checks both directions and considers equivalent port names:
        1. This port as local_port (we see neighbor)
        2. This port as remote_port (neighbor sees us)
        3. Equivalent ports (same physical port with different names)
        """
        cache_key = (switch_id, port_id)
        if cache_key not in self._topology_cache:
            # Get all equivalent port IDs (same physical port, different names)
            equivalent_port_ids = self._get_equivalent_port_ids(switch_id, port_id)

            link = None
            for pid in equivalent_port_ids:
                # Check if this port is the local side of a link
                link = (
                    self.db.query(TopologyLink)
                    .filter(
                        TopologyLink.local_switch_id == switch_id,
                        TopologyLink.local_port_id == pid
                    )
                    .first()
                )
                if link:
                    break

                # Check if this port is the remote side of a link
                link = (
                    self.db.query(TopologyLink)
                    .filter(
                        TopologyLink.remote_switch_id == switch_id,
                        TopologyLink.remote_port_id == pid
                    )
                    .first()
                )
                if link:
                    break

            self._topology_cache[cache_key] = link
        return self._topology_cache[cache_key]

    def _get_downstream_switches_from_trunk(self, switch_id: int, trunk_port_name: str) -> List[Tuple[int, str]]:
        """Find switches connected via an Eth-Trunk interface.

        Since Eth-Trunk is a LAG (Link Aggregation), we need to:
        1. Find all LLDP links from this switch
        2. Match those that might be part of this trunk

        Returns list of (remote_switch_id, remote_port_name) tuples.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Get all topology links FROM this switch
        links = (
            self.db.query(TopologyLink)
            .filter(TopologyLink.local_switch_id == switch_id)
            .all()
        )

        downstream = []
        for link in links:
            local_port = self._get_port(link.local_port_id)
            remote_port = self._get_port(link.remote_port_id) if link.remote_port_id else None

            if local_port:
                local_port_lower = local_port.port_name.lower()
                # Check if this link's local port is the trunk or a member of the trunk
                # Eth-Trunk members are typically XGE/10GE ports
                if trunk_port_name.lower() in local_port_lower or 'trunk' in local_port_lower:
                    remote_switch = self._get_switch(link.remote_switch_id)
                    if remote_switch:
                        downstream.append((
                            link.remote_switch_id,
                            remote_port.port_name if remote_port else "unknown"
                        ))
                        logger.debug(f"Trunk {trunk_port_name} links to {remote_switch.hostname}")

        # If no direct trunk match, try to find links to L2 switches in same site
        if not downstream:
            switch = self._get_switch(switch_id)
            if switch:
                # Get site code from hostname (e.g., 21_L3-CORE_251 -> 21)
                import re
                match = re.match(r'^(\d+)_', switch.hostname)
                if match:
                    site_code = match.group(1)
                    for link in links:
                        remote_switch = self._get_switch(link.remote_switch_id)
                        if remote_switch and remote_switch.hostname.startswith(f"{site_code}_L2"):
                            remote_port = self._get_port(link.remote_port_id) if link.remote_port_id else None
                            downstream.append((
                                link.remote_switch_id,
                                remote_port.port_name if remote_port else "unknown"
                            ))

        logger.info(f"Trunk {trunk_port_name} on switch {switch_id}: found {len(downstream)} downstream switches")
        return downstream

    def _trace_mac_through_trunk(
        self,
        mac_address: str,
        mac_id: int,
        start_switch_id: int,
        trunk_port_name: str,
        visited: set,
        trace_path: List[str]
    ) -> Optional[EndpointInfo]:
        """Trace a MAC address through an Eth-Trunk to find the real endpoint.

        This is called when we find a MAC on a trunk port. We need to:
        1. Find downstream switches connected via this trunk
        2. Check if any of them see this MAC
        3. Recursively trace until we find a non-trunk endpoint
        """
        import logging
        logger = logging.getLogger(__name__)

        if start_switch_id in visited:
            logger.debug(f"Already visited switch {start_switch_id}, stopping loop")
            return None
        visited.add(start_switch_id)

        start_switch = self._get_switch(start_switch_id)
        if not start_switch:
            return None

        trace_path = trace_path + [f"{start_switch.hostname}:{trunk_port_name} (trunk)"]
        logger.info(f"Tracing MAC {mac_address} through trunk {trunk_port_name} on {start_switch.hostname}")

        # Find downstream switches
        downstream = self._get_downstream_switches_from_trunk(start_switch_id, trunk_port_name)

        if not downstream:
            logger.warning(f"No downstream switches found for trunk {trunk_port_name}")
            return None

        # Check each downstream switch for this MAC
        for remote_switch_id, remote_port_name in downstream:
            remote_switch = self._get_switch(remote_switch_id)
            if not remote_switch:
                continue

            # Find MAC location on this switch
            mac_locations = (
                self.db.query(MacLocation)
                .filter(
                    MacLocation.mac_id == mac_id,
                    MacLocation.switch_id == remote_switch_id
                )
                .all()
            )

            if not mac_locations:
                logger.debug(f"MAC not found on {remote_switch.hostname}")
                continue

            logger.info(f"MAC {mac_address} found on {remote_switch.hostname}")

            # Check each location on this switch
            for loc in mac_locations:
                port = self._get_port(loc.port_id)
                if not port:
                    continue

                port_name_lower = port.port_name.lower()

                # If it's another trunk, recurse
                if 'trunk' in port_name_lower or 'eth-trunk' in port_name_lower:
                    result = self._trace_mac_through_trunk(
                        mac_address, mac_id, remote_switch_id,
                        port.port_name, visited, trace_path
                    )
                    if result:
                        return result
                else:
                    # Check if this is an endpoint (no LLDP neighbor, low MAC count)
                    lldp_link = self._get_lldp_neighbor(remote_switch_id, port.id)
                    mac_count = self._get_mac_count_on_port(remote_switch_id, port.id)

                    if lldp_link is None and mac_count <= self.UPLINK_MAC_THRESHOLD:
                        # Found the endpoint!
                        logger.info(f"Endpoint found: {remote_switch.hostname}:{port.port_name}")
                        return EndpointInfo(
                            mac_address=mac_address,
                            switch_id=remote_switch_id,
                            switch_hostname=remote_switch.hostname,
                            switch_ip=remote_switch.ip_address,
                            port_id=port.id,
                            port_name=port.port_name,
                            vlan_id=loc.vlan_id,
                            lldp_device_name=None,
                            is_endpoint=True,
                            trace_path=trace_path + [f"{remote_switch.hostname}:{port.port_name}"]
                        )
                    elif lldp_link:
                        # This port has LLDP neighbor, follow the chain
                        next_switch_id = lldp_link.remote_switch_id
                        if next_switch_id not in visited:
                            result = self._trace_mac_through_trunk(
                                mac_address, mac_id, next_switch_id,
                                port.port_name, visited, trace_path + [f"{remote_switch.hostname}:{port.port_name}"]
                            )
                            if result:
                                return result

        return None

    def _get_mac_on_switch(self, mac_id: int, switch_id: int) -> Optional[MacLocation]:
        """Get the MAC location on a specific switch."""
        return (
            self.db.query(MacLocation)
            .filter(
                MacLocation.mac_id == mac_id,
                MacLocation.switch_id == switch_id,
                MacLocation.is_current == True
            )
            .first()
        )

    def _get_mac_count_on_port(self, switch_id: int, port_id: int) -> int:
        """Get the count of UNIQUE MAC addresses ever seen on a specific port.

        IP FABRIC KEY INSIGHT:
        - Count ALL unique MACs ever seen, not just is_current=True!
        - Uplink ports see MANY different MACs over time (all devices behind)
        - Endpoint ports see only a FEW MACs (the device + maybe virtual MACs)

        This is the most reliable indicator for uplink detection.
        """
        from sqlalchemy import func

        cache_key = (switch_id, port_id)
        if cache_key not in self._port_mac_count_cache:
            # Count UNIQUE MACs ever seen on this port (ignore is_current!)
            count = (
                self.db.query(func.count(func.distinct(MacLocation.mac_id)))
                .filter(
                    MacLocation.switch_id == switch_id,
                    MacLocation.port_id == port_id
                )
                .scalar()
            )
            self._port_mac_count_cache[cache_key] = count or 0
        return self._port_mac_count_cache[cache_key]

    def _is_likely_uplink(self, switch_id: int, port_id: int) -> bool:
        """Determine if a port is likely an uplink based on multiple factors.

        A port is likely an uplink if:
        1. It has an LLDP neighbor that is a managed switch, OR
        2. It has many MAC addresses (above threshold)
        """
        # Check MAC count first (faster)
        mac_count = self._get_mac_count_on_port(switch_id, port_id)
        if mac_count > self.UPLINK_MAC_THRESHOLD:
            return True

        # Check LLDP neighbor
        lldp_link = self._get_lldp_neighbor(switch_id, port_id)
        if lldp_link:
            # Check if neighbor is a managed switch
            remote_switch = self._get_switch(lldp_link.remote_switch_id)
            if remote_switch:
                return True

        return False

    def trace_endpoint(self, mac_address: str) -> Optional[EndpointInfo]:
        """
        Trace a MAC address to its physical endpoint using IP Fabric methodology.

        IP Fabric Strategy:
        1. Get ALL locations where this MAC has EVER been seen (ignore is_current!)
        2. Group by unique (switch_id, port_id) pairs
        3. Score each location based on endpoint likelihood:
           - Trunk port = DISQUALIFIED (always uplink)
           - Port with LLDP neighbor = likely uplink
           - Port with many MACs = likely uplink
           - Port with few MACs + no LLDP = likely ENDPOINT
        4. Return the location with highest endpoint score

        Returns the endpoint info with the actual switch/port where the device
        is directly connected, not an uplink port.
        """
        from datetime import datetime, timedelta
        from sqlalchemy import func

        # Find the MAC in database
        mac = (
            self.db.query(MacAddress)
            .filter(MacAddress.mac_address == mac_address)
            .first()
        )
        if not mac:
            return None

        # IP FABRIC KEY INSIGHT: Get ALL locations, not just is_current=True!
        # Group by switch+port to get unique locations, use most recent seen_at
        all_locations = (
            self.db.query(
                MacLocation.switch_id,
                MacLocation.port_id,
                func.max(MacLocation.vlan_id).label('vlan_id'),
                func.max(MacLocation.seen_at).label('last_seen')
            )
            .filter(MacLocation.mac_id == mac.id)
            .group_by(MacLocation.switch_id, MacLocation.port_id)
            .all()
        )

        if not all_locations:
            return None

        # Build list with switch and port objects
        locations = []
        for loc in all_locations:
            switch = self._get_switch(loc.switch_id)
            port = self._get_port(loc.port_id)
            if switch and port:
                locations.append({
                    'switch_id': loc.switch_id,
                    'port_id': loc.port_id,
                    'vlan_id': loc.vlan_id,
                    'last_seen': loc.last_seen,
                    'switch': switch,
                    'port': port
                })

        if not locations:
            return None

        # Build set of switches that see this MAC (for LLDP neighbor check)
        switches_with_mac = {loc['switch_id'] for loc in locations}

        # Score each location for endpoint likelihood
        scored_locations = []
        trace_info = []

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"MAC {mac_address} - analyzing {len(locations)} unique locations")

        for loc in locations:
            switch = loc['switch']
            port = loc['port']
            score = 0
            reasons = []

            # Factor 0: DISQUALIFY trunk ports immediately
            port_name_lower = port.port_name.lower()
            if 'trunk' in port_name_lower or 'eth-trunk' in port_name_lower:
                score = -1000  # Trunk ports are ALWAYS uplinks
                reasons.append("TRUNK_DISQUALIFIED")
                scored_locations.append({
                    'loc': loc,
                    'switch': switch,
                    'port': port,
                    'score': score,
                    'reasons': reasons,
                    'mac_count': 0
                })
                continue

            # Factor 1: LLDP neighbor check (most important!)
            lldp_link = self._get_lldp_neighbor(switch.id, port.id)
            if lldp_link is None:
                score += 100  # No LLDP = very likely endpoint!
                reasons.append("NO_LLDP_NEIGHBOR")
            else:
                remote_switch_id = lldp_link.remote_switch_id
                remote_switch = self._get_switch(remote_switch_id)
                if remote_switch:
                    if remote_switch_id not in switches_with_mac:
                        # Neighbor doesn't see MAC = we are the endpoint
                        score += 80
                        reasons.append(f"neighbor_no_mac:{remote_switch.hostname}")
                    else:
                        # Neighbor also sees MAC = we are uplink
                        score -= 50
                        reasons.append(f"UPLINK_neighbor_has_mac:{remote_switch.hostname}")
                    trace_info.append(f"{switch.hostname}:{port.port_name} -> {remote_switch.hostname}")

            # Factor 2: MAC count on port (CRITICAL for uplink detection!)
            mac_count = self._get_mac_count_on_port(switch.id, port.id)
            if mac_count > 50:
                # DISQUALIFY: >50 MACs is DEFINITELY an uplink, no matter what
                score = -800
                reasons.append(f"UPLINK_DISQUALIFIED_mac_count:{mac_count}")
            elif mac_count > 20:
                # Very likely uplink - heavy penalty
                score -= 150
                reasons.append(f"likely_uplink_mac_count:{mac_count}")
            elif mac_count > self.UPLINK_MAC_THRESHOLD:
                score -= 50  # Many MACs = likely uplink
                reasons.append(f"high_mac_count:{mac_count}")
            elif mac_count <= 3:
                score += 50  # Low MAC count = likely endpoint
                reasons.append(f"low_mac_count:{mac_count}")
            else:
                score += 20
                reasons.append(f"moderate_mac_count:{mac_count}")

            # Factor 3: Switch type (minor factor)
            if 'L3' in switch.hostname or 'Core' in switch.hostname:
                score -= 10
                reasons.append("core_switch")
            elif 'L2' in switch.hostname:
                score += 10
                reasons.append("access_switch")

            scored_locations.append({
                'loc': loc,
                'switch': switch,
                'port': port,
                'score': score,
                'reasons': reasons,
                'mac_count': mac_count
            })

        # Sort by score (highest first)
        scored_locations.sort(key=lambda x: x['score'], reverse=True)

        # Log scoring for debugging
        logger.info(f"MAC {mac_address} endpoint scoring results:")
        for sl in scored_locations[:5]:  # Top 5
            logger.info(f"  {sl['switch'].hostname}:{sl['port'].port_name} "
                       f"score={sl['score']} mac_count={sl['mac_count']} "
                       f"reasons={sl['reasons']}")

        # Return the best scored location if it's a valid endpoint
        if scored_locations and scored_locations[0]['score'] > -500:
            best = scored_locations[0]
            return EndpointInfo(
                mac_address=mac_address,
                switch_id=best['switch'].id,
                switch_hostname=best['switch'].hostname,
                switch_ip=best['switch'].ip_address,
                port_id=best['port'].id,
                port_name=best['port'].port_name,
                vlan_id=best['loc']['vlan_id'],
                lldp_device_name=None,
                is_endpoint=best['score'] > 50,
                trace_path=trace_info
            )

        # ALL locations are uplinks/trunks (score <= -500)
        # This could mean:
        # 1. MAC is behind unmanaged device (AP, mini-switch) on an access switch
        # 2. MAC is on another switch but the Core/upstream wasn't fully discovered
        #
        # Strategy:
        # - If the port connects to a managed switch (has LLDP to another switch in DB),
        #   we can't determine endpoint - need to discover the neighbor
        # - If the port has "neighbor_no_mac", the neighbor doesn't see the MAC = we are deepest
        logger.info(f"MAC {mac_address} only seen on uplink/trunk ports, analyzing...")

        # Check if any location has a neighbor that DOES NOT see the MAC
        # This would indicate the device is behind that port
        deepest_locations = []
        uncertain_locations = []

        for sl in scored_locations:
            has_neighbor_no_mac = any('neighbor_no_mac' in r for r in sl['reasons'])
            has_neighbor_with_mac = any('UPLINK_neighbor_has_mac' in r for r in sl['reasons'])

            if has_neighbor_no_mac and not has_neighbor_with_mac:
                # This switch's neighbor doesn't see the MAC - we are deepest
                deepest_locations.append(sl)
            else:
                # The neighbor also sees the MAC, or we're not sure
                uncertain_locations.append(sl)

        # If we have locations where neighbor doesn't see MAC IN DATABASE, use those
        # BUT: the neighbor might have the MAC and we just didn't discover it!
        # So mark this as UNCERTAIN unless it's clearly an unmanaged device
        if deepest_locations:
            # Sort by: L2 switches preferred, lower MAC count
            deepest_locations.sort(key=lambda x: (
                0 if 'access_switch' in x['reasons'] else 1,
                x['mac_count']
            ))
            best = deepest_locations[0]

            # Check if the neighbor is a Core/L3 switch (which may not have been fully discovered)
            neighbor_name = None
            for r in best['reasons']:
                if 'neighbor_no_mac:' in r:
                    neighbor_name = r.split(':')[1]
                    break

            # If neighbor is L3/Core, mark as UNCERTAIN (Core discovery might be incomplete)
            if neighbor_name and ('L3' in neighbor_name or 'Core' in neighbor_name.upper()):
                logger.warning(f"MAC {mac_address} seen on uplink to Core switch {neighbor_name}. "
                              f"Core switch may need discovery.")
                return EndpointInfo(
                    mac_address=mac_address,
                    switch_id=best['switch'].id,
                    switch_hostname=best['switch'].hostname,
                    switch_ip=best['switch'].ip_address,
                    port_id=best['port'].id,
                    port_name=best['port'].port_name,
                    vlan_id=best['loc']['vlan_id'],
                    lldp_device_name=None,
                    is_endpoint=False,
                    trace_path=trace_info + [f"UNCERTAIN: MAC seen on uplink to {neighbor_name} - Core switch needs MAC discovery"]
                )
            else:
                # Neighbor is L2/access - likely behind unmanaged device
                logger.info(f"Deepest location found: {best['switch'].hostname}:{best['port'].port_name} "
                           f"(neighbor doesn't see MAC - device is behind this port)")
                return EndpointInfo(
                    mac_address=mac_address,
                    switch_id=best['switch'].id,
                    switch_hostname=best['switch'].hostname,
                    switch_ip=best['switch'].ip_address,
                    port_id=best['port'].id,
                    port_name=best['port'].port_name,
                    vlan_id=best['loc']['vlan_id'],
                    lldp_device_name=None,
                    is_endpoint=False,  # Behind unmanaged device
                    trace_path=trace_info + [f"Behind unmanaged device on {best['switch'].hostname}:{best['port'].port_name}"]
                )

        # All locations have neighbors that also see the MAC (or no data)
        # This means the MAC is likely on another switch that wasn't fully discovered
        if uncertain_locations:
            # Return the location but mark as uncertain
            best = uncertain_locations[0]
            logger.warning(f"MAC {mac_address} endpoint uncertain: only seen on uplink ports. "
                          f"Neighbor switches may need discovery. Best guess: {best['switch'].hostname}:{best['port'].port_name}")
            return EndpointInfo(
                mac_address=mac_address,
                switch_id=best['switch'].id,
                switch_hostname=best['switch'].hostname,
                switch_ip=best['switch'].ip_address,
                port_id=best['port'].id,
                port_name=best['port'].port_name,
                vlan_id=best['loc']['vlan_id'],
                lldp_device_name=None,
                is_endpoint=False,  # NOT the real endpoint
                trace_path=trace_info + [f"UNCERTAIN: MAC arrives via uplink {best['switch'].hostname}:{best['port'].port_name} - neighbor switch needs discovery"]
            )

        return None

    def _check_historical_endpoint(
        self, mac_id: int, current_scored: List[Dict]
    ) -> Optional[EndpointInfo]:
        """
        Check historical locations for a better endpoint when current scoring is ambiguous.

        This handles cases where:
        1. Discovery missed the true endpoint switch (SNMP timeout, etc.)
        2. The MAC was recently seen on a better endpoint port

        Returns an EndpointInfo if a better historical endpoint is found.
        """
        from datetime import datetime, timedelta
        import logging
        logger = logging.getLogger(__name__)

        # Only look at recent history (last 24 hours)
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)

        # Get historical locations not in current set
        current_switch_port_pairs = {
            (sl['switch'].id, sl['port'].id) for sl in current_scored
        }

        historical_locations = (
            self.db.query(MacLocation, Switch, Port)
            .join(Switch, MacLocation.switch_id == Switch.id)
            .join(Port, MacLocation.port_id == Port.id)
            .filter(
                MacLocation.mac_id == mac_id,
                MacLocation.seen_at >= recent_cutoff,
                MacLocation.is_current == False  # Only historical
            )
            .order_by(MacLocation.seen_at.desc())
            .all()
        )

        for loc, switch, port in historical_locations:
            # Skip if already in current set
            if (switch.id, port.id) in current_switch_port_pairs:
                continue

            # Score this historical location
            mac_count = self._get_mac_count_on_port(switch.id, port.id)
            lldp_link = self._get_lldp_neighbor(switch.id, port.id)

            # Only consider if it looks like a real endpoint:
            # 1. Low MAC count on port (<= 3)
            # 2. No LLDP neighbor (edge port)
            if mac_count <= 3 and lldp_link is None:
                logger.info(
                    f"Found better historical endpoint: {switch.hostname}:{port.port_name} "
                    f"(mac_count={mac_count}, no_lldp, seen_at={loc.seen_at})"
                )
                return EndpointInfo(
                    mac_address="",  # Will be filled by caller
                    switch_id=switch.id,
                    switch_hostname=switch.hostname,
                    switch_ip=switch.ip_address,
                    port_id=port.id,
                    port_name=port.port_name,
                    vlan_id=loc.vlan_id,
                    lldp_device_name=None,
                    is_endpoint=True,
                    trace_path=[f"{switch.hostname}:{port.port_name} (historical)"]
                )

        return None

    def _follow_chain_to_endpoint(
        self,
        mac_id: int,
        current_switch_id: int,
        current_port_id: int,
        switches_with_mac: set,
        visited: set,
        trace_path: List[str]
    ) -> Optional[EndpointInfo]:
        """
        Follow LLDP links to find the deepest switch that sees this MAC.
        """
        if current_switch_id in visited:
            return None
        visited.add(current_switch_id)

        current_switch = self._get_switch(current_switch_id)
        current_port = self._get_port(current_port_id)

        if not current_switch or not current_port:
            return None

        lldp_link = self._get_lldp_neighbor(current_switch_id, current_port_id)

        if lldp_link is None:
            # No LLDP = endpoint found
            loc = self._get_mac_on_switch(mac_id, current_switch_id)
            return EndpointInfo(
                mac_address="",
                switch_id=current_switch_id,
                switch_hostname=current_switch.hostname,
                switch_ip=current_switch.ip_address,
                port_id=current_port_id,
                port_name=current_port.port_name,
                vlan_id=loc.vlan_id if loc else None,
                lldp_device_name=None,
                is_endpoint=True,
                trace_path=trace_path + [f"{current_switch.hostname}:{current_port.port_name}"]
            )

        remote_switch_id = lldp_link.remote_switch_id
        remote_switch = self._get_switch(remote_switch_id)

        if not remote_switch or remote_switch_id not in switches_with_mac:
            # Neighbor doesn't see the MAC - we are the endpoint
            loc = self._get_mac_on_switch(mac_id, current_switch_id)
            return EndpointInfo(
                mac_address="",
                switch_id=current_switch_id,
                switch_hostname=current_switch.hostname,
                switch_ip=current_switch.ip_address,
                port_id=current_port_id,
                port_name=current_port.port_name,
                vlan_id=loc.vlan_id if loc else None,
                lldp_device_name=remote_switch.hostname if remote_switch else None,
                is_endpoint=True,
                trace_path=trace_path + [f"{current_switch.hostname}:{current_port.port_name}"]
            )

        # Follow to remote switch
        trace_path = trace_path + [f"{current_switch.hostname}:{current_port.port_name} -> {remote_switch.hostname}"]

        # Find MAC location on remote switch
        mac_loc_on_remote = self._get_mac_on_switch(mac_id, remote_switch_id)
        if not mac_loc_on_remote:
            return None

        return self._follow_chain_to_endpoint(
            mac_id,
            remote_switch_id,
            mac_loc_on_remote.port_id,
            switches_with_mac,
            visited,
            trace_path
        )


    def get_all_endpoints_for_mac(self, mac_address: str) -> List[EndpointInfo]:
        """
        Get all endpoint locations for a MAC (in case it's on multiple VLANs/ports).

        Filters out uplink ports and returns only actual endpoints.
        """
        mac = (
            self.db.query(MacAddress)
            .filter(MacAddress.mac_address == mac_address)
            .first()
        )
        if not mac:
            return []

        # Get all current locations
        locations = (
            self.db.query(MacLocation, Switch, Port)
            .join(Switch, MacLocation.switch_id == Switch.id)
            .join(Port, MacLocation.port_id == Port.id)
            .filter(
                MacLocation.mac_id == mac.id,
                MacLocation.is_current == True
            )
            .all()
        )

        endpoints = []
        seen_endpoints = set()  # Avoid duplicates

        for loc, switch, port in locations:
            # Check if this port has LLDP neighbor
            lldp_link = self._get_lldp_neighbor(switch.id, port.id)

            if lldp_link is None:
                # This is an endpoint port
                endpoint_key = (switch.id, port.id)
                if endpoint_key not in seen_endpoints:
                    seen_endpoints.add(endpoint_key)
                    endpoints.append(EndpointInfo(
                        mac_address=mac_address,
                        switch_id=switch.id,
                        switch_hostname=switch.hostname,
                        switch_ip=switch.ip_address,
                        port_id=port.id,
                        port_name=port.port_name,
                        vlan_id=loc.vlan_id,
                        lldp_device_name=None,
                        is_endpoint=True,
                        trace_path=[f"{switch.hostname}:{port.port_name}"]
                    ))

        # If no direct endpoints found, try tracing
        if not endpoints:
            traced = self.trace_endpoint(mac_address)
            if traced:
                endpoints.append(traced)

        return endpoints
