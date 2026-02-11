#!/usr/bin/env python3
"""
Cleanup script to remove invalid ports created by the SNMP parsing bug.
Removes ports with:
- Binary/non-printable characters in name
- Numeric-only names (like "1", "65535")
- Invalid port names that don't match standard naming conventions
"""

import sqlite3
import re
import sys

DB_PATH = "mactraker.db"

def is_valid_port_name(name: str) -> bool:
    """Check if port name is valid (standard Huawei/Cisco naming)"""
    if not name:
        return False

    # Must be printable ASCII
    if not name.isprintable():
        return False

    # Valid prefixes for port names
    valid_prefixes = (
        'GigabitEthernet', 'Gi', 'Gig',
        'XGigabitEthernet', 'XGi', 'Ten',
        'Ethernet', 'Eth',
        'FastEthernet', 'Fa',
        '100GE', '40GE', '25GE', '10GE',
        'Vlanif', 'LoopBack', 'NULL',
        'MEth', 'Stack-Port',
        'Tunnel', 'Bridge-Aggregation', 'Eth-Trunk'
    )

    # Check if starts with valid prefix
    if name.startswith(valid_prefixes):
        return True

    # Reject pure numbers
    if name.isdigit():
        return False

    # Reject hex strings (likely MAC addresses)
    if re.match(r'^[0-9a-fA-F]{6,}$', name):
        return False

    # Reject very short names
    if len(name) < 3:
        return False

    return False  # Default to invalid for safety

def main():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all ports
    cursor.execute("SELECT id, switch_id, port_name FROM ports")
    all_ports = cursor.fetchall()
    print(f"Total ports in database: {len(all_ports)}")

    # Find invalid ports
    invalid_ports = []
    valid_count = 0

    for port_id, switch_id, port_name in all_ports:
        if is_valid_port_name(port_name):
            valid_count += 1
        else:
            invalid_ports.append((port_id, switch_id, port_name))

    print(f"Valid ports: {valid_count}")
    print(f"Invalid ports to delete: {len(invalid_ports)}")

    if not invalid_ports:
        print("No invalid ports found. Database is clean.")
        return

    # Show sample of invalid ports
    print("\nSample invalid ports:")
    for port_id, switch_id, port_name in invalid_ports[:20]:
        display_name = repr(port_name) if not port_name.isprintable() else port_name
        print(f"  ID {port_id} (switch {switch_id}): {display_name[:50]}")

    if len(invalid_ports) > 20:
        print(f"  ... and {len(invalid_ports) - 20} more")

    # Ask for confirmation
    response = input(f"\nDelete {len(invalid_ports)} invalid ports? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return

    # Delete invalid ports - process in batches to avoid SQL limits
    port_ids = [p[0] for p in invalid_ports]
    batch_size = 500

    total_deleted_locations = 0
    total_deleted_history = 0
    total_deleted_links = 0

    for i in range(0, len(port_ids), batch_size):
        batch = port_ids[i:i + batch_size]
        placeholders = ','.join('?' * len(batch))

        # Delete mac_locations referencing these ports
        cursor.execute(f"DELETE FROM mac_locations WHERE port_id IN ({placeholders})", batch)
        total_deleted_locations += cursor.rowcount

        # Delete mac_history referencing these ports
        cursor.execute(f"DELETE FROM mac_history WHERE port_id IN ({placeholders})", batch)
        total_deleted_history += cursor.rowcount

        # Delete topology_links
        cursor.execute(f"DELETE FROM topology_links WHERE local_port_id IN ({placeholders}) OR remote_port_id IN ({placeholders})", batch + batch)
        total_deleted_links += cursor.rowcount

        if (i + batch_size) % 2000 == 0:
            print(f"  Processed {i + batch_size} ports...")

    print(f"  Deleted {total_deleted_locations} mac_locations")
    print(f"  Deleted {total_deleted_history} mac_history records")
    print(f"  Deleted {total_deleted_links} topology_links")

    # Delete the invalid ports
    print("Deleting invalid ports...")
    cursor.execute(f"DELETE FROM ports WHERE id IN ({','.join('?' * len(port_ids))})", port_ids)
    deleted_ports = cursor.rowcount
    print(f"  Deleted {deleted_ports} ports")

    # Commit
    conn.commit()
    print("\nCleanup completed successfully!")

    # Show final counts
    cursor.execute("SELECT COUNT(*) FROM ports")
    final_count = cursor.fetchone()[0]
    print(f"Remaining ports in database: {final_count}")

    conn.close()

if __name__ == "__main__":
    main()
