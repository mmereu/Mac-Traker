"""NeDi database integration service.

This service connects to the NeDi MySQL database to import:
- Devices (switches/routers)
- Nodes (MAC addresses with their locations)
- Interfaces (ports)
- Links (topology connections via LLDP/CDP)

Configuration is loaded from environment variables.
See .env.example for required settings.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.utils.port_utils import normalize_port_name
from app.db.models import (
    Switch,
    Port,
    MacAddress,
    MacLocation,
    TopologyLink,
    DiscoveryLog,
)

logger = logging.getLogger(__name__)


@dataclass
class NeDiConfig:
    """NeDi database connection configuration.

    All values are loaded from environment variables with sensible defaults.
    """
    host: str = os.getenv("NEDI_DB_HOST", "localhost")
    port: int = int(os.getenv("NEDI_DB_PORT", "3306"))
    user: str = os.getenv("NEDI_DB_USER", "nedi")
    password: str = os.getenv("NEDI_DB_PASSWORD", "")
    database: str = os.getenv("NEDI_DB_NAME", "nedi")
    charset: str = "utf8mb4"


class NeDiService:
    """Service for importing data from NeDi MySQL database."""

    def __init__(self, config: Optional[NeDiConfig] = None):
        """Initialize NeDi service with optional config."""
        self.config = config or NeDiConfig()
        self._connection: Optional[pymysql.Connection] = None

    def connect(self) -> bool:
        """Establish connection to NeDi MySQL database."""
        try:
            self._connection = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset=self.config.charset,
                cursorclass=DictCursor,
                connect_timeout=10,
            )
            logger.info(f"Connected to NeDi database at {self.config.host}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to NeDi database: {e}")
            return False

    def disconnect(self):
        """Close connection to NeDi database."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Disconnected from NeDi database")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def get_tables(self) -> List[str]:
        """List all tables in NeDi database."""
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            return [list(row.values())[0] for row in cursor.fetchall()]

    def get_table_structure(self, table_name: str) -> List[Dict]:
        """Get column information for a table."""
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            cursor.execute(f"DESCRIBE {table_name}")
            return cursor.fetchall()

    def get_devices(self) -> List[Dict]:
        """Get all network devices from NeDi.

        NeDi devices table has:
        - device: hostname/IP identifier
        - devip: IP address (stored as INT)
        - devos: Device OS (IOS, Huawei, etc.)
        - description: SNMP sysDescr (contains sysName info)
        - location: SNMP sysLocation
        - contact: SNMP sysContact
        - services: SNMP services mask
        - lastdis: Last discovery timestamp (UNIX epoch)
        - readcomm: SNMP read community
        - vendor: Device vendor
        """
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            # NeDi uses 'devices' table for network devices
            # devip is stored as INT, convert to IP string
            cursor.execute("""
                SELECT
                    device,
                    INET_NTOA(devip) as devip,
                    devos,
                    description,
                    location,
                    contact,
                    services,
                    FROM_UNIXTIME(lastdis) as lastdis,
                    snmpversion,
                    readcomm as community,
                    cliport,
                    vendor
                FROM devices
                WHERE devip IS NOT NULL AND devip != 0
                ORDER BY device
            """)
            return cursor.fetchall()

    def get_nodes(self, limit: int = 500000) -> List[Dict]:
        """Get MAC address nodes from NeDi.

        NeDi nodes table has:
        - mac: MAC address (format: xxxxxxxxxxxx)
        - oui: OUI/Vendor info
        - device: Device where MAC was seen
        - ifname: Interface name
        - vlanid: VLAN ID
        - metric: LLDP/CDP metric
        - lastseen: Last seen timestamp (UNIX epoch)
        - firstseen: First seen timestamp (UNIX epoch)
        - noduser: Username/hostname
        - nodesc: Description
        """
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT
                    mac,
                    oui,
                    noduser as name,
                    nodesc,
                    device,
                    ifname,
                    vlanid,
                    metric,
                    FROM_UNIXTIME(lastseen) as lastseen,
                    FROM_UNIXTIME(firstseen) as firstseen
                FROM nodes
                WHERE mac IS NOT NULL AND mac != ''
                ORDER BY lastseen DESC
                LIMIT {limit}
            """)
            return cursor.fetchall()

    def get_interfaces(self, device: Optional[str] = None) -> List[Dict]:
        """Get interfaces from NeDi.

        NeDi interfaces table has:
        - device: Device hostname
        - ifname: Interface name
        - ifidx: SNMP ifIndex
        - ifdesc: Interface description
        - alias: Interface alias
        - iftype: Interface type
        - speed: Interface speed
        - duplex: Duplex mode
        - pvid: Port VLAN ID
        - ifstat: Interface status (up/down)
        - linktype: Link type (uplink detection)
        """
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            query = """
                SELECT
                    device,
                    ifname,
                    ifidx,
                    ifdesc,
                    alias,
                    iftype,
                    speed,
                    duplex,
                    pvid,
                    ifstat,
                    linktype
                FROM interfaces
            """
            if device:
                query += f" WHERE device = %s"
                cursor.execute(query, (device,))
            else:
                query += " ORDER BY device, ifname"
                cursor.execute(query)
            return cursor.fetchall()

    def get_links(self) -> List[Dict]:
        """Get topology links from NeDi.

        NeDi links table has:
        - device: Local device
        - ifname: Local interface
        - neighbor: Remote device
        - nbrifname: Remote interface
        - bandwidth: Link bandwidth
        - linktype: Link type (LLDP/CDP)
        - linkdesc: Link description
        """
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    device,
                    ifname,
                    neighbor,
                    nbrifname,
                    bandwidth,
                    linktype as type,
                    linkdesc
                FROM links
                ORDER BY device, ifname
            """)
            return cursor.fetchall()

    def get_vlans(self) -> List[Dict]:
        """Get VLAN information from NeDi."""
        if not self._connection:
            return []

        with self._connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    device,
                    vlanid,
                    vlanname
                FROM vlans
                ORDER BY device, vlanid
            """)
            return cursor.fetchall()

    def get_node_count(self) -> int:
        """Get total count of nodes (MAC addresses) in NeDi."""
        if not self._connection:
            return 0

        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM nodes")
            result = cursor.fetchone()
            return result['count'] if result else 0

    def get_device_count(self) -> int:
        """Get total count of devices in NeDi."""
        if not self._connection:
            return 0

        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM devices")
            result = cursor.fetchone()
            return result['count'] if result else 0

    def import_devices_to_mactraker(self, db: Session) -> Dict[str, int]:
        """Import NeDi devices as switches into Mac-Traker.

        Returns:
            Dict with counts: created, updated, skipped, errors
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        devices = self.get_devices()
        logger.info(f"Found {len(devices)} devices in NeDi")

        for device in devices:
            try:
                ip_address = device.get("devip", "").strip() if device.get("devip") else ""
                hostname = device.get("device", "") or ""

                if not ip_address or not hostname:
                    stats["skipped"] += 1
                    continue

                # Check if switch exists by IP OR hostname (to handle duplicates)
                existing = db.query(Switch).filter(
                    or_(Switch.ip_address == ip_address, Switch.hostname == hostname)
                ).first()

                if existing:
                    # Update existing switch
                    existing.hostname = hostname
                    existing.ip_address = ip_address  # Update IP in case hostname matched
                    existing.location = device.get("location")
                    existing.snmp_community = device.get("community", os.getenv("SNMP_COMMUNITY", "public"))
                    existing.last_seen = device.get("lastdis")
                    # Use description as sys_name (contains SNMP sysDescr)
                    existing.sys_name = device.get("description")

                    # Detect device type from devos
                    devos = (device.get("devos") or "").lower()
                    if "huawei" in devos or "vrp" in devos:
                        existing.device_type = "huawei"
                    elif "cisco" in devos or "ios" in devos:
                        existing.device_type = "cisco"
                    elif "extreme" in devos:
                        existing.device_type = "extreme"

                    stats["updated"] += 1
                else:
                    # Create new switch
                    devos = (device.get("devos") or "").lower()
                    device_type = "huawei"  # Default
                    if "cisco" in devos or "ios" in devos:
                        device_type = "cisco"
                    elif "extreme" in devos:
                        device_type = "extreme"

                    new_switch = Switch(
                        hostname=hostname,
                        ip_address=ip_address,
                        device_type=device_type,
                        snmp_community=device.get("community", os.getenv("SNMP_COMMUNITY", "public")),
                        location=device.get("location"),
                        sys_name=device.get("description"),  # Use description as sys_name
                        is_active=True,
                        last_seen=device.get("lastdis"),
                    )
                    db.add(new_switch)
                    db.flush()  # Flush immediately to catch constraint errors early
                    stats["created"] += 1

            except Exception as e:
                logger.error(f"Error importing device {device}: {e}")
                db.rollback()  # Rollback to recover from integrity errors
                stats["errors"] += 1

        db.commit()
        logger.info(f"Device import stats: {stats}")
        return stats

    def import_nodes_to_mactraker(
        self,
        db: Session,
        limit: int = 500000
    ) -> Dict[str, int]:
        """Import NeDi nodes (MAC addresses) into Mac-Traker.

        Returns:
            Dict with counts: created, updated, skipped, errors
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0, "uplink_skipped": 0}

        nodes = self.get_nodes(limit=limit)
        logger.info(f"Found {len(nodes)} nodes in NeDi")

        # Build switch IP to ID mapping
        switches = db.query(Switch).all()
        switch_map = {s.hostname: s for s in switches}
        switch_ip_map = {s.ip_address: s for s in switches}

        for node in nodes:
            try:
                mac = self._normalize_mac(node.get("mac", ""))
                if not mac or len(mac) != 17:
                    stats["skipped"] += 1
                    continue

                device_name = node.get("device", "")
                if not device_name:
                    stats["skipped"] += 1
                    continue

                # Find the switch
                switch = switch_map.get(device_name) or switch_ip_map.get(device_name)
                if not switch:
                    stats["skipped"] += 1
                    continue

                # Get or create MAC address
                mac_addr = db.query(MacAddress).filter(
                    MacAddress.mac_address == mac
                ).first()

                if not mac_addr:
                    mac_addr = MacAddress(
                        mac_address=mac,
                        vendor_oui=mac[:8].upper(),
                        vendor_name=node.get("oui"),  # OUI vendor from NeDi
                        first_seen=node.get("firstseen") or datetime.utcnow(),
                        last_seen=node.get("lastseen") or datetime.utcnow(),
                        is_active=True,
                    )
                    db.add(mac_addr)
                    db.flush()  # Get the ID
                    stats["created"] += 1
                else:
                    mac_addr.last_seen = node.get("lastseen") or datetime.utcnow()
                    mac_addr.is_active = True
                    if not mac_addr.vendor_name and node.get("oui"):
                        mac_addr.vendor_name = node.get("oui")
                    stats["updated"] += 1

                # Get or create port
                port_name = normalize_port_name(node.get("ifname", "unknown"))
                port = db.query(Port).filter(
                    Port.switch_id == switch.id,
                    Port.port_name == port_name
                ).first()

                if not port:
                    port = Port(
                        switch_id=switch.id,
                        port_name=port_name,
                        vlan_id=node.get("vlanid"),
                    )
                    db.add(port)
                    db.flush()

                # Skip location update for uplink ports - keep endpoint location
                # EXCEPTION: endpoint OUIs (APs, IP phones) are always saved
                ENDPOINT_OUIS_NEDI = [
                    # Extreme Networks APs
                    '00186E', '00012E', '5C0E8B', 'B4C799', '00E60E',
                    # Aruba / HPE
                    '000B86', '24DE9A', '6CFDB9', '9C1C12', 'ACA31E', 'D8C7C8', '20A6CD', '94B40F',
                    # Cisco Meraki
                    '0018BA', '0024A5', '88155F',
                    # Ubiquiti
                    '00275D', '0418D6', '24A43C', '44D9E7', '68D79A', '788A20',
                    '802AA8', 'B4FBE4', 'DC9FDB', 'E063DA', 'F09FC2', 'FCECDA',
                    # Ruckus
                    'C4108A', '58B633', '4C1D96', '842B2B',
                ]
                mac_oui = mac_clean.replace(':', '').upper()[:6]
                is_endpoint_oui = mac_oui in ENDPOINT_OUIS_NEDI
                if port.is_uplink and not is_endpoint_oui:
                    stats["uplink_skipped"] += 1
                    continue

                # Update or create MAC location (only for non-uplink ports)
                existing_loc = db.query(MacLocation).filter(
                    MacLocation.mac_id == mac_addr.id,
                    MacLocation.is_current == True
                ).first()

                if existing_loc:
                    # Check if existing location is on an uplink - if so, prefer this non-uplink location
                    existing_port = db.query(Port).filter(Port.id == existing_loc.port_id).first()
                    if existing_port and existing_port.is_uplink:
                        # Current location is on uplink, update to this better endpoint location
                        existing_loc.switch_id = switch.id
                        existing_loc.port_id = port.id
                        existing_loc.vlan_id = node.get("vlanid")
                        existing_loc.ip_address = node.get("ip")
                        existing_loc.hostname = node.get("name")
                        existing_loc.seen_at = node.get("lastseen") or datetime.utcnow()
                    else:
                        # Current location is already on endpoint port, just update timestamp
                        existing_loc.seen_at = node.get("lastseen") or datetime.utcnow()
                        existing_loc.vlan_id = node.get("vlanid")
                        existing_loc.ip_address = node.get("ip")
                        existing_loc.hostname = node.get("name")
                else:
                    new_loc = MacLocation(
                        mac_id=mac_addr.id,
                        switch_id=switch.id,
                        port_id=port.id,
                        vlan_id=node.get("vlanid"),
                        ip_address=node.get("ip"),
                        hostname=node.get("name"),
                        is_current=True,
                        seen_at=node.get("lastseen") or datetime.utcnow(),
                    )
                    db.add(new_loc)

            except Exception as e:
                logger.error(f"Error importing node {node}: {e}")
                db.rollback()  # Rollback to recover from integrity errors
                stats["errors"] += 1

        db.commit()
        logger.info(f"Node import stats: {stats}")
        if stats["uplink_skipped"] > 0:
            logger.info(f"Skipped {stats['uplink_skipped']} nodes on uplink ports (location not updated)")
        return stats

    def import_links_to_mactraker(self, db: Session) -> Dict[str, int]:
        """Import NeDi topology links into Mac-Traker.

        Returns:
            Dict with counts: created, updated, skipped, errors
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        links = self.get_links()
        logger.info(f"Found {len(links)} links in NeDi")

        # Build switch and port mappings
        switches = db.query(Switch).all()
        switch_map = {s.hostname: s for s in switches}
        switch_ip_map = {s.ip_address: s for s in switches}

        for link in links:
            try:
                local_device = link.get("device", "")
                remote_device = link.get("neighbor", "")

                local_switch = switch_map.get(local_device) or switch_ip_map.get(local_device)
                remote_switch = switch_map.get(remote_device) or switch_ip_map.get(remote_device)

                if not local_switch or not remote_switch:
                    stats["skipped"] += 1
                    continue

                local_ifname = normalize_port_name(link.get("ifname") or "unknown")
                remote_ifname = normalize_port_name(link.get("nbrifname") or "unknown")

                # Skip if interface names are empty
                if not local_ifname or local_ifname == "":
                    local_ifname = "unknown"
                if not remote_ifname or remote_ifname == "":
                    remote_ifname = "unknown"

                # Get or create local port
                local_port = db.query(Port).filter(
                    Port.switch_id == local_switch.id,
                    Port.port_name == local_ifname
                ).first()

                if not local_port:
                    local_port = Port(
                        switch_id=local_switch.id,
                        port_name=local_ifname,
                        is_uplink=True,  # It's a link, so it's an uplink
                    )
                    db.add(local_port)
                    db.flush()
                else:
                    if local_port.lldp_neighbor_type not in ('ap', 'phone'):
                        local_port.is_uplink = True

                # Get or create remote port
                remote_port = db.query(Port).filter(
                    Port.switch_id == remote_switch.id,
                    Port.port_name == remote_ifname
                ).first()

                if not remote_port:
                    remote_port = Port(
                        switch_id=remote_switch.id,
                        port_name=remote_ifname,
                        is_uplink=True,
                    )
                    db.add(remote_port)
                    db.flush()
                else:
                    if remote_port.lldp_neighbor_type not in ('ap', 'phone'):
                        remote_port.is_uplink = True

                # Check if link exists
                existing_link = db.query(TopologyLink).filter(
                    TopologyLink.local_switch_id == local_switch.id,
                    TopologyLink.remote_switch_id == remote_switch.id,
                    TopologyLink.local_port_id == local_port.id,
                ).first()

                if existing_link:
                    existing_link.last_seen = datetime.utcnow()
                    existing_link.remote_port_id = remote_port.id
                    stats["updated"] += 1
                else:
                    protocol = (link.get("type") or "lldp").lower()
                    if protocol not in ("lldp", "cdp"):
                        protocol = "lldp"

                    new_link = TopologyLink(
                        local_switch_id=local_switch.id,
                        local_port_id=local_port.id,
                        remote_switch_id=remote_switch.id,
                        remote_port_id=remote_port.id,
                        protocol=protocol,
                    )
                    db.add(new_link)
                    stats["created"] += 1

            except Exception as e:
                logger.error(f"Error importing link {link}: {e}")
                stats["errors"] += 1
                # Don't rollback - just skip this link and continue

        db.commit()
        logger.info(f"Link import stats: {stats}")
        return stats

    def import_interfaces_to_mactraker(self, db: Session) -> Dict[str, int]:
        """Import NeDi interface data to enhance uplink detection.

        Uses NeDi's linktype field to mark additional uplink ports
        that may not have been detected via LLDP link import.

        Returns:
            Dict with counts: updated, skipped, errors
        """
        stats = {"updated": 0, "skipped": 0, "errors": 0}

        interfaces = self.get_interfaces()
        logger.info(f"Found {len(interfaces)} interfaces in NeDi")

        # Build switch mapping
        switches = db.query(Switch).all()
        switch_map = {s.hostname: s for s in switches}
        switch_ip_map = {s.ip_address: s for s in switches}

        for iface in interfaces:
            try:
                device_name = iface.get("device", "")
                if not device_name:
                    stats["skipped"] += 1
                    continue

                switch = switch_map.get(device_name) or switch_ip_map.get(device_name)
                if not switch:
                    stats["skipped"] += 1
                    continue

                ifname = normalize_port_name(iface.get("ifname", ""))
                if not ifname:
                    stats["skipped"] += 1
                    continue

                # Find existing port
                port = db.query(Port).filter(
                    Port.switch_id == switch.id,
                    Port.port_name == ifname
                ).first()

                if not port:
                    stats["skipped"] += 1
                    continue

                # Update port metadata from NeDi
                linktype = iface.get("linktype") or ""
                ifstat = iface.get("ifstat") or ""
                speed = iface.get("speed")
                alias = iface.get("alias") or ""

                # Mark as uplink if NeDi linktype indicates it
                # NeDi linktype values: empty=endpoint, non-empty=has neighbor (uplink)
                # BUT: respect LLDP classification - AP/phone ports are NOT uplinks
                if linktype and linktype.strip():
                    if port.lldp_neighbor_type not in ('ap', 'phone'):
                        port.is_uplink = True

                # Update port description from NeDi alias
                if alias and not port.port_description:
                    port.port_description = alias

                # Update speed
                if speed and not port.speed:
                    port.speed = str(speed)

                # Update operational status
                if ifstat:
                    port.oper_status = "up" if ifstat.lower() in ("up", "1") else "down"

                stats["updated"] += 1

            except Exception as e:
                logger.error(f"Error importing interface {iface}: {e}")
                stats["errors"] += 1

        db.commit()
        logger.info(f"Interface import stats: {stats}")
        return stats

    def full_import(self, db: Session, node_limit: int = 500000) -> Dict[str, Any]:
        """Perform full import from NeDi to Mac-Traker.

        Order: devices -> interfaces/links -> nodes (MACs)

        Returns:
            Dict with all import statistics
        """
        results = {
            "devices": {"created": 0, "updated": 0, "skipped": 0, "errors": 0},
            "nodes": {"created": 0, "updated": 0, "skipped": 0, "errors": 0},
            "links": {"created": 0, "updated": 0, "skipped": 0, "errors": 0},
            "interfaces": {"updated": 0, "skipped": 0, "errors": 0},
            "success": False,
            "error": None,
        }

        try:
            # Log discovery start
            discovery_log = DiscoveryLog(
                discovery_type="nedi_import",
                status="running",
                started_at=datetime.utcnow(),
            )
            db.add(discovery_log)
            db.commit()

            # Import devices first
            logger.info("Starting device import from NeDi...")
            results["devices"] = self.import_devices_to_mactraker(db)

            # Import links (topology)
            logger.info("Starting link import from NeDi...")
            results["links"] = self.import_links_to_mactraker(db)

            # Import interfaces (enhanced uplink detection)
            logger.info("Starting interface import from NeDi...")
            results["interfaces"] = self.import_interfaces_to_mactraker(db)

            # Import nodes (MAC addresses)
            logger.info("Starting node import from NeDi...")
            results["nodes"] = self.import_nodes_to_mactraker(db, limit=node_limit)

            # Deactivate stale MACs (not seen in 48 hours)
            logger.info("Deactivating stale MACs...")
            stale_cutoff = datetime.utcnow() - timedelta(hours=48)
            stale_count = db.query(MacAddress).filter(
                MacAddress.is_active == True,
                MacAddress.last_seen < stale_cutoff
            ).update({"is_active": False}, synchronize_session=False)
            db.commit()
            if stale_count > 0:
                logger.info(f"Deactivated {stale_count} stale MACs (not seen in 48h)")
            results["stale_deactivated"] = stale_count

            # Update discovery log
            discovery_log.status = "success"
            discovery_log.completed_at = datetime.utcnow()
            discovery_log.mac_count = results["nodes"]["created"] + results["nodes"]["updated"]
            discovery_log.duration_ms = int(
                (discovery_log.completed_at - discovery_log.started_at).total_seconds() * 1000
            )
            db.commit()

            results["success"] = True
            logger.info(f"NeDi import completed successfully: {results}")

        except Exception as e:
            logger.error(f"NeDi import failed: {e}")
            results["error"] = str(e)
            results["success"] = False

            # Update discovery log with error
            if discovery_log:
                discovery_log.status = "error"
                discovery_log.error_message = str(e)
                discovery_log.completed_at = datetime.utcnow()
                db.commit()

        return results

    def _normalize_mac(self, mac: str) -> str:
        """Normalize MAC address to AA:BB:CC:DD:EE:FF format."""
        if not mac:
            return ""

        # Remove common separators and convert to uppercase
        clean = mac.upper().replace("-", "").replace(":", "").replace(".", "")

        # Must be 12 hex characters
        if len(clean) != 12:
            return ""

        # Format as AA:BB:CC:DD:EE:FF
        return ":".join(clean[i:i+2] for i in range(0, 12, 2))

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of NeDi database contents."""
        return {
            "devices": self.get_device_count(),
            "nodes": self.get_node_count(),
            "connected": self._connection is not None,
        }
