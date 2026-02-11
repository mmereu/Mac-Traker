#!/usr/bin/env python3
"""
Fix MAC locations that are currently on uplink ports.

This script finds MACs whose current location is on an uplink port,
then searches all switches to find the real endpoint.
If found, updates the location in the database.

Run from backend directory:
    python scripts/fix_mac_locations.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netmiko import ConnectHandler
import sqlite3
from datetime import datetime


def get_db_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mactraker.db")


def get_macs_on_uplinks():
    """Get all MACs that are currently located on uplink ports."""
    db = sqlite3.connect(get_db_path())
    cursor = db.cursor()

    cursor.execute("""
        SELECT ma.id, ma.mac_address, ml.id as loc_id, s.hostname, p.port_name
        FROM mac_addresses ma
        JOIN mac_locations ml ON ma.id = ml.mac_id
        JOIN ports p ON ml.port_id = p.id
        JOIN switches s ON ml.switch_id = s.id
        WHERE ml.is_current = 1 AND p.is_uplink = 1
    """)

    macs = cursor.fetchall()
    db.close()
    return macs


def get_switches_with_creds():
    """Get all switches with credentials."""
    db = sqlite3.connect(get_db_path())
    cursor = db.cursor()

    cursor.execute("""
        SELECT s.id, s.hostname, s.ip_address, g.ssh_username, g.ssh_password_encrypted
        FROM switches s
        JOIN switch_groups g ON s.group_id = g.id
        WHERE s.is_active = 1
    """)

    switches = cursor.fetchall()
    db.close()
    return switches


def get_uplink_ports():
    """Get all uplink ports indexed by switch_id."""
    db = sqlite3.connect(get_db_path())
    cursor = db.cursor()

    cursor.execute("SELECT switch_id, port_name FROM ports WHERE is_uplink = 1")
    uplinks = {}
    for sid, pname in cursor.fetchall():
        if sid not in uplinks:
            uplinks[sid] = set()
        # Add both formats
        short_name = pname.replace("GigabitEthernet", "GE").replace("XGigabitEthernet", "XGE")
        uplinks[sid].add(short_name)
        uplinks[sid].add(pname)

    db.close()
    return uplinks


def find_endpoint_for_mac(mac_huawei, switches, uplinks):
    """Find real endpoint for a MAC address."""
    for sid, hostname, ip, username, password in switches:
        try:
            conn = ConnectHandler(
                device_type="huawei",
                host=ip,
                username=username,
                password=password,
                port=22,
                timeout=10
            )
            output = conn.send_command(f"display mac-address | include {mac_huawei}", read_timeout=10)
            conn.disconnect()

            if mac_huawei in output:
                for line in output.split("\n"):
                    if mac_huawei in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            port = parts[2]
                            vlan = parts[1].split("/")[0] if "/" in parts[1] else parts[1]
                            is_uplink = port in uplinks.get(sid, set())

                            if not is_uplink:
                                return (sid, hostname, port, vlan)
        except:
            pass

    return None


def update_mac_location(mac_id, new_switch_id, new_port_name, vlan_id):
    """Update MAC location in database."""
    db = sqlite3.connect(get_db_path())
    cursor = db.cursor()

    # Get port_id for the new port
    cursor.execute("""
        SELECT id FROM ports
        WHERE switch_id = ? AND (port_name = ? OR port_name = ?)
    """, (new_switch_id, new_port_name, new_port_name.replace("GE", "GigabitEthernet")))

    port_row = cursor.fetchone()
    if not port_row:
        db.close()
        return False

    new_port_id = port_row[0]

    # Mark current location as not current
    cursor.execute("""
        UPDATE mac_locations
        SET is_current = 0
        WHERE mac_id = ? AND is_current = 1
    """, (mac_id,))

    # Create new location
    cursor.execute("""
        INSERT INTO mac_locations (mac_id, switch_id, port_id, vlan_id, seen_at, is_current)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (mac_id, new_switch_id, new_port_id, int(vlan_id) if vlan_id else 1, datetime.utcnow().isoformat()))

    db.commit()
    db.close()
    return True


def mac_to_huawei(mac_colon):
    """Convert MAC from XX:XX:XX:XX:XX:XX to xxxx-xxxx-xxxx format."""
    mac_clean = mac_colon.replace(":", "").lower()
    return f"{mac_clean[0:4]}-{mac_clean[4:8]}-{mac_clean[8:12]}"


def main():
    print("=" * 60)
    print("MAC Location Fix - Moving MACs from Uplinks to Endpoints")
    print("=" * 60)

    # Get data
    macs_on_uplinks = get_macs_on_uplinks()
    switches = get_switches_with_creds()
    uplinks = get_uplink_ports()

    print(f"Found {len(macs_on_uplinks)} MACs currently on uplink ports")
    print(f"Scanning {len(switches)} switches for real endpoints...")
    print()

    fixed_count = 0
    not_found_count = 0

    for mac_id, mac_address, loc_id, current_switch, current_port in macs_on_uplinks:
        mac_huawei = mac_to_huawei(mac_address)

        # Find real endpoint
        result = find_endpoint_for_mac(mac_huawei, switches, uplinks)

        if result:
            new_switch_id, new_hostname, new_port, vlan = result
            print(f"  {mac_address}: {current_switch}:{current_port} -> {new_hostname}:{new_port}")

            if update_mac_location(mac_id, new_switch_id, new_port, vlan):
                fixed_count += 1
            else:
                print(f"    WARNING: Failed to update location (port not found in DB)")
        else:
            not_found_count += 1
            # Only print first 10 not found to avoid spam
            if not_found_count <= 10:
                print(f"  {mac_address}: No endpoint found (device not on monitored switches)")

    if not_found_count > 10:
        print(f"  ... and {not_found_count - 10} more MACs with no endpoint found")

    print()
    print("=" * 60)
    print(f"Summary:")
    print(f"  MACs fixed (moved to endpoint): {fixed_count}")
    print(f"  MACs with no endpoint found:    {not_found_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
