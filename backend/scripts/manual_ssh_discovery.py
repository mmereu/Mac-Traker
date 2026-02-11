#!/usr/bin/env python3
"""
Manual SSH Discovery Script.

Runs discovery via SSH on all switches and populates the database.
Uses the same logic as the SSHDiscoveryService but runs standalone.

Run from backend directory:
    python scripts/manual_ssh_discovery.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime
from netmiko import ConnectHandler
import sqlite3
import re


def get_db_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mactraker.db")


def get_switches():
    """Get all active switches with credentials."""
    db = sqlite3.connect(get_db_path())
    cursor = db.cursor()

    cursor.execute("""
        SELECT s.id, s.hostname, s.ip_address, g.ssh_username, g.ssh_password_encrypted
        FROM switches s
        JOIN switch_groups g ON s.group_id = g.id
        WHERE s.is_active = 1
        ORDER BY s.hostname
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
        short_name = pname.replace("GigabitEthernet", "GE").replace("XGigabitEthernet", "XGE")
        uplinks[sid].add(short_name)
        uplinks[sid].add(pname)

    db.close()
    return uplinks


def normalize_mac(mac_huawei):
    """Convert MAC from Huawei format to standard format."""
    # xxxx-xxxx-xxxx -> XX:XX:XX:XX:XX:XX
    mac_clean = mac_huawei.replace("-", "").upper()
    return ":".join([mac_clean[i:i+2] for i in range(0, 12, 2)])


def parse_huawei_mac_table(output):
    """Parse Huawei 'display mac-address' output."""
    mac_entries = []

    for line in output.split("\n"):
        # Format: xxxx-xxxx-xxxx    VLAN/-    Port    Type
        if re.match(r'^[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}', line.lower()):
            parts = line.split()
            if len(parts) >= 3:
                mac_huawei = parts[0]
                vlan_part = parts[1]
                port = parts[2]

                # Parse VLAN (format: "VLAN/-" or just a number)
                vlan = 1
                if "/" in vlan_part:
                    try:
                        vlan = int(vlan_part.split("/")[0])
                    except:
                        pass
                else:
                    try:
                        vlan = int(vlan_part)
                    except:
                        pass

                mac_entries.append({
                    "mac_address": normalize_mac(mac_huawei),
                    "port_name": port,
                    "vlan_id": vlan
                })

    return mac_entries


def discover_switch_ssh(switch_id, hostname, ip, username, password, uplinks):
    """Discover MAC addresses from a single switch via SSH."""
    device = {
        "device_type": "huawei",
        "host": ip,
        "username": username,
        "password": password,
        "port": 22,
        "timeout": 30,
    }

    try:
        print(f"  Connecting to {hostname} ({ip})...", end=" ", flush=True)
        conn = ConnectHandler(**device)
        output = conn.send_command("display mac-address", read_timeout=60)
        conn.disconnect()

        mac_entries = parse_huawei_mac_table(output)
        print(f"Found {len(mac_entries)} MACs")

        return mac_entries

    except Exception as e:
        print(f"ERROR: {str(e)[:50]}")
        return []


