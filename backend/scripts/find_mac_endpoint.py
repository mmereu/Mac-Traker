#!/usr/bin/env python3
"""Find real endpoint for a specific MAC address."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netmiko import ConnectHandler
import sqlite3

def main():
    mac_to_find = sys.argv[1] if len(sys.argv) > 1 else "0001-2e7c-7194"

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mactraker.db")
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    # Get switches
    cursor.execute("""
        SELECT s.id, s.hostname, s.ip_address, g.ssh_username, g.ssh_password_encrypted
        FROM switches s
        JOIN switch_groups g ON s.group_id = g.id
        WHERE s.is_active = 1
    """)
    switches = cursor.fetchall()

    # Get uplink ports per switch
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

    print(f"Cercando MAC {mac_to_find} su {len(switches)} switch...")
    print("=" * 60)

    endpoints = []
    uplink_locations = []

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
            output = conn.send_command(f"display mac-address | include {mac_to_find}", read_timeout=10)
            conn.disconnect()

            if mac_to_find in output:
                for line in output.split("\n"):
                    if mac_to_find in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            port = parts[2]
                            is_uplink = port in uplinks.get(sid, set())

                            if is_uplink:
                                uplink_locations.append((hostname, port))
                                print(f"  {hostname}: {port} -> UPLINK")
                            else:
                                endpoints.append((hostname, port))
                                print(f"  {hostname}: {port} -> ENDPOINT")
        except Exception as e:
            err_msg = str(e)[:40]
            if "Authentication" not in err_msg:
                print(f"  {hostname}: Error - {err_msg}")

    print("=" * 60)
    if endpoints:
        print(f"\nREAL ENDPOINT FOUND: {endpoints[0][0]}:{endpoints[0][1]}")
    else:
        print(f"\nNO ENDPOINT FOUND!")
        print(f"MAC visible on {len(uplink_locations)} uplink ports")
        print("This device is NOT directly connected to any monitored switch")

if __name__ == "__main__":
    main()
