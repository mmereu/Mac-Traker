"""LLDP Discovery Service for topology mapping."""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.db.models import Switch, Port, TopologyLink
from app.utils.port_utils import normalize_port_name

logger = logging.getLogger(__name__)

# LLDP MIB OIDs
LLDP_MIB = {
    "lldpRemTable": "1.0.8802.1.1.2.1.4.1.1",
    "lldpRemChassisId": "1.0.8802.1.1.2.1.4.1.1.5",  # Remote chassis ID (MAC)
    "lldpRemPortId": "1.0.8802.1.1.2.1.4.1.1.7",     # Remote port ID
    "lldpRemPortDesc": "1.0.8802.1.1.2.1.4.1.1.8",   # Remote port description
    "lldpRemSysName": "1.0.8802.1.1.2.1.4.1.1.9",    # Remote system name
    "lldpRemSysCapSupported": "1.0.8802.1.1.2.1.4.1.1.11",  # Remote system capabilities supported
    "lldpRemSysCapEnabled": "1.0.8802.1.1.2.1.4.1.1.12",    # Remote system capabilities enabled
    "lldpRemManAddr": "1.0.8802.1.1.2.1.4.2.1.4",    # Remote management address
}

# LLDP System Capabilities bit positions (IEEE 802.1AB)
# Bit 0: Other
# Bit 1: Repeater
# Bit 2: Bridge (Switch)
# Bit 3: WLAN Access Point
# Bit 4: Router
# Bit 5: Telephone
# Bit 6: DOCSIS Cable Device
# Bit 7: Station Only
LLDP_CAP_OTHER = 0x01
LLDP_CAP_REPEATER = 0x02
LLDP_CAP_BRIDGE = 0x04      # Switch
LLDP_CAP_WLAN_AP = 0x08     # Access Point
LLDP_CAP_ROUTER = 0x10
LLDP_CAP_TELEPHONE = 0x20
LLDP_CAP_DOCSIS = 0x40
LLDP_CAP_STATION = 0x80

# Huawei LLDP MIB
HUAWEI_LLDP_MIB = {
    "hwLldpRemoteSystemData": "1.3.6.1.4.1.2011.5.25.134.1.1.1",
    "hwLldpRemSysName": "1.3.6.1.4.1.2011.5.25.134.1.1.1.1.6",
    "hwLldpRemPortId": "1.3.6.1.4.1.2011.5.25.134.1.1.1.1.4",
    "hwLldpRemManAddr": "1.3.6.1.4.1.2011.5.25.134.1.1.1.1.9",
}


class LLDPNeighbor:
    """Represents an LLDP neighbor discovered on a switch."""

    def __init__(
        self,
        local_port_name: str,
        local_port_index: int,
        remote_chassis_id: str,
        remote_port_id: str,
        remote_system_name: Optional[str] = None,
        remote_mgmt_address: Optional[str] = None,
        remote_port_desc: Optional[str] = None,
        remote_sys_cap_supported: int = 0,
        remote_sys_cap_enabled: int = 0,
    ):
        self.local_port_name = local_port_name
        self.local_port_index = local_port_index
        self.remote_chassis_id = remote_chassis_id
        self.remote_port_id = remote_port_id
        self.remote_system_name = remote_system_name
        self.remote_mgmt_address = remote_mgmt_address
        self.remote_port_desc = remote_port_desc
        self.remote_sys_cap_supported = remote_sys_cap_supported
        self.remote_sys_cap_enabled = remote_sys_cap_enabled

    @property
    def is_switch(self) -> bool:
        """Returns True if remote device is a switch/bridge."""
        return bool(self.remote_sys_cap_enabled & LLDP_CAP_BRIDGE)

    @property
    def is_access_point(self) -> bool:
        """Returns True if remote device is a WLAN Access Point."""
        return bool(self.remote_sys_cap_enabled & LLDP_CAP_WLAN_AP)

    @property
    def is_router(self) -> bool:
        """Returns True if remote device is a router."""
        return bool(self.remote_sys_cap_enabled & LLDP_CAP_ROUTER)

    @property
    def is_phone(self) -> bool:
        """Returns True if remote device is a telephone/IP phone."""
        return bool(self.remote_sys_cap_enabled & LLDP_CAP_TELEPHONE)

    @property
    def is_network_device(self) -> bool:
        """Returns True if remote device is a network device (switch, router, or AP that forwards traffic)."""
        # A switch or router is network infrastructure that forwards traffic
        # An AP is a special case: it has LLDP but MACs behind it are endpoints
        return self.is_switch or self.is_router

    @property
    def neighbor_type(self) -> str:
        """Returns human-readable neighbor type."""
        types = []
        if self.is_router:
            types.append("Router")
        if self.is_switch:
            types.append("Switch")
        if self.is_access_point:
            types.append("AP")
        if self.is_phone:
            types.append("Phone")
        return "/".join(types) if types else "Unknown"


