"""MAC Address Discovery Service - Based on NeDi SNMP OIDs."""
import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    walk_cmd,
)

# OID da NeDi libsnmp.pm - FwdBridge()
OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    # Bridge MIB - MAC table
    "dot1dTpFdbAddress": "1.3.6.1.2.1.17.4.3.1.1",  # MAC address (binary)
    "dot1dTpFdbPort": "1.3.6.1.2.1.17.4.3.1.2",  # Port number
    "dot1dTpFdbStatus": "1.3.6.1.2.1.17.4.3.1.3",  # Status
    # Port to IF index mapping
    "dot1dBasePortIfIndex": "1.3.6.1.2.1.17.1.4.1.2",
    # Q-Bridge MIB (includes VLAN)
    "dot1qTpFdbPort": "1.3.6.1.2.1.17.7.1.2.2.1.2",
    # Interface names
    "ifName": "1.3.6.1.2.1.31.1.1.1.1",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
}


class MacDiscoveryService:
    """Service for discovering MAC addresses from switches via SNMP."""

    def __init__(self, db_path: str, community: str = os.getenv("SNMP_COMMUNITY", "public"), timeout: int = 10):
        self.db_path = db_path
        self.community = community
        self.timeout = timeout
        self.retries = 2

    async def _create_target(self, ip: str) -> UdpTransportTarget:
        """Create SNMP target."""
        return await UdpTransportTarget.create(
            (ip, 161), timeout=self.timeout, retries=self.retries
        )

    async def get_port_if_mapping(self, ip: str) -> dict[int, int]:
        """Get bridge port to ifIndex mapping."""
        snmpEngine = SnmpEngine()
        mapping = {}

        try:
            target = await self._create_target(ip)
            async for errorInd, errorStat, errorIdx, varBinds in walk_cmd(
                snmpEngine,
                CommunityData(self.community),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(OIDS["dot1dBasePortIfIndex"])),
            ):
                if errorInd or errorStat:
                    break
                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    bridge_port = int(oid_str.split(".")[-1])
                    # Value can be Integer or other type
                    try:
                        if_index = int(str(varBind[1]))
                    except (ValueError, TypeError):
                        continue
                    mapping[bridge_port] = if_index
        finally:
            snmpEngine.close_dispatcher()

        return mapping

    async def get_interface_names(self, ip: str) -> dict[int, str]:
        """Get ifIndex to interface name mapping."""
        snmpEngine = SnmpEngine()
        names = {}

        try:
            target = await self._create_target(ip)
            async for errorInd, errorStat, errorIdx, varBinds in walk_cmd(
                snmpEngine,
                CommunityData(self.community),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(OIDS["ifName"])),
            ):
                if errorInd or errorStat:
                    break
                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    try:
                        if_index = int(oid_str.split(".")[-1])
                    except (ValueError, TypeError):
                        continue
                    if_name = str(varBind[1])
                    names[if_index] = if_name
        finally:
            snmpEngine.close_dispatcher()

        return names

    async def get_mac_table(self, ip: str) -> list[dict]:
        """Get MAC address table from switch using Bridge MIB (NeDi style)."""
        snmpEngine = SnmpEngine()
        macs = []

        try:
            target = await self._create_target(ip)

            # Walk dot1dTpFdbPort - MAC is encoded in OID, port is value
            async for errorInd, errorStat, errorIdx, varBinds in walk_cmd(
                snmpEngine,
                CommunityData(self.community),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(OIDS["dot1dTpFdbPort"])),
            ):
                if errorInd:
                    print(f"  SNMP Error: {errorInd}")
                    break
                if errorStat:
                    print(f"  SNMP Status: {errorStat.prettyPrint()}")
                    break

                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    port = int(varBind[1])

                    # Extract MAC from OID (last 6 octets)
                    # OID format: 1.3.6.1.2.1.17.4.3.1.2.MAC1.MAC2.MAC3.MAC4.MAC5.MAC6
                    parts = oid_str.split(".")
                    if len(parts) >= 6:
                        mac_parts = parts[-6:]
                        mac = ":".join(f"{int(p):02x}" for p in mac_parts)
                        macs.append({"mac": mac, "port": port})

        finally:
            snmpEngine.close_dispatcher()

        return macs

    async def discover_switch(self, switch_id: int, ip: str, hostname: str) -> dict:
        """Full MAC discovery for a single switch."""
        print(f"\n[{hostname}] ({ip}) - Starting discovery...")
        result = {
            "switch_id": switch_id,
            "ip": ip,
            "hostname": hostname,
            "mac_count": 0,
            "macs": [],
            "error": None,
        }

        try:
            # Step 1: Get port-to-ifIndex mapping
            print(f"  Getting port mapping...")
            port_map = await self.get_port_if_mapping(ip)
            print(f"  Found {len(port_map)} port mappings")

            # Step 2: Get interface names
            print(f"  Getting interface names...")
            if_names = await self.get_interface_names(ip)
            print(f"  Found {len(if_names)} interface names")

            # Step 3: Get MAC table
            print(f"  Walking MAC table...")
            macs = await self.get_mac_table(ip)
            print(f"  Found {len(macs)} MAC addresses")

            # Step 4: Resolve port names
            for mac_entry in macs:
                bridge_port = mac_entry["port"]
                if_index = port_map.get(bridge_port, bridge_port)
                if_name = if_names.get(if_index, f"Port{bridge_port}")
                mac_entry["if_index"] = if_index
                mac_entry["if_name"] = if_name

            result["macs"] = macs
            result["mac_count"] = len(macs)

        except Exception as e:
            result["error"] = str(e)
            print(f"  ERROR: {e}")

        return result

    async def discover_all(self) -> list[dict]:
        """Discover MAC addresses from all switches in DB."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, ip_address, hostname FROM switches WHERE is_active = 1"
        )
        switches = cursor.fetchall()
        conn.close()

        print(f"=== MAC Discovery: {len(switches)} switches ===")

        results = []
        for switch_id, ip, hostname in switches:
            result = await self.discover_switch(switch_id, ip, hostname)
            results.append(result)

        return results

    def save_results_to_db(self, results: list[dict]) -> dict:
        """Save discovered MACs to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        stats = {
            "total_macs": 0,
            "new_macs": 0,
            "updated_macs": 0,
            "switches_ok": 0,
            "switches_error": 0,
        }

        for result in results:
            if result["error"]:
                stats["switches_error"] += 1
                continue

            stats["switches_ok"] += 1
            switch_id = result["switch_id"]

            for mac_entry in result["macs"]:
                mac = mac_entry["mac"].upper()
                port_name = mac_entry["if_name"]
                stats["total_macs"] += 1

                # Check if MAC exists
                cursor.execute(
                    "SELECT id FROM mac_addresses WHERE mac_address = ?", (mac,)
                )
                mac_row = cursor.fetchone()

                if mac_row:
                    mac_id = mac_row[0]
                    # Update last_seen
                    cursor.execute(
                        "UPDATE mac_addresses SET last_seen = ?, is_active = 1 WHERE id = ?",
                        (now, mac_id),
                    )
                    stats["updated_macs"] += 1
                else:
                    # Insert new MAC
                    oui = mac[:8].replace(":", "")
                    cursor.execute(
                        """INSERT INTO mac_addresses
                           (mac_address, vendor_oui, first_seen, last_seen, is_active)
                           VALUES (?, ?, ?, ?, 1)""",
                        (mac, oui, now, now),
                    )
                    mac_id = cursor.lastrowid
                    stats["new_macs"] += 1

                # Get or create port
                cursor.execute(
                    "SELECT id FROM ports WHERE switch_id = ? AND port_name = ?",
                    (switch_id, port_name),
                )
                port_row = cursor.fetchone()

                if port_row:
                    port_id = port_row[0]
                else:
                    cursor.execute(
                        """INSERT INTO ports (switch_id, port_name, port_index)
                           VALUES (?, ?, ?)""",
                        (switch_id, port_name, mac_entry.get("if_index", 0)),
                    )
                    port_id = cursor.lastrowid

                # Update/Insert mac_location
                cursor.execute(
                    """SELECT id FROM mac_locations
                       WHERE mac_id = ? AND is_current = 1""",
                    (mac_id,),
                )
                loc_row = cursor.fetchone()

                if loc_row:
                    cursor.execute(
                        """UPDATE mac_locations
                           SET switch_id = ?, port_id = ?, seen_at = ?
                           WHERE id = ?""",
                        (switch_id, port_id, now, loc_row[0]),
                    )
                else:
                    cursor.execute(
                        """INSERT INTO mac_locations
                           (mac_id, switch_id, port_id, seen_at, is_current)
                           VALUES (?, ?, ?, ?, 1)""",
                        (mac_id, switch_id, port_id, now),
                    )

            # Update switch last_discovery
            cursor.execute(
                "UPDATE switches SET last_discovery = ?, last_seen = ? WHERE id = ?",
                (now, now, switch_id),
            )

        conn.commit()
        conn.close()

        return stats


async def main():
    """Run MAC discovery."""
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "mactraker.db"

    service = MacDiscoveryService(db_path)
    results = await service.discover_all()

    print("\n" + "=" * 60)
    print("SAVING TO DATABASE...")
    stats = service.save_results_to_db(results)

    print("\n" + "=" * 60)
    print("=== DISCOVERY COMPLETE ===")
    print(f"Switches OK:    {stats['switches_ok']}")
    print(f"Switches Error: {stats['switches_error']}")
    print(f"Total MACs:     {stats['total_macs']}")
    print(f"New MACs:       {stats['new_macs']}")
    print(f"Updated MACs:   {stats['updated_macs']}")


if __name__ == "__main__":
    asyncio.run(main())
