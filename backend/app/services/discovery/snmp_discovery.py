"""SNMP Discovery Service for MAC address table retrieval."""
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.db.models import Switch, Port, MacAddress, MacLocation, MacHistory, DiscoveryLog
from app.services.alerts.alert_service import AlertService
from app.utils.port_utils import normalize_port_name

logger = logging.getLogger(__name__)

# Try to import pysnmp - if it fails, set flag to False
PYSNMP_AVAILABLE = False
try:
    from pysnmp.hlapi.v1arch.asyncio import (
        walk_cmd, get_cmd, SnmpDispatcher, CommunityData,
        UdpTransportTarget, ObjectType, ObjectIdentity
    )
    PYSNMP_AVAILABLE = True
    logger.info(f"✓ pysnmp 7.x library loaded successfully - real SNMP discovery available (PYSNMP_AVAILABLE={PYSNMP_AVAILABLE})")
except ImportError as e:
    logger.error(f"✗ pysnmp library import failed: {e}. SNMP discovery will NOT work!")
except Exception as e:
    logger.error(f"✗ Unexpected error loading pysnmp: {e}. SNMP discovery will NOT work!")

# Bridge MIB OIDs for MAC address table
BRIDGE_MIB = {
    "dot1dTpFdbAddress": "1.3.6.1.2.1.17.4.3.1.1",  # MAC address
    "dot1dTpFdbPort": "1.3.6.1.2.1.17.4.3.1.2",     # Port number
    "dot1dTpFdbStatus": "1.3.6.1.2.1.17.4.3.1.3",   # Status
}

# Q-Bridge MIB for VLAN-aware MAC table (802.1Q)
QBRIDGE_MIB = {
    "dot1qTpFdbPort": "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "dot1qVlanStaticRowStatus": "1.3.6.1.2.1.17.7.1.4.3.1.5",  # VLAN list (802.1Q)
    "dot1qVlanCurrentEntry": "1.3.6.1.2.1.17.7.1.4.2.1",  # Current VLAN table
}

# Standard SNMPv2-MIB OIDs for system info
SYSTEM_MIB = {
    "sysName": "1.3.6.1.2.1.1.5.0",       # SNMPv2-MIB::sysName.0
    "sysDescr": "1.3.6.1.2.1.1.1.0",      # SNMPv2-MIB::sysDescr.0
    "sysObjectID": "1.3.6.1.2.1.1.2.0",   # SNMPv2-MIB::sysObjectID.0
    "sysUpTime": "1.3.6.1.2.1.1.3.0",     # SNMPv2-MIB::sysUpTime.0
    "sysContact": "1.3.6.1.2.1.1.4.0",    # SNMPv2-MIB::sysContact.0
    "sysLocation": "1.3.6.1.2.1.1.6.0",   # SNMPv2-MIB::sysLocation.0
}

# IF-MIB OIDs for interface/port status
IF_MIB = {
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",           # Interface description
    "ifType": "1.3.6.1.2.1.2.2.1.3",            # Interface type
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",     # Admin status (up=1, down=2, testing=3)
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",      # Operational status (up=1, down=2, testing=3, etc.)
    "ifNumber": "1.3.6.1.2.1.2.1.0",            # Total number of interfaces
}

# ENTITY-MIB OIDs for equipment information (serial number)
ENTITY_MIB = {
    "entPhysicalSerialNum": "1.3.6.1.2.1.47.1.1.1.1.11",  # Serial number
    "entPhysicalModelName": "1.3.6.1.2.1.47.1.1.1.1.13",  # Model name
    "entPhysicalClass": "1.3.6.1.2.1.47.1.1.1.1.5",       # Physical class (chassis=3)
}

# Huawei CloudEngine specific MIBs
HUAWEI_MIB = {
    # Huawei FDB Dynamic MAC Table (hwFdbDynMacTable) - CORRECT OID for MAC addresses
    # OID format: base.MAC[6bytes].VLAN.type.flags = ifIndex
    # Example: 1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4.0.230.14.101.89.0.1001.1.48 = 104
    "hwFdbDynMacTable": "1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4",  # Huawei dynamic FDB MAC table
    # Legacy OIDs (kept for fallback)
    "hwL2VlanMacTable": "1.3.6.1.4.1.2011.5.25.42.3.1.1.1",  # Huawei MAC table per VLAN (old)
    "hwL2VlanMacAddress": "1.3.6.1.4.1.2011.5.25.42.3.1.1.1.1",  # MAC address
    "hwL2VlanMacPort": "1.3.6.1.4.1.2011.5.25.42.3.1.1.1.2",  # Port name
    "hwL2VlanMacVlan": "1.3.6.1.4.1.2011.5.25.42.3.1.1.1.3",  # VLAN ID
    # Huawei-specific ENTITY-MIB extensions
    "hwEntityBoardSerial": "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.19",  # Board serial number
    "hwEntitySystemSerial": "1.3.6.1.4.1.2011.6.3.3.2.1.2",  # System serial (alternate)
    # Huawei VLAN MIB
    "hwVlanMIBEntry": "1.3.6.1.4.1.2011.5.25.42.1.1.1",  # Huawei VLAN table
}