class LLDPDiscoveryService:
    """Service for discovering network topology via LLDP."""

    def __init__(self, db: Session):
        self.db = db

    def _find_local_port(self, switch_id: int, port_index: int,
                          fallback_name: str = None) -> Optional[Port]:
        """Find a local port by ifIndex (port_index) first, then by name as fallback.

        LLDP provides lldpRemLocalPortNum which equals the ifIndex of the local port.
        SNMP MAC discovery creates ports with real ifDescr names and stores the same
        ifIndex as port_index. Using ifIndex for lookup ensures LLDP correctly matches
        ports regardless of name format differences (GE vs XGE, slot differences, etc.).
        """
        # Primary: lookup by port_index (ifIndex) - most reliable for cross-MIB matching
        if port_index and port_index > 0:
            port = self.db.query(Port).filter(
                Port.switch_id == switch_id,
                Port.port_index == port_index
            ).first()
            if port:
                return port

        # Fallback: lookup by normalized name
        if fallback_name:
            normalized = normalize_port_name(fallback_name)
            port = self.db.query(Port).filter(
                Port.switch_id == switch_id,
                Port.port_name == normalized
            ).first()
            if port:
                return port

        return None

    def _cleanup_duplicate_ports(self):
        """Clean up duplicate port records with same ifIndex on the same switch.

        Previous LLDP bug created ports with wrong names (e.g., GE0/0/4) while
        SNMP discovery created the correct port (e.g., GE1/0/4) with the same ifIndex.
        This merges duplicates by moving all references to the port with MAC locations.
        """
        from sqlalchemy import func
        from app.db.models import MacLocation, MacHistory

        # Find (switch_id, port_index) pairs that have >1 port record
        duplicates = self.db.query(
            Port.switch_id, Port.port_index, func.count(Port.id).label('cnt')
        ).filter(
            Port.port_index.isnot(None),
            Port.port_index > 0
        ).group_by(
            Port.switch_id, Port.port_index
        ).having(
            func.count(Port.id) > 1
        ).all()

        if not duplicates:
            return 0

        merged_count = 0
        for switch_id, port_index, cnt in duplicates:
            ports = self.db.query(Port).filter(
                Port.switch_id == switch_id,
                Port.port_index == port_index
            ).all()

            # Decide which port to KEEP:
            # 1. Prefer port with MacLocation references (it's the one SNMP uses)
            # 2. Then prefer port with LLDP neighbor info
            # 3. Then prefer the one with the longer/more specific name
            keep = ports[0]
            for p in ports[1:]:
                keep_locs = self.db.query(MacLocation).filter(
                    MacLocation.port_id == keep.id
                ).count()
                p_locs = self.db.query(MacLocation).filter(
                    MacLocation.port_id == p.id
                ).count()

                if p_locs > keep_locs:
                    keep = p
                elif p_locs == keep_locs and p.lldp_neighbor_name and not keep.lldp_neighbor_name:
                    keep = p

            # Merge all other ports into keep
            for p in ports:
                if p.id == keep.id:
                    continue

                # Transfer LLDP info if keep doesn't have it
                if p.lldp_neighbor_name and not keep.lldp_neighbor_name:
                    keep.lldp_neighbor_name = p.lldp_neighbor_name
                    keep.lldp_neighbor_type = p.lldp_neighbor_type
                    keep.is_uplink = p.is_uplink
                    keep.port_type = p.port_type

                # Move MacLocation references
                self.db.query(MacLocation).filter(
                    MacLocation.port_id == p.id
                ).update({MacLocation.port_id: keep.id})

                # Move MacHistory references (port_id and previous_port_id)
                self.db.query(MacHistory).filter(
                    MacHistory.port_id == p.id
                ).update({MacHistory.port_id: keep.id})
                self.db.query(MacHistory).filter(
                    MacHistory.previous_port_id == p.id
                ).update({MacHistory.previous_port_id: keep.id})

                # Move TopologyLink references
                self.db.query(TopologyLink).filter(
                    TopologyLink.local_port_id == p.id
                ).update({TopologyLink.local_port_id: keep.id})
                self.db.query(TopologyLink).filter(
                    TopologyLink.remote_port_id == p.id
                ).update({TopologyLink.remote_port_id: keep.id})

                logger.info(
                    f"Merging duplicate port '{p.port_name}' (id={p.id}) "
                    f"into '{keep.port_name}' (id={keep.id}), "
                    f"switch_id={switch_id}, ifIndex={port_index}"
                )
                self.db.delete(p)
                merged_count += 1

        if merged_count > 0:
            self.db.flush()
            logger.info(f"Cleaned up {merged_count} duplicate port records")

        return merged_count

    async def discover_neighbors(self, switch: Switch) -> List[LLDPNeighbor]:
        """
        Discover LLDP neighbors for a switch.

        Args:
            switch: The switch to query

        Returns:
            List of discovered LLDP neighbors
        """
        logger.info(f"Discovering LLDP neighbors for {switch.hostname} ({switch.ip_address})")

        try:
            return await self._query_lldp(switch)
        except ImportError as e:
            logger.error(f"pysnmp not available for LLDP discovery: {e}")
            raise RuntimeError("pysnmp library not available - cannot perform LLDP discovery")
        except Exception as e:
            logger.error(f"LLDP query failed for {switch.hostname}: {e}")
            raise

    async def _query_lldp(self, switch: Switch) -> List[LLDPNeighbor]:
        """Query LLDP neighbors via SNMP."""
        from pysnmp.hlapi.v1arch.asyncio import (
            walk_cmd, SnmpDispatcher, CommunityData,
            UdpTransportTarget, ObjectType, ObjectIdentity
        )

        neighbors = []
        community = switch.snmp_community or "public"
        device_type = (switch.device_type or "huawei").lower()

        logger.info(f"Querying LLDP neighbors for {switch.hostname} via SNMP")

        # Storage for LLDP data indexed by OID suffix
        chassis_data = {}
        port_data = {}
        sysname_data = {}
        syscap_supported_data = {}
        syscap_enabled_data = {}

        try:
            dispatcher = SnmpDispatcher()
            target = await UdpTransportTarget.create((switch.ip_address, 161), timeout=10, retries=3)

            # pysnmp 7.x walk_cmd takes only ONE ObjectType per call
            # Walk lldpRemChassisId
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(LLDP_MIB["lldpRemChassisId"]))
            ):
                if errorIndication or errorStatus:
                    break
                for oid, value in varBinds:
                    oid_str = str(oid)
                    # Extract last 3 parts: timeMark.localPortNum.index
                    parts = oid_str.split(".")
                    if len(parts) >= 3:
                        key = ".".join(parts[-3:])
                        chassis_data[key] = str(value)

            # Walk lldpRemPortId
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(LLDP_MIB["lldpRemPortId"]))
            ):
                if errorIndication or errorStatus:
                    break
                for oid, value in varBinds:
                    oid_str = str(oid)
                    parts = oid_str.split(".")
                    if len(parts) >= 3:
                        key = ".".join(parts[-3:])
                        port_data[key] = str(value)

            # Walk lldpRemSysName
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(LLDP_MIB["lldpRemSysName"]))
            ):
                if errorIndication or errorStatus:
                    break
                for oid, value in varBinds:
                    oid_str = str(oid)
                    parts = oid_str.split(".")
                    if len(parts) >= 3:
                        key = ".".join(parts[-3:])
                        sysname_data[key] = str(value)

            # Walk lldpRemSysCapSupported (System Capabilities Supported)
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(LLDP_MIB["lldpRemSysCapSupported"]))
            ):
                if errorIndication or errorStatus:
                    break
                for oid, value in varBinds:
                    oid_str = str(oid)
                    parts = oid_str.split(".")
                    if len(parts) >= 3:
                        key = ".".join(parts[-3:])
                        # Value is BITS, parse as integer
                        try:
                            if hasattr(value, 'prettyPrint'):
                                val_str = value.prettyPrint()
                                # Handle hex string like "0x0c" or bytes
                                if val_str.startswith("0x"):
                                    syscap_supported_data[key] = int(val_str, 16)
                                elif isinstance(value, bytes):
                                    syscap_supported_data[key] = int.from_bytes(value[:2], 'big') if len(value) >= 2 else int.from_bytes(value, 'big')
                                else:
                                    syscap_supported_data[key] = int(val_str) if val_str.isdigit() else 0
                            else:
                                syscap_supported_data[key] = int(value)
                        except (ValueError, TypeError):
                            syscap_supported_data[key] = 0

            # Walk lldpRemSysCapEnabled (System Capabilities Enabled)
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(LLDP_MIB["lldpRemSysCapEnabled"]))
            ):
                if errorIndication or errorStatus:
                    break
                for oid, value in varBinds:
                    oid_str = str(oid)
                    parts = oid_str.split(".")
                    if len(parts) >= 3:
                        key = ".".join(parts[-3:])
                        try:
                            if hasattr(value, 'prettyPrint'):
                                val_str = value.prettyPrint()
                                if val_str.startswith("0x"):
                                    syscap_enabled_data[key] = int(val_str, 16)
                                elif isinstance(value, bytes):
                                    syscap_enabled_data[key] = int.from_bytes(value[:2], 'big') if len(value) >= 2 else int.from_bytes(value, 'big')
                                else:
                                    syscap_enabled_data[key] = int(val_str) if val_str.isdigit() else 0
                            else:
                                syscap_enabled_data[key] = int(value)
                        except (ValueError, TypeError):
                            syscap_enabled_data[key] = 0

            dispatcher.close_dispatcher()

            # Combine data by key
            for key in chassis_data:
                parts = key.split(".")
                local_port_index = int(parts[1]) if len(parts) >= 2 else 1

                neighbor = LLDPNeighbor(
                    local_port_name=normalize_port_name(f"GigabitEthernet0/0/{local_port_index}"),
                    local_port_index=local_port_index,
                    remote_chassis_id=chassis_data.get(key, ""),
                    remote_port_id=port_data.get(key, ""),
                    remote_system_name=sysname_data.get(key) if sysname_data.get(key) else None,
                    remote_sys_cap_supported=syscap_supported_data.get(key, 0),
                    remote_sys_cap_enabled=syscap_enabled_data.get(key, 0),
                )
                neighbors.append(neighbor)

                # Log neighbor type for debugging
                logger.debug(f"LLDP neighbor on port {local_port_index}: {neighbor.remote_system_name} - type: {neighbor.neighbor_type} (caps: 0x{neighbor.remote_sys_cap_enabled:02x})")

            logger.info(f"LLDP discovery completed for {switch.hostname}: {len(neighbors)} neighbors found")

        except Exception as e:
            logger.error(f"LLDP SNMP query failed for {switch.hostname}: {e}")
            raise

        return neighbors

    async def refresh_topology(self) -> Dict[str, Any]:
        """
        Refresh network topology by discovering LLDP neighbors on all switches.

        Returns:
            Summary of topology discovery results
        """
        start_time = datetime.utcnow()

        switches = self.db.query(Switch).filter(Switch.is_active == True).all()

        result = {
            "status": "success",
            "switches_discovered": 0,
            "links_created": 0,
            "links_updated": 0,
            "errors": [],
            "started_at": start_time.isoformat(),
        }

        if len(switches) < 2:
            result["status"] = "warning"
            result["message"] = "Almeno 2 switch necessari per creare topologia"
            return result

        # Clean up duplicate port records from previous LLDP runs
        # (same ifIndex, different names due to LLDP vs SNMP naming mismatch)
        try:
            merged = self._cleanup_duplicate_ports()
            if merged > 0:
                self.db.commit()
        except Exception as e:
            logger.warning(f"Duplicate port cleanup failed: {e}")
            self.db.rollback()

        # Track discovered links to avoid duplicates
        discovered_links = set()

        for switch in switches:
            try:
                neighbors = await self.discover_neighbors(switch)
                result["switches_discovered"] += 1

                for neighbor in neighbors:
                    # Try to find the remote switch in database
                    remote_switch = None

                    if neighbor.remote_system_name:
                        remote_switch = self.db.query(Switch).filter(
                            Switch.hostname == neighbor.remote_system_name
                        ).first()

                    if not remote_switch and neighbor.remote_mgmt_address:
                        remote_switch = self.db.query(Switch).filter(
                            Switch.ip_address == neighbor.remote_mgmt_address
                        ).first()

                    if not remote_switch:
                        # Remote device not in switches table (could be AP, phone, etc.)
                        # Still update local port's LLDP fields for correct uplink/endpoint classification
                        logger.info(f"LLDP neighbor '{neighbor.remote_system_name}' on {switch.hostname}:{neighbor.local_port_name} not in switches DB - updating port LLDP info")

                        # Determine neighbor type
                        if neighbor.is_access_point:
                            nr_type = "ap"
                            nr_is_uplink = False
                            nr_port_type = "ap_port"
                        elif neighbor.is_phone:
                            nr_type = "phone"
                            nr_is_uplink = False
                            nr_port_type = "phone_port"
                        elif neighbor.is_network_device:
                            nr_type = "switch"
                            nr_is_uplink = True
                            nr_port_type = "uplink"
                        else:
                            # Check system name for AP-like patterns (fallback)
                            sys_name = (neighbor.remote_system_name or "").upper()
                            if any(p in sys_name for p in ["-AP", "_AP", "AP0", "AP1", "AP2", "AP3"]):
                                nr_type = "ap"
                                nr_is_uplink = False
                                nr_port_type = "ap_port"
                                logger.info(f"Detected AP by name pattern: '{neighbor.remote_system_name}'")
                            else:
                                nr_type = "unknown"
                                nr_is_uplink = True
                                nr_port_type = "uplink"

                        # Update local port with LLDP data (lookup by ifIndex first)
                        local_port = self._find_local_port(
                            switch.id, neighbor.local_port_index, neighbor.local_port_name
                        )
                        if local_port:
                            local_port.lldp_neighbor_name = neighbor.remote_system_name
                            local_port.lldp_neighbor_type = nr_type
                            local_port.is_uplink = nr_is_uplink
                            local_port.port_type = nr_port_type
                            logger.info(f"Updated port {switch.hostname}:{neighbor.local_port_name} -> LLDP={neighbor.remote_system_name}, type={nr_type}, is_uplink={nr_is_uplink}")
                        continue

                    # Create a unique link identifier (sorted to handle bidirectional)
                    link_key = tuple(sorted([switch.id, remote_switch.id]))

                    if link_key in discovered_links:
                        continue  # Skip duplicate link

                    discovered_links.add(link_key)

                    # Determine if this port should be treated as uplink based on neighbor type
                    # - If neighbor is Switch/Router: this is an UPLINK (traffic transits through)
                    # - If neighbor is AP: this is an AP_PORT (MACs behind it are endpoints)
                    # - If neighbor is Phone: this is an ENDPOINT (phone is the endpoint)
                    if neighbor.is_network_device:
                        # Neighbor is switch/router - this is a true uplink
                        port_type = "uplink"
                        is_uplink = True
                        lldp_neighbor_type = "switch" if neighbor.is_switch else "router"
                    elif neighbor.is_access_point:
                        # Neighbor is AP - MACs behind this port ARE endpoints!
                        port_type = "ap_port"
                        is_uplink = False  # Critical: AP ports are NOT uplinks for MAC tracking!
                        lldp_neighbor_type = "ap"
                        logger.info(f"Port {neighbor.local_port_name} on {switch.hostname} has AP neighbor '{neighbor.remote_system_name}' - MACs on this port are ENDPOINTS")
                    elif neighbor.is_phone:
                        # Neighbor is IP phone - this is an endpoint
                        port_type = "phone_port"
                        is_uplink = False
                        lldp_neighbor_type = "phone"
                    else:
                        # Unknown device type with LLDP - assume it's infrastructure
                        port_type = "uplink"
                        is_uplink = True
                        lldp_neighbor_type = "unknown"

                    # Get or create local port (lookup by ifIndex first, then name)
                    local_port = self._find_local_port(
                        switch.id, neighbor.local_port_index, neighbor.local_port_name
                    )

                    if not local_port:
                        local_port = Port(
                            switch_id=switch.id,
                            port_name=normalize_port_name(neighbor.local_port_name),
                            port_index=neighbor.local_port_index,
                            port_type=port_type,
                            is_uplink=is_uplink,
                        )
                        self.db.add(local_port)
                        self.db.flush()
                    else:
                        # Update port type based on LLDP neighbor
                        local_port.is_uplink = is_uplink
                        local_port.port_type = port_type

                    # Store LLDP neighbor info on port for reference
                    if hasattr(local_port, 'lldp_neighbor_name'):
                        local_port.lldp_neighbor_name = neighbor.remote_system_name
                    if hasattr(local_port, 'lldp_neighbor_type'):
                        local_port.lldp_neighbor_type = lldp_neighbor_type

                    # Get or create remote port
                    remote_port_name = normalize_port_name(neighbor.remote_port_id)
                    remote_port = self.db.query(Port).filter(
                        Port.switch_id == remote_switch.id,
                        Port.port_name == remote_port_name
                    ).first()

                    if not remote_port:
                        remote_port = Port(
                            switch_id=remote_switch.id,
                            port_name=remote_port_name,
                            port_index=1,  # Default index
                            port_type="uplink",
                            is_uplink=True,
                        )
                        self.db.add(remote_port)
                        self.db.flush()
                    else:
                        remote_port.is_uplink = True
                        remote_port.port_type = "uplink"

                    # Check for existing link
                    existing_link = self.db.query(TopologyLink).filter(
                        ((TopologyLink.local_switch_id == switch.id) &
                         (TopologyLink.remote_switch_id == remote_switch.id)) |
                        ((TopologyLink.local_switch_id == remote_switch.id) &
                         (TopologyLink.remote_switch_id == switch.id))
                    ).first()

                    if existing_link:
                        # Update existing link
                        existing_link.last_seen = datetime.utcnow()
                        existing_link.protocol = "lldp"
                        result["links_updated"] += 1
                    else:
                        # Create new link
                        new_link = TopologyLink(
                            local_switch_id=switch.id,
                            local_port_id=local_port.id,
                            remote_switch_id=remote_switch.id,
                            remote_port_id=remote_port.id,
                            protocol="lldp",
                            discovered_at=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                        )
                        self.db.add(new_link)
                        result["links_created"] += 1

            except Exception as e:
                error_msg = f"Error discovering {switch.hostname}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)

        self.db.commit()

        result["completed_at"] = datetime.utcnow().isoformat()
        result["message"] = f"Topologia aggiornata: {result['links_created']} nuovi collegamenti, {result['links_updated']} aggiornati"

        logger.info(f"Topology refresh complete: {result['links_created']} created, {result['links_updated']} updated")

        return result