def save_mac_locations(switch_id, mac_entries, uplinks):
    """Save MAC locations to database."""
    db = sqlite3.connect(get_db_path())
    cursor = db.cursor()

    saved_count = 0
    uplink_count = 0
    switch_uplinks = uplinks.get(switch_id, set())

    for entry in mac_entries:
        mac_address = entry["mac_address"]
        port_name = entry["port_name"]
        vlan_id = entry["vlan_id"]
        now = datetime.utcnow().isoformat()

        # Check if this port is uplink (check both short and long forms)
        short_port = port_name.replace("GigabitEthernet", "GE").replace("XGigabitEthernet", "XGE")
        long_port = port_name.replace("GE", "GigabitEthernet").replace("XGE", "XGigabitEthernet")
        is_uplink = port_name in switch_uplinks or short_port in switch_uplinks or long_port in switch_uplinks

        if is_uplink:
            uplink_count += 1
            continue  # Skip MACs on uplink ports

        # Get or create port
        norm_port = port_name.replace("GE", "GigabitEthernet").replace("XGE", "XGigabitEthernet")
        cursor.execute("""
            SELECT id FROM ports
            WHERE switch_id = ? AND (port_name = ? OR port_name = ?)
        """, (switch_id, port_name, norm_port))

        port_row = cursor.fetchone()
        if not port_row:
            # Create port
            cursor.execute("""
                INSERT INTO ports (switch_id, port_name, port_index, vlan_id, port_type, is_uplink, admin_status, oper_status, last_mac_count, updated_at)
                VALUES (?, ?, 0, ?, 'access', 0, 'up', 'up', 0, ?)
            """, (switch_id, norm_port, vlan_id, now))
            port_id = cursor.lastrowid
        else:
            port_id = port_row[0]

        # Get or create MAC address
        cursor.execute("SELECT id FROM mac_addresses WHERE mac_address = ?", (mac_address,))
        mac_row = cursor.fetchone()

        if not mac_row:
            # Create MAC
            oui = mac_address[:8].replace(":", "")
            cursor.execute("""
                INSERT INTO mac_addresses (mac_address, vendor_oui, first_seen, last_seen, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (mac_address, oui, now, now))
            mac_id = cursor.lastrowid
        else:
            mac_id = mac_row[0]
            # Update last_seen
            cursor.execute("UPDATE mac_addresses SET last_seen = ?, is_active = 1 WHERE id = ?", (now, mac_id))

        # Check existing location
        cursor.execute("""
            SELECT id, port_id FROM mac_locations
            WHERE mac_id = ? AND is_current = 1
        """, (mac_id,))
        loc_row = cursor.fetchone()

        if loc_row:
            if loc_row[1] != port_id:
                # Check if existing location is on uplink
                cursor.execute("SELECT is_uplink FROM ports WHERE id = ?", (loc_row[1],))
                old_port = cursor.fetchone()
                old_is_uplink = old_port[0] if old_port else False

                if old_is_uplink:
                    # Old location was uplink, update to endpoint
                    cursor.execute("UPDATE mac_locations SET is_current = 0 WHERE id = ?", (loc_row[0],))
                    cursor.execute("""
                        INSERT INTO mac_locations (mac_id, switch_id, port_id, vlan_id, seen_at, is_current)
                        VALUES (?, ?, ?, ?, ?, 1)
                    """, (mac_id, switch_id, port_id, vlan_id, now))
                else:
                    # Both are endpoint, keep existing (no move)
                    cursor.execute("UPDATE mac_locations SET seen_at = ? WHERE id = ?", (now, loc_row[0]))
            else:
                # Same location, update timestamp
                cursor.execute("UPDATE mac_locations SET seen_at = ? WHERE id = ?", (now, loc_row[0]))
        else:
            # Create new location
            cursor.execute("""
                INSERT INTO mac_locations (mac_id, switch_id, port_id, vlan_id, seen_at, is_current)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (mac_id, switch_id, port_id, vlan_id, now))

        saved_count += 1

    db.commit()
    db.close()

    return saved_count, uplink_count


def main():
    print("=" * 60)
    print("Manual SSH Discovery")
    print("=" * 60)

    switches = get_switches()
    uplinks = get_uplink_ports()

    print(f"Found {len(switches)} switches to scan")
    print(f"Loaded uplink ports for {len(uplinks)} switches")
    print()

    total_macs = 0
    total_uplink = 0
    failed_switches = []

    for switch_id, hostname, ip, username, password in switches:
        mac_entries = discover_switch_ssh(switch_id, hostname, ip, username, password, uplinks)

        if mac_entries:
            saved, uplink_skipped = save_mac_locations(switch_id, mac_entries, uplinks)
            total_macs += saved
            total_uplink += uplink_skipped
            print(f"    Saved: {saved} endpoint MACs, skipped {uplink_skipped} uplink MACs")
        else:
            failed_switches.append(hostname)

    print()
    print("=" * 60)
    print(f"Discovery Complete!")
    print(f"  Total endpoint MACs saved: {total_macs}")
    print(f"  Total uplink MACs skipped: {total_uplink}")
    print(f"  Failed switches: {len(failed_switches)}")
    if failed_switches:
        for sw in failed_switches[:5]:
            print(f"    - {sw}")
        if len(failed_switches) > 5:
            print(f"    ... and {len(failed_switches) - 5} more")
    print("=" * 60)


if __name__ == "__main__":
    main()