class SNMPDiscoveryService:
    """Service for discovering MAC addresses via SNMP."""

    def __init__(self, db: Session):
        self.db = db
        self.alert_service = AlertService(db)

    async def discover_switch(self, switch: Switch) -> Dict[str, Any]:
        """
        Discover MAC addresses from a single switch via SNMP.

        Args:
            switch: The switch to query

        Returns:
            Dictionary with discovery results
        """
        start_time = datetime.utcnow()
        result = {
            "switch_id": switch.id,
            "hostname": switch.hostname,
            "status": "success",
            "mac_count": 0,
            "error_message": None,
            "started_at": start_time,
        }

        try:
            logger.info(f"Starting discovery for {switch.hostname} ({switch.ip_address})")

            if not PYSNMP_AVAILABLE:
                # pysnmp not available - cannot proceed
                raise RuntimeError("pysnmp library not available - cannot perform SNMP discovery")

            # Real SNMP query (requires network access and pysnmp)
            logger.info(f"Using real SNMP query for {switch.hostname} with community '{switch.snmp_community}'")
            mac_entries = await self._query_snmp(switch)

            # Process discovered MACs
            processed_count = await self._process_mac_entries(switch, mac_entries)
            result["mac_count"] = processed_count
            logger.info(f"Processed {processed_count} MACs for {switch.hostname}")

            # Query and update system info (sysName, serial, VLANs, port status)
            await self.update_switch_system_info(switch)

            # Update switch last_discovery timestamp
            switch.last_discovery = datetime.utcnow()
            switch.last_seen = datetime.utcnow()
            self.db.commit()

        except Exception as e:
            logger.error(f"Discovery failed for {switch.hostname}: {str(e)}", exc_info=True)
            result["status"] = "error"
            result["error_message"] = str(e)

        # Log the discovery
        result["completed_at"] = datetime.utcnow()
        result["duration_ms"] = int((result["completed_at"] - start_time).total_seconds() * 1000)

        self._log_discovery(switch, result)

        return result

    async def _query_snmp(self, switch: Switch) -> List[Dict[str, Any]]:
        """
        Query switch via SNMP for MAC address table.

        This is the real SNMP implementation using pysnmp.
        Requires network access to the switch.
        Supports Huawei CloudEngine, Cisco, and generic switches.
        """
        device_type = (switch.device_type or "huawei").lower()

        if device_type == "huawei":
            return await self._query_snmp_huawei(switch)
        elif device_type == "cisco":
            return await self._query_snmp_cisco(switch)
        else:
            return await self._query_snmp_generic(switch)

    async def _get_ifindex_map(self, switch: Switch) -> Dict[int, str]:
        """
        Build a mapping of ifIndex -> interface name (ifDescr) from IF-MIB.
        This allows accurate port name resolution instead of heuristics.
        """
        ifindex_map = {}
        community = switch.snmp_community or "public"
        ifdescr_oid = IF_MIB["ifDescr"]

        try:
            dispatcher = SnmpDispatcher()
            target = await UdpTransportTarget.create((switch.ip_address, 161), timeout=15, retries=2)

            async for result in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(ifdescr_oid))
            ):
                try:
                    errorIndication, errorStatus, errorIndex, varBinds = result
                except (ValueError, TypeError):
                    continue

                if errorIndication or errorStatus:
                    break

                for varBind in varBinds:
                    try:
                        oid, value = varBind
                        oid_str = str(oid)

                        # Check OID is still in ifDescr subtree
                        if not oid_str.startswith(ifdescr_oid):
                            break

                        # Extract ifIndex from OID (last element)
                        if_index = int(oid_str.split(".")[-1])
                        if_descr = str(value).strip().strip('"')

                        # Only store physical interfaces (skip VLAN, Loopback, NULL, etc.)
                        if if_descr and any(p in if_descr for p in ['Ethernet', 'GE', 'Trunk', '40GE', '100GE']):
                            ifindex_map[if_index] = if_descr

                    except (ValueError, IndexError, TypeError):
                        continue

            logger.info(f"Built ifIndex map for {switch.hostname}: {len(ifindex_map)} interfaces")

        except Exception as e:
            logger.warning(f"Failed to build ifIndex map for {switch.hostname}: {e}")

        return ifindex_map

    async def _query_snmp_huawei(self, switch: Switch) -> List[Dict[str, Any]]:
        """
        Query Huawei CloudEngine switch via SNMP for MAC address table.
        Uses Huawei hwFdbDynMacTable (1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4).

        OID format: base.MAC[6bytes].VLAN.type.flags = ifIndex
        Example: 1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4.0.230.14.101.89.0.1001.1.48 = 104
        - MAC: 0.230.14.101.89.0 = 00:E6:0E:65:59:00
        - VLAN: 1001
        - type: 1 (dynamic)
        - flags: 48
        - ifIndex: 104

        Uses pysnmp 7.x asynchronous API.
        """
        mac_entries = []
        community = switch.snmp_community or "public"

        logger.info(f"Querying Huawei switch {switch.hostname} ({switch.ip_address}) via SNMP")

        try:
            mib_tried = "HUAWEI-FDB-MIB"

            # First, build ifIndex -> interface name mapping
            ifindex_map = await self._get_ifindex_map(switch)

            # pysnmp 7.x asynchronous API
            dispatcher = SnmpDispatcher()
            target = await UdpTransportTarget.create((switch.ip_address, 161), timeout=30, retries=3)

            # Use the correct Huawei FDB OID
            huawei_fdb_oid = HUAWEI_MIB["hwFdbDynMacTable"]
            huawei_success = False

            try:
                async for result in walk_cmd(
                    dispatcher,
                    CommunityData(community, mpModel=1),  # SNMPv2c
                    target,
                    ObjectType(ObjectIdentity(huawei_fdb_oid))
                ):
                    try:
                        errorIndication, errorStatus, errorIndex, varBinds = result
                    except (ValueError, TypeError) as unpack_err:
                        logger.debug(f"Failed to unpack SNMP result: {unpack_err}")
                        continue

                    if errorIndication:
                        logger.warning(f"SNMP error indication: {errorIndication}")
                        break
                    if errorStatus:
                        try:
                            error_at = varBinds[int(errorIndex) - 1][0] if errorIndex else '?'
                        except (ValueError, IndexError, TypeError):
                            error_at = '?'
                        logger.warning(f"SNMP error status: {errorStatus.prettyPrint()} at {error_at}")
                        break

                    for varBind in varBinds:
                        try:
                            oid, value = varBind
                            oid_str = str(oid)
                        except Exception as vb_err:
                            logger.debug(f"Failed to parse varBind: {vb_err}")
                            continue

                        # Check if we're still in the correct OID subtree
                        if not oid_str.startswith(huawei_fdb_oid):
                            logger.debug(f"OID {oid_str} outside FDB table, stopping walk")
                            raise StopIteration("OID outside table")

                        huawei_success = True

                        # Parse Huawei FDB MAC table entry
                        # OID format: base.MAC[6].VLAN.type.flags = ifIndex
                        # Example: 1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4.0.230.14.101.89.0.1001.1.48 = 104
                        parts = oid_str.split(".")
                        base_len = len(huawei_fdb_oid.split("."))  # 14 parts for the base OID

                        # After base, we have: MAC[6].VLAN.type.flags
                        # Total parts needed: base_len + 6 (MAC) + 1 (VLAN) + 1 (type) + 1 (flags) = base_len + 9
                        if len(parts) < base_len + 9:
                            logger.debug(f"OID too short: {oid_str}")
                            continue

                        try:
                            # Extract MAC from OID (6 bytes after base)
                            mac_start = base_len
                            mac_bytes = []
                            for i in range(6):
                                byte_val = int(parts[mac_start + i]) % 256
                                mac_bytes.append(byte_val)

                            # Skip broadcast/multicast MACs (first byte odd = multicast)
                            if mac_bytes[0] & 0x01:
                                continue

                            # Skip all-zeros MAC
                            if all(b == 0 for b in mac_bytes):
                                continue

                            mac_address = ":".join([f"{b:02X}" for b in mac_bytes])

                            # Extract VLAN (position after MAC)
                            vlan_id = int(parts[mac_start + 6])

                            # Extract ifIndex from value (the integer value returned)
                            if hasattr(value, 'prettyPrint'):
                                raw_value = value.prettyPrint()
                            else:
                                raw_value = str(value)

                            # Parse ifIndex
                            if isinstance(raw_value, str) and raw_value.isdigit():
                                if_index = int(raw_value)
                            elif isinstance(raw_value, int):
                                if_index = raw_value
                            else:
                                try:
                                    if_index = int(raw_value)
                                except (ValueError, TypeError):
                                    logger.debug(f"Cannot parse ifIndex '{raw_value}' for MAC {mac_address}")
                                    continue

                            # Convert ifIndex to port name using Huawei S6730 convention
                            # ifIndex mapping for Huawei S6730:
                            # GE ports: ifIndex = slot*1000 + port (e.g., GE1/0/1 = 1001? No...)
                            # Actually Huawei uses simple sequential numbering:
                            # ifIndex 1-48: GigabitEthernet1/0/1-48
                            # ifIndex 49-52: XGigabitEthernet1/0/1-4 (10G uplinks)
                            # Or with slot: ifIndex = (slot-1)*52 + port for stacked
                            #
                            # For S6730-H48X6C: 48 GE + 6 10G = 54 ports
                            # ifIndex seems to be sequential starting from 1
                            # Let's map based on observed values (63, 81, 87, 88, 90, 91, 92, 100, 102, 104...)
                            # These are likely the real ifIndex values from IF-MIB

                            port_name = self._huawei_ifindex_to_port(if_index, ifindex_map)

                            mac_entries.append({
                                "mac_address": mac_address,
                                "port_name": port_name,
                                "port_index": if_index,
                                "vlan_id": vlan_id,
                                "device_type": "huawei",
                            })

                        except (ValueError, IndexError, TypeError) as parse_err:
                            logger.debug(f"Failed to parse OID: {oid_str} - {parse_err}")
                            continue

            except StopIteration:
                pass  # Normal end of table
            except Exception as walk_err:
                logger.warning(f"Huawei SNMP walk failed: {walk_err}")

            if not huawei_success or len(mac_entries) == 0:
                # Fallback to Q-Bridge MIB
                logger.info(f"Huawei FDB MIB returned no data, falling back to Q-Bridge MIB for {switch.hostname}")
                mib_tried = "Q-BRIDGE-MIB"
                mac_entries = await self._query_snmp_generic(switch)

            logger.info(f"Huawei discovery completed for {switch.hostname}: {len(mac_entries)} MACs found via {mib_tried}")

        except Exception as e:
            logger.error(f"SNMP query failed for Huawei {switch.hostname}: {e}")
            raise

        return mac_entries

    def _huawei_ifindex_to_port(self, if_index: int, ifindex_map: Dict[int, str] = None) -> str:
        """
        Convert Huawei ifIndex to port name.

        Huawei S6730-H48X6C stack ifIndex mapping (from IF-MIB):
        - ifIndex 61-108: Slot 1 XGE1/0/1-48 + 40GE1/0/1-6
        - ifIndex 115-168: Slot 2 XGE2/0/1-48 + 40GE2/0/1-6
        - ifIndex 177+: Eth-Trunk (aggregated interfaces)

        Args:
            if_index: The interface index from SNMP
            ifindex_map: Optional pre-built mapping of ifIndex -> ifDescr

        Returns:
            Port name string
        """
        if if_index <= 0:
            return "Unknown"

        # Use pre-built map if available
        if ifindex_map and if_index in ifindex_map:
            return ifindex_map[if_index]

        # Huawei S6730-H48X6C stack heuristic mapping
        # Based on observed ifDescr from IF-MIB:
        # - ifIndex 61 = XGigabitEthernet1/0/1
        # - ifIndex 104 = XGigabitEthernet1/0/44
        # - ifIndex 115 = XGigabitEthernet2/0/1
        # - ifIndex 177+ = Eth-Trunk

        if 61 <= if_index <= 108:
            # Slot 1: XGE1/0/1-48 (ifIndex 61-108)
            port_num = if_index - 60
            if port_num <= 48:
                return f"XGigabitEthernet1/0/{port_num}"
            else:
                # 40GE ports (ifIndex 109-114 would be 40GE1/0/1-6)
                return f"40GE1/0/{port_num - 48}"
        elif 109 <= if_index <= 114:
            # Slot 1: 40GE1/0/1-6
            return f"40GE1/0/{if_index - 108}"
        elif 115 <= if_index <= 162:
            # Slot 2: XGE2/0/1-48 (ifIndex 115-162)
            port_num = if_index - 114
            return f"XGigabitEthernet2/0/{port_num}"
        elif 163 <= if_index <= 168:
            # Slot 2: 40GE2/0/1-6
            return f"40GE2/0/{if_index - 162}"
        elif if_index >= 177:
            # Eth-Trunk interfaces
            # ifIndex 177=Eth-Trunk13, 178=Eth-Trunk14, 179=Eth-Trunk7, etc.
            # These are not sequential, so just return generic name
            return f"Eth-Trunk-ifIndex-{if_index}"
        else:
            # Unknown range - could be VLAN interface or management
            return f"Interface-{if_index}"

    async def _query_snmp_cisco(self, switch: Switch) -> List[Dict[str, Any]]:
        """
        Query Cisco switch via SNMP for MAC address table.
        Uses pysnmp 7.x asynchronous API.
        """
        mac_entries = []
        community = switch.snmp_community or "public"

        logger.info(f"Querying Cisco switch {switch.hostname} ({switch.ip_address}) via SNMP")

        try:
            # pysnmp 7.x asynchronous API
            dispatcher = SnmpDispatcher()
            target = await UdpTransportTarget.create((switch.ip_address, 161), timeout=10, retries=3)

            # Use Q-Bridge MIB for Cisco (dot1qTpFdbPort)
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(QBRIDGE_MIB["dot1qTpFdbPort"]))
            ):
                if errorIndication:
                    logger.warning(f"SNMP error indication: {errorIndication}")
                    break
                if errorStatus:
                    logger.warning(f"SNMP error status: {errorStatus.prettyPrint()}")
                    break

                for varBind in varBinds:
                    try:
                        oid, value = varBind
                        oid_str = str(oid)
                    except Exception as vb_err:
                        logger.debug(f"Failed to parse Cisco varBind: {vb_err}")
                        continue

                    # Parse Q-Bridge MIB entry
                    # OID format: base.vlan_id.mac_bytes
                    parts = oid_str.split(".")
                    if len(parts) >= 6:
                        try:
                            # Clean MAC bytes from OID
                            mac_bytes = parts[-6:]
                            mac_bytes_clean = []
                            for b in mac_bytes:
                                b_clean = ''.join(c for c in b if c.isdigit())
                                if b_clean:
                                    mac_bytes_clean.append(int(b_clean) % 256)
                                else:
                                    mac_bytes_clean.append(0)
                            mac_address = ":".join([f"{b:02X}" for b in mac_bytes_clean])

                            # Extract VLAN from OID
                            vlan_part = parts[-7] if len(parts) > 6 else "1"
                            vlan_clean = ''.join(c for c in vlan_part if c.isdigit())
                            vlan_id = int(vlan_clean) if vlan_clean else 1
                        except (ValueError, IndexError) as parse_err:
                            logger.debug(f"Failed to parse Cisco OID parts: {parts[-7:]} - {parse_err}")
                            continue

                        # Parse port index safely
                        try:
                            port_index = int(value)
                        except (ValueError, TypeError):
                            # Value is not a number, try to extract digits or use hash
                            value_str = str(value)
                            match = re.search(r'\d+$', value_str)
                            if match:
                                port_index = int(match.group())
                            else:
                                logger.warning(f"Non-numeric port value '{value}' for MAC {mac_address}, using hash")
                                port_index = abs(hash(value_str)) % 1000 + 1

                        mac_entries.append({
                            "mac_address": mac_address,
                            "port_name": f"Gi0/{port_index}",
                            "port_index": port_index,
                            "vlan_id": vlan_id,
                            "device_type": "cisco",
                        })

            logger.info(f"Cisco discovery completed for {switch.hostname}: {len(mac_entries)} MACs found")

        except Exception as e:
            logger.error(f"SNMP query failed for Cisco {switch.hostname}: {e}")
            raise

        return mac_entries

    async def _query_snmp_generic(self, switch: Switch) -> List[Dict[str, Any]]:
        """
        Query generic switch via SNMP for MAC address table.
        Uses standard Bridge MIB.
        Uses pysnmp 7.x asynchronous API.
        """
        mac_entries = []
        community = switch.snmp_community or "public"

        logger.info(f"Querying generic switch {switch.hostname} ({switch.ip_address}) via SNMP")

        try:
            # pysnmp 7.x asynchronous API
            dispatcher = SnmpDispatcher()
            target = await UdpTransportTarget.create((switch.ip_address, 161), timeout=5, retries=2)

            # First, walk MAC address table to get MAC->index mapping
            mac_to_index = {}  # Maps MAC address to its OID index suffix
            mac_address_oid = BRIDGE_MIB["dot1dTpFdbAddress"]

            try:
                async for result in walk_cmd(
                    dispatcher,
                    CommunityData(community, mpModel=1),  # SNMPv2c
                    target,
                    ObjectType(ObjectIdentity(mac_address_oid))
                ):
                    try:
                        errorIndication, errorStatus, errorIndex, varBinds = result
                    except (ValueError, TypeError) as unpack_err:
                        logger.debug(f"Failed to unpack MAC SNMP result: {unpack_err}")
                        continue

                    if errorIndication:
                        logger.warning(f"SNMP error indication (MAC): {errorIndication}")
                        break
                    if errorStatus:
                        logger.warning(f"SNMP error status (MAC): {errorStatus.prettyPrint()}")
                        break

                    for varBind in varBinds:
                        try:
                            oid, value = varBind
                            oid_str = str(oid)

                            # CRITICAL: Check if we're still in the MAC address table
                            if not oid_str.startswith(mac_address_oid):
                                logger.debug(f"OID {oid_str} outside Bridge MAC table, stopping walk")
                                break

                            # Extract index suffix from OID (the part after the base OID)
                            index_suffix = oid_str[len(mac_address_oid)+1:] if len(oid_str) > len(mac_address_oid) else ""

                            # Parse MAC address from value
                            mac_bytes_str = value.prettyPrint()
                            hex_str = mac_bytes_str.replace("0x", "").replace(" ", "")
                            hex_clean = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                            if len(hex_clean) != 12:
                                continue
                            mac_address = ":".join([f"{int(hex_clean[i:i+2], 16):02X}" for i in range(0, 12, 2)])

                            mac_to_index[index_suffix] = mac_address
                        except Exception as parse_err:
                            logger.debug(f"Failed to parse MAC varBind: {parse_err}")
                            continue
            except Exception as walk_err:
                logger.warning(f"Generic SNMP MAC walk failed: {walk_err}")

            logger.info(f"Found {len(mac_to_index)} MAC addresses via Bridge MIB")

            # Now walk port table to get port mappings
            port_oid = BRIDGE_MIB["dot1dTpFdbPort"]
            try:
                async for result in walk_cmd(
                    dispatcher,
                    CommunityData(community, mpModel=1),
                    target,
                    ObjectType(ObjectIdentity(port_oid))
                ):
                    try:
                        errorIndication, errorStatus, errorIndex, varBinds = result
                    except (ValueError, TypeError):
                        continue

                    if errorIndication or errorStatus:
                        break

                    for varBind in varBinds:
                        try:
                            oid, value = varBind
                            oid_str = str(oid)

                            # Check OID prefix
                            if not oid_str.startswith(port_oid):
                                break

                            # Extract index suffix
                            index_suffix = oid_str[len(port_oid)+1:] if len(oid_str) > len(port_oid) else ""

                            # Look up the MAC address for this index
                            if index_suffix in mac_to_index:
                                mac_address = mac_to_index[index_suffix]

                                # Parse port index
                                try:
                                    port_index = int(value)
                                except (ValueError, TypeError):
                                    value_str = str(value)
                                    match = re.search(r'\d+$', value_str)
                                    port_index = int(match.group()) if match else 1

                                mac_entries.append({
                                    "mac_address": mac_address,
                                    "port_name": f"Port{port_index}",
                                    "port_index": port_index,
                                    "vlan_id": 1,  # Default VLAN
                                })
                        except Exception as parse_err:
                            logger.debug(f"Failed to parse port varBind: {parse_err}")
                            continue
            except Exception as walk_err:
                logger.warning(f"Generic SNMP port walk failed: {walk_err}")

            logger.info(f"Generic discovery completed for {switch.hostname}: {len(mac_entries)} MACs found")

        except Exception as e:
            logger.error(f"SNMP query failed for {switch.hostname}: {e}")
            raise

        return mac_entries

    async def _process_mac_entries(
        self,
        switch: Switch,
        mac_entries: List[Dict[str, Any]]
    ) -> int:
        """
        Process discovered MAC entries and store in database.

        IMPORTANT: This function now implements STALE MAC CLEANUP.
        MACs that are no longer present on the switch are marked as is_current=False.

        Args:
            switch: The switch these MACs were found on
            mac_entries: List of discovered MAC entries

        Returns:
            Number of MACs processed
        """
        processed = 0
        batch_size = 100  # Commit every N entries to avoid long transactions

        # === STALE MAC CLEANUP ===
        # Build set of MAC addresses currently discovered on this switch
        discovered_macs = set(entry["mac_address"].upper() for entry in mac_entries)

        # Find all current MAC locations for this switch
        current_locations = self.db.query(MacLocation).filter(
            MacLocation.switch_id == switch.id,
            MacLocation.is_current == True
        ).all()

        # Mark as stale any MAC not in the discovered set
        stale_count = 0
        for location in current_locations:
            mac = self.db.query(MacAddress).filter(MacAddress.id == location.mac_id).first()
            if mac and mac.mac_address.upper() not in discovered_macs:
                # This MAC is no longer on this switch - mark as not current
                location.is_current = False
                stale_count += 1

                # Create history entry for disappearance
                history_entry = MacHistory(
                    mac_id=mac.id,
                    switch_id=switch.id,
                    port_id=location.port_id,
                    vlan_id=location.vlan_id,
                    event_type="disappeared",
                    event_at=datetime.utcnow(),
                )
                self.db.add(history_entry)

        if stale_count > 0:
            logger.info(f"Marked {stale_count} stale MACs as not current on {switch.hostname}")
            try:
                self.db.commit()
            except Exception as e:
                logger.warning(f"Failed to commit stale MAC cleanup for {switch.hostname}: {e}")
                self.db.rollback()
        # === END STALE MAC CLEANUP ===

        for entry in mac_entries:
            mac_address = entry["mac_address"]
            port_name = normalize_port_name(entry["port_name"])
            port_index = entry.get("port_index", 0)
            vlan_id = entry.get("vlan_id", 1)

            # Get or create port
            port = self.db.query(Port).filter(
                Port.switch_id == switch.id,
                Port.port_name == port_name
            ).first()

            # Detect uplink ports based on:
            # 1. Port name patterns (Eth-Trunk, Port-channel, etc.)
            # 2. LLDP neighbor type (from previous LLDP discovery)
            #
            # CRITICAL LOGIC:
            # - Port with LLDP neighbor = switch/router -> TRUE UPLINK (don't save MACs as endpoint)
            # - Port with LLDP neighbor = AP -> NOT UPLINK (MACs behind AP ARE endpoints!)
            # - Port with LLDP neighbor = phone -> NOT UPLINK (phone is endpoint)
            # - Port with no LLDP neighbor -> could be endpoint
            # - Port name contains 'trunk'/'lag' -> likely uplink

            is_uplink_by_name = any(keyword in port_name.lower() for keyword in [
                'trunk', 'eth-trunk', 'port-channel', 'po', 'lag', 'bond'
            ])

            if not port:
                # New port - use name-based detection initially
                port_type = "trunk" if is_uplink_by_name else "access"
                port = Port(
                    switch_id=switch.id,
                    port_name=port_name,
                    port_index=port_index,
                    vlan_id=vlan_id,
                    port_type=port_type,
                    is_uplink=is_uplink_by_name,
                )
                self.db.add(port)
                try:
                    self.db.flush()  # Get the port ID
                except Exception as e:
                    logger.warning(f"Failed to flush port {port_name}: {e}")
                    self.db.rollback()
                    continue  # Skip this MAC entry
            else:
                # Existing port - respect LLDP-based classification if available
                if port.lldp_neighbor_type:
                    # LLDP has already classified this port
                    # Only switch/router neighbors make this a true uplink
                    if port.lldp_neighbor_type in ('switch', 'router', 'unknown'):
                        # This is a true uplink - MACs on this port are transiting, not endpoints
                        if not port.is_uplink:
                            port.is_uplink = True
                            port.port_type = "uplink"
                            logger.debug(f"Port {port_name} marked as uplink (LLDP neighbor: {port.lldp_neighbor_type})")
                    elif port.lldp_neighbor_type == 'ap':
                        # AP port - MACs behind this ARE endpoints!
                        port.is_uplink = False
                        port.port_type = "ap_port"
                        logger.debug(f"Port {port_name} is AP port - MACs are endpoints")
                    elif port.lldp_neighbor_type == 'phone':
                        # Phone port - endpoint
                        port.is_uplink = False
                        port.port_type = "phone_port"
                elif is_uplink_by_name and not port.is_uplink:
                    # No LLDP info but name suggests trunk
                    port.is_uplink = True
                    port.port_type = "trunk"

            # Get or create MAC address
            mac = self.db.query(MacAddress).filter(
                MacAddress.mac_address == mac_address
            ).first()

            is_new_mac = False
            if not mac:
                # New MAC - create it
                oui = mac_address[:8].replace(":", "")
                mac = MacAddress(
                    mac_address=mac_address,
                    vendor_oui=oui,
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    is_active=True,
                )
                self.db.add(mac)
                try:
                    self.db.flush()
                except Exception as e:
                    logger.warning(f"Failed to flush MAC {mac_address}: {e}")
                    self.db.rollback()
                    continue  # Skip this MAC entry
                is_new_mac = True
            else:
                # Update existing MAC
                mac.last_seen = datetime.utcnow()
                mac.is_active = True

            # Update or create location
            location = self.db.query(MacLocation).filter(
                MacLocation.mac_id == mac.id,
                MacLocation.is_current == True
            ).first()

            if location:
                # Check if location changed
                if location.switch_id != switch.id or location.port_id != port.id:
                    # Get current location's port to check if it's uplink
                    current_port = self.db.query(Port).filter(Port.id == location.port_id).first()
                    current_is_uplink = current_port.is_uplink if current_port else False

                    # ENDPOINT PRIORITY LOGIC (IMPROVED with LLDP neighbor type):
                    #
                    # The key insight: A MAC address flows FROM endpoint TOWARD core.
                    # So every switch along the path sees the MAC on its upstream port.
                    # We want to save ONLY the endpoint location (furthest downstream).
                    #
                    # Decision matrix:
                    # - Current port is NOT uplink + New port IS uplink -> KEEP current (current is endpoint)
                    # - Current port IS uplink + New port is NOT uplink -> UPDATE (found real endpoint!)
                    # - Both uplink -> keep newer (or don't update - MAC is in transit)
                    # - Both endpoint -> UPDATE (MAC actually moved)
                    #
                    # Special cases:
                    # - AP ports (LLDP neighbor=AP): treat as endpoint, MACs behind AP are endpoints
                    # - Phone ports: treat as endpoint
                    # - Unknown LLDP neighbor: treat as uplink (be conservative)

                    # OUI-based endpoint detection: some devices are ALWAYS endpoints
                    # regardless of being on uplink ports (e.g., Access Points, IP Phones)
                    ENDPOINT_OUIS = [
                        # === ACCESS POINTS ===
                        # Extreme Networks
                        '00186E',  # Extreme Networks (Access Points)
                        '00012E',  # Extreme Networks / Computec OY
                        '5C0E8B',  # Extreme Networks
                        'B4C799',  # Extreme Networks
                        '00E60E',  # Extreme Networks Headquarters (APs)
                        # Aruba / HPE
                        '000B86',  # Aruba Networks
                        '24DE9A',  # Aruba Networks
                        '6CFDB9',  # Aruba Networks
                        '9C1C12',  # Aruba Networks
                        'ACA31E',  # Aruba, a Hewlett Packard Enterprise Company
                        'D8C7C8',  # Aruba Networks
                        '20A6CD',  # Aruba Networks
                        '94B40F',  # Aruba Networks
                        # Cisco Access Points (AIR-AP, Meraki)
                        '0018BA',  # Cisco-Linksys (Meraki)
                        '0024A5',  # Cisco Meraki
                        '88155F',  # Cisco Meraki
                        '0C8BFD',  # Intel Corporate (common in Cisco AP)
                        # Ubiquiti
                        '00275D',  # Ubiquiti Networks
                        '0418D6',  # Ubiquiti Inc
                        '24A43C',  # Ubiquiti Inc
                        '44D9E7',  # Ubiquiti Inc
                        '68D79A',  # Ubiquiti Inc
                        '788A20',  # Ubiquiti Inc
                        '802AA8',  # Ubiquiti Inc
                        'B4FBE4',  # Ubiquiti Inc
                        'DC9FDB',  # Ubiquiti Inc
                        'E063DA',  # Ubiquiti Inc
                        'F09FC2',  # Ubiquiti Inc
                        'FCECDA',  # Ubiquiti Inc
                        # Ruckus Wireless
                        '000000',  # Placeholder - real OUIs below
                        'C4108A',  # Ruckus Wireless
                        '58B633',  # Ruckus Wireless
                        '4C1D96',  # Ruckus Wireless
                        '842B2B',  # Ruckus Wireless
                        'EC589F',  # Ruckus Wireless
                        '74911A',  # Ruckus Wireless
                        # Cambium Networks
                        '58C17A',  # Cambium Networks
                        '0004561',  # Cambium Networks
                        # === IP PHONES ===
                        # Cisco IP Phones
                        '00070E',  # Cisco IP Phone
                        '000FEE',  # Cisco IP Phone
                        '001121',  # Cisco IP Phone
                        '001A2F',  # Cisco IP Phone
                        '001BD4',  # Cisco IP Phone
                        '00226B',  # Cisco IP Phone
                        '002490',  # Cisco IP Phone
                        '002566',  # Cisco IP Phone
                        '0026CB',  # Cisco IP Phone
                        '10BDEC',  # Cisco IP Phone
                        '1CE6C7',  # Cisco IP Phone
                        '442B03',  # Cisco IP Phone
                        '503DE5',  # Cisco IP Phone
                        '5CF9DD',  # Cisco IP Phone
                        '6400F1',  # Cisco IP Phone
                        '6C416A',  # Cisco IP Phone
                        '7C1E52',  # Cisco IP Phone
                        'A8A666',  # Cisco IP Phone
                        'C4649B',  # Cisco IP Phone
                        'DCF898',  # Cisco IP Phone
                        'F8B7E2',  # Cisco IP Phone
                        # Polycom IP Phones
                        '0004F2',  # Polycom
                        '64167F',  # Polycom
                        # Yealink IP Phones
                        '001565',  # Yealink
                        '24CF11',  # Yealink
                        '309E65',  # Yealink
                        '805E0C',  # Yealink
                        '805EC0',  # Yealink (alternate)
                        # Grandstream IP Phones
                        '000B82',  # Grandstream Networks
                        # Avaya IP Phones
                        '00040D',  # Avaya
                        '001B4F',  # Avaya
                        '3CE5A6',  # Avaya
                        '70521C',  # Avaya
                        '7C57BC',  # Avaya
                        # Snom IP Phones
                        '000413',  # Snom Technology
                        # Mitel IP Phones
                        '08000F',  # Mitel Networks
                    ]
                    # Remove placeholder if present
                    ENDPOINT_OUIS = [oui for oui in ENDPOINT_OUIS if oui != '000000']
                    mac_oui = mac_address.replace(':', '').upper()[:6]
                    is_oui_endpoint = mac_oui in ENDPOINT_OUIS

                    # Determine if new port is truly an uplink or endpoint
                    # Use LLDP neighbor type if available, otherwise fall back to is_uplink flag
                    new_port_lldp_type = port.lldp_neighbor_type if port else None
                    new_port_is_uplink = port.is_uplink if port else is_uplink_by_name

                    # Override uplink status based on LLDP neighbor type
                    if new_port_lldp_type == 'ap':
                        # AP port - MACs behind it are endpoints!
                        new_port_is_uplink = False
                        logger.debug(f"Port {port_name} has AP neighbor - treating MACs as endpoints")
                    elif new_port_lldp_type == 'phone':
                        new_port_is_uplink = False
                    elif new_port_lldp_type in ('switch', 'router'):
                        new_port_is_uplink = True

                    # NOTE: For existing MACs, do NOT force new_port_is_uplink=False for OUI endpoints.
                    # The actual port uplink status must be respected so that the endpoint
                    # priority logic below works correctly. OUI endpoints are only used to
                    # bypass the "skip new MAC on uplink" check for brand-new MACs (see below).

                    if new_port_is_uplink and not current_is_uplink:
                        # New port is uplink but we already have a non-uplink endpoint
                        # DON'T update - just log that we saw it on uplink
                        logger.info(f"MAC {mac_address} seen on uplink {port_name} (switch {switch.hostname}), keeping endpoint location at {current_port.port_name if current_port else 'unknown'}")
                        # Update timestamp on current location to show MAC is still active
                        location.seen_at = datetime.utcnow()
                    elif new_port_is_uplink and current_is_uplink and is_oui_endpoint:
                        # Both ports are uplinks and MAC is an endpoint device (AP/phone)
                        # DON'T update - moving between uplinks is meaningless for endpoint devices
                        # Wait for the real access port discovery
                        logger.debug(f"Endpoint OUI MAC {mac_address} seen on another uplink {port_name} (switch {switch.hostname}), keeping current uplink location")
                        location.seen_at = datetime.utcnow()
                    else:
                        # Normal move or upgrade from uplink to endpoint
                        if not new_port_is_uplink and current_is_uplink:
                            logger.info(f"MAC {mac_address} found real endpoint: {port_name} on {switch.hostname} (was on uplink {current_port.port_name if current_port else 'unknown'})")

                        # MAC has moved! Create history entry for the move
                        history_entry = MacHistory(
                            mac_id=mac.id,
                            switch_id=switch.id,
                            port_id=port.id,
                            vlan_id=vlan_id,
                            event_type="move",
                            event_at=datetime.utcnow(),
                            previous_switch_id=location.switch_id,
                            previous_port_id=location.port_id,
                        )
                        self.db.add(history_entry)

                        # Generate alert for MAC movement (only if not upgrading from uplink)
                        if not (not new_port_is_uplink and current_is_uplink):
                            old_switch = self.db.query(Switch).filter(Switch.id == location.switch_id).first()
                            old_port = self.db.query(Port).filter(Port.id == location.port_id).first()
                            if old_switch and old_port:
                                self.alert_service.create_mac_move_alert(
                                    mac=mac,
                                    new_switch=switch,
                                    new_port=port,
                                    old_switch=old_switch,
                                    old_port=old_port,
                                    vlan_id=vlan_id
                                )

                        # Mark old location as not current
                        location.is_current = False
                        # Create new location
                        new_location = MacLocation(
                            mac_id=mac.id,
                            switch_id=switch.id,
                            port_id=port.id,
                            vlan_id=vlan_id,
                            seen_at=datetime.utcnow(),
                            is_current=True,
                        )
                        self.db.add(new_location)
                else:
                    # Same location - just update timestamp
                    location.seen_at = datetime.utcnow()
            else:
                # Compute uplink/endpoint status for new MACs (no prior location)
                mac_oui = mac_address.replace(':', '').upper()[:6]
                is_oui_endpoint = mac_oui in ENDPOINT_OUIS
                new_port_is_uplink = port.is_uplink if port else is_uplink_by_name
                if port and port.lldp_neighbor_type:
                    if port.lldp_neighbor_type in ('switch', 'router'):
                        new_port_is_uplink = True
                    elif port.lldp_neighbor_type in ('ap', 'phone'):
                        new_port_is_uplink = False

                # Skip saving MAC on uplink ports
                # MACs on uplinks are in transit, not endpoints
                #
                # For endpoint OUI MACs (APs, phones): only save on uplink if
                # this is a BRAND-NEW MAC (first time ever seen). If the MAC
                # already exists in DB but lost its current location (stale cleanup),
                # do NOT save on uplink - it will be found on its real access port
                # when that switch gets discovered.
                if new_port_is_uplink:
                    if not is_oui_endpoint:
                        logger.debug(f"Skipping MAC {mac_address} on uplink {port_name} (switch {switch.hostname}) - not an endpoint")
                        continue  # Skip this MAC entry, don't save
                    elif not is_new_mac:
                        # Known MAC with endpoint OUI but no current location
                        # Don't save on uplink - wait for the real access switch
                        logger.info(f"Skipping known endpoint OUI MAC {mac_address} on uplink {port_name} (switch {switch.hostname}) - waiting for access port discovery")
                        continue

                # Create new location (only for access ports, or brand-new endpoint OUIs)
                new_location = MacLocation(
                    mac_id=mac.id,
                    switch_id=switch.id,
                    port_id=port.id,
                    vlan_id=vlan_id,
                    seen_at=datetime.utcnow(),
                    is_current=True,
                )
                self.db.add(new_location)

                # Create history entry for new MAC (first seen)
                if is_new_mac:
                    history_entry = MacHistory(
                        mac_id=mac.id,
                        switch_id=switch.id,
                        port_id=port.id,
                        vlan_id=vlan_id,
                        event_type="new",
                        event_at=datetime.utcnow(),
                    )
                    self.db.add(history_entry)

                    # Generate alert for new MAC
                    self.alert_service.create_new_mac_alert(
                        mac=mac,
                        switch=switch,
                        port=port,
                        vlan_id=vlan_id
                    )

            processed += 1

            # Batch commit every N entries to avoid long transactions and reduce lock time
            if processed % batch_size == 0:
                try:
                    self.db.commit()
                    logger.debug(f"Committed batch of {batch_size} MACs for {switch.hostname}")
                except Exception as e:
                    logger.warning(f"Failed to commit batch for {switch.hostname}: {e}")
                    self.db.rollback()

        # Update MAC counts per port for this switch
        # Count current MAC locations per port
        from sqlalchemy import func
        port_mac_counts = (
            self.db.query(Port.id, func.count(MacLocation.id).label('mac_count'))
            .outerjoin(MacLocation, (MacLocation.port_id == Port.id) & (MacLocation.is_current == True))
            .filter(Port.switch_id == switch.id)
            .group_by(Port.id)
            .all()
        )

        # Update last_mac_count for each port
        for port_id, mac_count in port_mac_counts:
            port = self.db.query(Port).filter(Port.id == port_id).first()
            if port:
                port.last_mac_count = mac_count

                # Check for port with multiple MACs (potential uplink not marked)
                if mac_count > 1 and not port.is_uplink:
                    # Generate alert for port with multiple MACs
                    self.alert_service.create_multiple_mac_alert(
                        switch=switch,
                        port=port,
                        mac_count=mac_count
                    )

        # Final commit for any remaining entries
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to commit final batch for {switch.hostname}: {e}")
            self.db.rollback()
        return processed

    def _log_discovery(self, switch: Switch, result: Dict[str, Any]) -> None:
        """Log the discovery operation to database."""
        log = DiscoveryLog(
            switch_id=switch.id,
            discovery_type="snmp",
            status=result["status"],
            mac_count=result["mac_count"],
            error_message=result.get("error_message"),
            started_at=result["started_at"],
            completed_at=result["completed_at"],
            duration_ms=result.get("duration_ms"),
        )
        self.db.add(log)
        self.db.commit()

    async def query_system_info(self, switch: Switch) -> Dict[str, Any]:
        """
        Query switch system information via SNMP.
        Returns sysName, serial number, VLAN count, port up/down counts.
        """
        if not PYSNMP_AVAILABLE:
            logger.warning(f"Skipping system info query for {switch.hostname} (pysnmp unavailable)")
            return {}

        community = switch.snmp_community or "public"
        system_info = {}

        try:
            dispatcher = SnmpDispatcher()
            target = await UdpTransportTarget.create((switch.ip_address, 161), timeout=10, retries=2)

            # Query sysName
            async for (errorIndication, errorStatus, errorIndex, varBinds) in get_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(SYSTEM_MIB["sysName"]))
            ):
                if not errorIndication and not errorStatus and varBinds:
                    oid, value = varBinds[0]
                    system_info["sys_name"] = str(value)
                    logger.info(f"Got sysName for {switch.hostname}: {system_info['sys_name']}")
                break

            # Query serial number from ENTITY-MIB
            serial_found = False
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(ENTITY_MIB["entPhysicalSerialNum"]))
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    oid, value = varBind
                    serial = str(value).strip()
                    if serial and serial != "":
                        system_info["serial_number"] = serial
                        serial_found = True
                        logger.info(f"Got serial number for {switch.hostname}: {serial}")
                        break
                if serial_found:
                    break

            # If no serial from ENTITY-MIB, try Huawei-specific OID
            if not serial_found and (switch.device_type or "").lower() == "huawei":
                async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                    dispatcher,
                    CommunityData(community, mpModel=1),
                    target,
                    ObjectType(ObjectIdentity(HUAWEI_MIB["hwEntityBoardSerial"]))
                ):
                    if errorIndication or errorStatus:
                        break
                    for varBind in varBinds:
                        oid, value = varBind
                        serial = str(value).strip()
                        if serial and serial != "":
                            system_info["serial_number"] = serial
                            logger.info(f"Got Huawei serial number for {switch.hostname}: {serial}")
                            break
                    break

            # Query model name from ENTITY-MIB
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(ENTITY_MIB["entPhysicalModelName"]))
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    oid, value = varBind
                    model = str(value).strip()
                    if model and model != "":
                        system_info["model"] = model
                        logger.info(f"Got model for {switch.hostname}: {model}")
                        break
                break

            # Query port status (ifOperStatus) to count up/down
            ports_up = 0
            ports_down = 0
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(IF_MIB["ifOperStatus"]))
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    try:
                        oid, value = varBind
                        status = int(value)
                        if status == 1:  # up
                            ports_up += 1
                        elif status == 2:  # down
                            ports_down += 1
                    except (ValueError, TypeError, Exception):
                        pass

            system_info["ports_up_count"] = ports_up
            system_info["ports_down_count"] = ports_down
            logger.info(f"Port status for {switch.hostname}: {ports_up} up, {ports_down} down")

            # Query VLAN count from Q-Bridge MIB
            vlans = set()
            async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                dispatcher,
                CommunityData(community, mpModel=1),
                target,
                ObjectType(ObjectIdentity(QBRIDGE_MIB["dot1qVlanCurrentEntry"]))
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    try:
                        oid_str = str(varBind[0])
                        # Extract VLAN ID from OID (last element)
                        parts = oid_str.split(".")
                        if len(parts) > 0:
                            vlan_id = int(parts[-1])
                            if 1 <= vlan_id <= 4094:
                                vlans.add(vlan_id)
                    except (ValueError, TypeError, Exception):
                        pass

            # If no VLANs from Q-Bridge, try Huawei VLAN MIB
            if len(vlans) == 0 and (switch.device_type or "").lower() == "huawei":
                async for (errorIndication, errorStatus, errorIndex, varBinds) in walk_cmd(
                    dispatcher,
                    CommunityData(community, mpModel=1),
                    target,
                    ObjectType(ObjectIdentity(HUAWEI_MIB["hwVlanMIBEntry"]))
                ):
                    if errorIndication or errorStatus:
                        break
                    for varBind in varBinds:
                        try:
                            oid_str = str(varBind[0])
                            parts = oid_str.split(".")
                            if len(parts) > 0:
                                vlan_id = int(parts[-1])
                                if 1 <= vlan_id <= 4094:
                                    vlans.add(vlan_id)
                        except (ValueError, TypeError, Exception):
                            pass

            system_info["vlan_count"] = len(vlans)
            logger.info(f"VLAN count for {switch.hostname}: {len(vlans)} VLANs")

        except Exception as e:
            logger.error(f"Error querying system info for {switch.hostname}: {e}")

        return system_info

    async def update_switch_system_info(self, switch: Switch) -> bool:
        """
        Query and update switch system information in the database.
        Called during discovery to populate sysName, serial, VLANs, port status.
        """
        try:
            system_info = await self.query_system_info(switch)

            if system_info:
                if "sys_name" in system_info:
                    switch.sys_name = system_info["sys_name"]
                if "serial_number" in system_info:
                    switch.serial_number = system_info["serial_number"]
                if "model" in system_info:
                    switch.model = system_info["model"]
                if "ports_up_count" in system_info:
                    switch.ports_up_count = system_info["ports_up_count"]
                if "ports_down_count" in system_info:
                    switch.ports_down_count = system_info["ports_down_count"]
                if "vlan_count" in system_info:
                    switch.vlan_count = system_info["vlan_count"]

                self.db.commit()
                logger.info(f"Updated system info for {switch.hostname}: sysName={switch.sys_name}, serial={switch.serial_number}, model={switch.model}, ports_up={switch.ports_up_count}, ports_down={switch.ports_down_count}, vlans={switch.vlan_count}")
                return True
        except Exception as e:
            logger.error(f"Failed to update system info for {switch.hostname}: {e}")
            self.db.rollback()

        return False

    async def discover_all_switches(self) -> Dict[str, Any]:
        """
        Run discovery on all active switches.

        Returns:
            Summary of discovery results
        """
        switches = self.db.query(Switch).filter(Switch.is_active == True).all()

        results = {
            "total_switches": len(switches),
            "successful": 0,
            "failed": 0,
            "total_macs": 0,
            "switch_results": [],
        }

        for switch in switches:
            result = await self.discover_switch(switch)
            results["switch_results"].append(result)

            if result["status"] == "success":
                results["successful"] += 1
                results["total_macs"] += result["mac_count"]
            else:
                results["failed"] += 1

        return results


