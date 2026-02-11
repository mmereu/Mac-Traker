"""SSH/CLI Discovery Service for MAC address table retrieval via SSH fallback."""
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.db.models import Switch, SwitchGroup, Port, MacAddress, MacLocation, MacHistory, DiscoveryLog
from app.services.alerts.alert_service import AlertService
from app.utils.port_utils import normalize_port_name

logger = logging.getLogger(__name__)


class SSHDiscoveryService:
    """Service for discovering MAC addresses via SSH/CLI as a fallback to SNMP."""

    # MAC address patterns
    MAC_PATTERN = re.compile(r'([0-9A-Fa-f]{4}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{4}|[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})')

    def __init__(self, db: Session):
        self.db = db
        self.alert_service = AlertService(db)

    async def discover_switch(self, switch: Switch) -> Dict[str, Any]:
        """
        Discover MAC addresses from a single switch via SSH/CLI.

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
            "discovery_type": "cli",
        }

        try:
            logger.info(f"Starting SSH discovery for {switch.hostname} ({switch.ip_address})")

            # Real SSH connection - no simulation fallback
            logger.info(f"Using real SSH connection for {switch.hostname}")
            mac_entries = await self._query_ssh(switch)

            # Process discovered MACs
            processed_count = await self._process_mac_entries(switch, mac_entries)
            result["mac_count"] = processed_count
            logger.info(f"SSH discovery processed {processed_count} MACs for {switch.hostname}")

            # Update switch last_discovery timestamp
            switch.last_discovery = datetime.utcnow()
            switch.last_seen = datetime.utcnow()
            self.db.commit()

        except Exception as e:
            logger.error(f"SSH discovery failed for {switch.hostname}: {str(e)}", exc_info=True)
            result["status"] = "error"
            result["error_message"] = str(e)

        # Log the discovery
        result["completed_at"] = datetime.utcnow()
        result["duration_ms"] = int((result["completed_at"] - start_time).total_seconds() * 1000)

        self._log_discovery(switch, result)

        return result

    def _get_ssh_credentials(self, switch: Switch) -> Dict[str, Any]:
        """Get SSH credentials from switch's group or defaults."""
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
                    # In a real implementation, decrypt the password
                    # For now, assume it's stored in plain text (not recommended for production)
                    credentials["password"] = group.ssh_password_encrypted
                if group.ssh_port:
                    credentials["port"] = group.ssh_port

        return credentials

    def _get_netmiko_device_type(self, switch: Switch) -> str:
        """Map switch device_type to netmiko device_type."""
        device_type = (switch.device_type or "huawei").lower()

        mapping = {
            "huawei": "huawei",
            "cisco": "cisco_ios",
            "extreme": "extreme",
            "hp": "hp_procurve",
            "juniper": "juniper",
        }

        return mapping.get(device_type, "generic_termserver")

    async def _query_ssh(self, switch: Switch) -> List[Dict[str, Any]]:
        """
        Query switch via SSH for MAC address table.

        This is the real SSH implementation using netmiko.
        Requires network access to the switch.
        """
        from netmiko import ConnectHandler

        credentials = self._get_ssh_credentials(switch)
        device_type = self._get_netmiko_device_type(switch)

        logger.info(f"Connecting to {switch.hostname} ({switch.ip_address}) via SSH as {credentials['username']}")

        device = {
            'device_type': device_type,
            'ip': switch.ip_address,
            'username': credentials['username'],
            'password': credentials['password'],
            'port': credentials['port'],
            'timeout': 30,
            'auth_timeout': 30,
            'banner_timeout': 30,
        }

        mac_entries = []

        try:
            with ConnectHandler(**device) as connection:
                # Get MAC address table based on device type
                switch_type = (switch.device_type or "huawei").lower()

                if switch_type == "huawei":
                    mac_entries = self._parse_huawei_mac_table(connection)
                elif switch_type == "cisco":
                    mac_entries = self._parse_cisco_mac_table(connection)
                else:
                    # Generic approach
                    mac_entries = self._parse_generic_mac_table(connection, switch_type)

        except Exception as e:
            logger.error(f"SSH query failed for {switch.hostname}: {e}")
            raise

        return mac_entries

    def _parse_huawei_mac_table(self, connection) -> List[Dict[str, Any]]:
        """Parse MAC address table from Huawei CloudEngine switch."""
        mac_entries = []

        # Huawei CloudEngine command to show MAC table
        output = connection.send_command("display mac-address")

        logger.debug(f"Huawei MAC table output:\n{output}")

        # Parse Huawei MAC table format
        # Typical format:
        # MAC Address       VLAN/VSI/BD  Learned-From  Type
        # -------------------------------------------------------------------------------
        # 0000-5e00-0101    100          GE1/0/1       dynamic
        # 48:2c:6a:xx:xx:xx 200          GE1/0/2       dynamic

        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or 'MAC Address' in line:
                continue

            # Try to parse the line
            parts = line.split()
            if len(parts) >= 4:
                mac_raw = parts[0]
                vlan_raw = parts[1]
                port_name = parts[2]
                mac_type = parts[3] if len(parts) > 3 else "dynamic"

                # Skip static/system MACs
                if mac_type.lower() in ['static', 'system']:
                    continue

                # Normalize MAC address format
                mac_address = self._normalize_mac(mac_raw)
                if not mac_address:
                    continue

                # Parse VLAN ID
                try:
                    vlan_id = int(vlan_raw.split('/')[0])  # Handle VSI/BD format
                except:
                    vlan_id = 1

                # Parse port index from port name
                port_index = self._extract_port_index(port_name)

                mac_entries.append({
                    "mac_address": mac_address,
                    "port_name": port_name,
                    "port_index": port_index,
                    "vlan_id": vlan_id,
                    "device_type": "huawei",
                })

        logger.info(f"Parsed {len(mac_entries)} MACs from Huawei CLI")
        return mac_entries

    def _parse_cisco_mac_table(self, connection) -> List[Dict[str, Any]]:
        """Parse MAC address table from Cisco switch."""
        mac_entries = []

        # Cisco IOS command to show MAC table
        output = connection.send_command("show mac address-table")

        logger.debug(f"Cisco MAC table output:\n{output}")

        # Parse Cisco MAC table format
        # Typical format:
        #           Mac Address Table
        # -------------------------------------------
        # Vlan    Mac Address       Type        Ports
        # ----    -----------       --------    -----
        #  100    0000.5e00.0101    DYNAMIC     Gi0/1
        #  200    48:2c:6a:xx:xx:xx DYNAMIC     Gi0/2

        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or 'Mac Address' in line or 'Vlan' in line:
                continue

            # Try to parse the line
            parts = line.split()
            if len(parts) >= 4:
                try:
                    vlan_id = int(parts[0])
                except:
                    continue

                mac_raw = parts[1]
                mac_type = parts[2]
                port_name = parts[3]

                # Skip static MACs
                if mac_type.upper() == 'STATIC':
                    continue

                # Normalize MAC address format
                mac_address = self._normalize_mac(mac_raw)
                if not mac_address:
                    continue

                # Parse port index
                port_index = self._extract_port_index(port_name)

                mac_entries.append({
                    "mac_address": mac_address,
                    "port_name": port_name,
                    "port_index": port_index,
                    "vlan_id": vlan_id,
                    "device_type": "cisco",
                })

        logger.info(f"Parsed {len(mac_entries)} MACs from Cisco CLI")
        return mac_entries

    def _parse_generic_mac_table(self, connection, device_type: str) -> List[Dict[str, Any]]:
        """Parse MAC address table from generic switch with common commands."""
        mac_entries = []

        # Try common commands
        commands = [
            "show mac address-table",
            "display mac-address",
            "show mac-address-table",
        ]

        output = ""
        for cmd in commands:
            try:
                output = connection.send_command(cmd)
                if output and "Invalid" not in output and "Error" not in output:
                    break
            except:
                continue

        if not output:
            logger.warning(f"Could not retrieve MAC table for {device_type} switch")
            return mac_entries

        # Try to find MAC addresses in output using regex
        for line in output.split('\n'):
            mac_match = self.MAC_PATTERN.search(line)
            if mac_match:
                mac_raw = mac_match.group(1)
                mac_address = self._normalize_mac(mac_raw)
                if mac_address:
                    # Try to extract port and VLAN from line
                    parts = line.split()
                    port_name = "Unknown"
                    vlan_id = 1

                    for part in parts:
                        # Look for port-like patterns
                        if any(prefix in part.lower() for prefix in ['gi', 'ge', 'fa', 'eth', 'port']):
                            port_name = part
                        # Look for VLAN numbers
                        try:
                            val = int(part)
                            if 1 <= val <= 4095:
                                vlan_id = val
                        except:
                            pass

                    mac_entries.append({
                        "mac_address": mac_address,
                        "port_name": port_name,
                        "port_index": self._extract_port_index(port_name),
                        "vlan_id": vlan_id,
                        "device_type": device_type,
                    })

        logger.info(f"Parsed {len(mac_entries)} MACs from generic CLI")
        return mac_entries

    def _normalize_mac(self, mac_raw: str) -> Optional[str]:
        """Normalize MAC address to standard XX:XX:XX:XX:XX:XX format."""
        if not mac_raw:
            return None

        # Remove common separators and convert to uppercase
        mac_clean = mac_raw.upper().replace('-', '').replace(':', '').replace('.', '')

        # Verify it's a valid MAC (12 hex characters)
        if len(mac_clean) != 12:
            return None

        try:
            int(mac_clean, 16)  # Verify it's valid hex
        except ValueError:
            return None

        # Format as XX:XX:XX:XX:XX:XX
        return ':'.join([mac_clean[i:i+2] for i in range(0, 12, 2)])

    def _extract_port_index(self, port_name: str) -> int:
        """Extract numeric port index from port name."""
        if not port_name:
            return 0

        # Try to find the last number in the port name
        numbers = re.findall(r'\d+', port_name)
        if numbers:
            return int(numbers[-1])

        return 0

    async def _process_mac_entries(
        self,
        switch: Switch,
        mac_entries: List[Dict[str, Any]]
    ) -> int:
        """
        Process discovered MAC entries and store in database.
        Same logic as SNMP discovery for consistency.
        """
        processed = 0

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

            # Detect uplink ports: Eth-Trunk, Port-channel, aggregated links
            is_uplink_port = any(keyword in port_name.lower() for keyword in [
                'trunk', 'eth-trunk', 'port-channel', 'po', 'lag', 'bond'
            ])
            port_type = "trunk" if is_uplink_port else "access"

            if not port:
                port = Port(
                    switch_id=switch.id,
                    port_name=port_name,
                    port_index=port_index,
                    vlan_id=vlan_id,
                    port_type=port_type,
                    is_uplink=is_uplink_port,
                )
                self.db.add(port)
                self.db.flush()
            elif is_uplink_port and not port.is_uplink:
                # Update existing port if it's a trunk but not marked as uplink
                port.is_uplink = True
                port.port_type = "trunk"
                self.db.flush()

            # Get or create MAC address
            mac = self.db.query(MacAddress).filter(
                MacAddress.mac_address == mac_address
            ).first()

            is_new_mac = False
            if not mac:
                oui = mac_address[:8].replace(":", "")
                mac = MacAddress(
                    mac_address=mac_address,
                    vendor_oui=oui,
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    is_active=True,
                )
                self.db.add(mac)
                self.db.flush()
                is_new_mac = True
            else:
                mac.last_seen = datetime.utcnow()
                mac.is_active = True

            # Update or create location
            location = self.db.query(MacLocation).filter(
                MacLocation.mac_id == mac.id,
                MacLocation.is_current == True
            ).first()

            if location:
                if location.switch_id != switch.id or location.port_id != port.id:
                    # Get current location's port to check if it's uplink
                    current_port = self.db.query(Port).filter(Port.id == location.port_id).first()
                    current_is_uplink = current_port.is_uplink if current_port else False

                    # ENDPOINT PRIORITY LOGIC:
                    # - If new port is uplink but current is NOT uplink -> DON'T update (keep endpoint)
                    # - If new port is NOT uplink but current IS uplink -> UPDATE (found real endpoint)
                    # - Otherwise -> normal behavior (update location)

                    if is_uplink_port and not current_is_uplink:
                        # New port is uplink but we already have a non-uplink endpoint
                        # DON'T update - just log that we saw it on uplink
                        logger.debug(f"MAC {mac_address} seen on uplink {port_name}, keeping endpoint location at {current_port.port_name if current_port else 'unknown'}")
                        # Update timestamp on current location to show MAC is still active
                        location.seen_at = datetime.utcnow()
                    else:
                        # Normal move or upgrade from uplink to endpoint
                        if not is_uplink_port and current_is_uplink:
                            logger.info(f"MAC {mac_address} found real endpoint: {port_name} (was on uplink {current_port.port_name if current_port else 'unknown'})")

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
                        if not (not is_uplink_port and current_is_uplink):
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

                        location.is_current = False
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
                    location.seen_at = datetime.utcnow()
            else:
                new_location = MacLocation(
                    mac_id=mac.id,
                    switch_id=switch.id,
                    port_id=port.id,
                    vlan_id=vlan_id,
                    seen_at=datetime.utcnow(),
                    is_current=True,
                )
                self.db.add(new_location)

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

                    self.alert_service.create_new_mac_alert(
                        mac=mac,
                        switch=switch,
                        port=port,
                        vlan_id=vlan_id
                    )

            processed += 1

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

        self.db.commit()
        return processed

    def _log_discovery(self, switch: Switch, result: Dict[str, Any]) -> None:
        """Log the SSH discovery operation to database."""
        log = DiscoveryLog(
            switch_id=switch.id,
            discovery_type="cli",
            status=result["status"],
            mac_count=result["mac_count"],
            error_message=result.get("error_message"),
            started_at=result["started_at"],
            completed_at=result["completed_at"],
            duration_ms=result.get("duration_ms"),
        )
        self.db.add(log)
        self.db.commit()
