#!/usr/bin/env python3
"""
Script to detect uplink ports using LLDP and mark them in the database.

Uplink ports are ports that connect to another network device (switch, router, AP).
These ports should be excluded from MAC endpoint search results.

Run from the backend directory:
    python scripts/detect_uplink_ports.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netmiko import ConnectHandler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sqlite3
import re


def get_switch_credentials():
    """Get switch credentials from database."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mactraker.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.hostname, s.ip_address, g.ssh_username, g.ssh_password_encrypted
        FROM switches s
        JOIN switch_groups g ON s.group_id = g.id
        WHERE s.is_active = 1
    """)

    switches = cursor.fetchall()
    conn.close()
    return switches


def get_lldp_neighbors(ip, username, password):
    """Get LLDP neighbors from a switch."""
    device = {
        "device_type": "huawei",
        "host": ip,
        "username": username,
        "password": password,
        "port": 22,
        "timeout": 15,
    }

    uplink_ports = []

    try:
        conn = ConnectHandler(**device)
        output = conn.send_command("display lldp neighbor brief")

        # Parse LLDP output
        # Format: Local Intf    Neighbor Dev             Neighbor Intf             Exptime(s)
        for line in output.split("\n"):
            if line.strip() and not line.startswith("Local") and not line.startswith("-"):
                parts = line.split()
                if len(parts) >= 3:
                    local_port = parts[0]
                    neighbor_dev = parts[1]

                    # If neighbor device name contains switch/router indicators, it's an uplink
                    # Also check if neighbor interface is a switch port (GE, XGE, 40GE, etc.)
                    neighbor_intf = parts[2] if len(parts) > 2 else ""

                    # This port has a LLDP neighbor -> it's connected to another network device
                    # Mark as uplink if neighbor is NOT an AP (mgt0 interface indicates AP)
                    if neighbor_intf != "mgt0":
                        uplink_ports.append(local_port)

        conn.disconnect()
    except Exception as e:
        print(f"  Error connecting to {ip}: {e}")

    return uplink_ports


def normalize_port_name(port_name):
    """Normalize port name for database comparison."""
    # GE0/0/27 -> GigabitEthernet0/0/27
    if port_name.startswith("GE"):
        return port_name.replace("GE", "GigabitEthernet")
    elif port_name.startswith("XGE"):
        return port_name.replace("XGE", "XGigabitEthernet")
    elif port_name.startswith("40GE"):
        return port_name.replace("40GE", "40GigabitEthernet")
    elif port_name.startswith("100GE"):
        return port_name.replace("100GE", "100GigabitEthernet")
    return port_name


def update_uplink_ports(switch_id, uplink_ports):
    """Update port is_uplink flag in database."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mactraker.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    updated = 0
    for port_name in uplink_ports:
        normalized = normalize_port_name(port_name)
        cursor.execute("""
            UPDATE ports
            SET is_uplink = 1
            WHERE switch_id = ? AND (port_name = ? OR port_name = ?)
            AND is_uplink = 0
        """, (switch_id, port_name, normalized))
        if cursor.rowcount > 0:
            updated += cursor.rowcount

    conn.commit()
    conn.close()
    return updated


def main():
    print("=" * 60)
    print("LLDP-Based Uplink Port Detection")
    print("=" * 60)

    switches = get_switch_credentials()
    print(f"Found {len(switches)} switches to scan\n")

    total_uplinks_found = 0
    total_updated = 0

    for switch_id, hostname, ip, username, password in switches:
        print(f"Scanning {hostname} ({ip})...")

        uplink_ports = get_lldp_neighbors(ip, username, password)

        if uplink_ports:
            print(f"  Found {len(uplink_ports)} LLDP neighbors: {', '.join(uplink_ports)}")
            total_uplinks_found += len(uplink_ports)

            updated = update_uplink_ports(switch_id, uplink_ports)
            if updated > 0:
                print(f"  Updated {updated} ports as uplinks")
                total_updated += updated
        else:
            print(f"  No LLDP neighbors found")

    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Total uplink ports detected: {total_uplinks_found}")
    print(f"  New ports marked as uplink: {total_updated}")
    print("=" * 60)


if __name__ == "__main__":
    main()
