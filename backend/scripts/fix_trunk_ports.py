#!/usr/bin/env python3
"""
Script to fix existing Eth-Trunk ports that are not marked as uplinks.

This script updates all ports containing 'trunk', 'eth-trunk', 'port-channel',
'lag', or 'bond' in their name to have is_uplink=True and port_type='trunk'.

Run from the backend directory:
    python scripts/fix_trunk_ports.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models import Port


def fix_trunk_ports():
    """Update all trunk ports to be marked as uplinks."""

    # Create database connection
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Find all ports that look like trunks but aren't marked as uplinks
        trunk_keywords = ['trunk', 'eth-trunk', 'port-channel', 'po', 'lag', 'bond']

        # Build OR conditions for each keyword
        conditions = []
        for keyword in trunk_keywords:
            conditions.append(Port.port_name.ilike(f'%{keyword}%'))

        # Query ports matching any keyword AND not already marked as uplink
        ports_to_fix = db.query(Port).filter(
            or_(*conditions),
            or_(Port.is_uplink == False, Port.is_uplink.is_(None))
        ).all()

        print(f"Found {len(ports_to_fix)} trunk ports not marked as uplinks")

        if not ports_to_fix:
            print("No ports to fix!")
            return

        # Show what will be updated
        print("\nPorts to be updated:")
        print("-" * 60)
        for port in ports_to_fix[:20]:  # Show first 20
            print(f"  Switch ID {port.switch_id}: {port.port_name} (is_uplink={port.is_uplink}, type={port.port_type})")

        if len(ports_to_fix) > 20:
            print(f"  ... and {len(ports_to_fix) - 20} more")

        # Ask for confirmation
        print("\n" + "=" * 60)
        response = input("Do you want to update these ports? (yes/no): ").strip().lower()

        if response != 'yes':
            print("Aborted.")
            return

        # Update the ports
        updated_count = 0
        for port in ports_to_fix:
            port.is_uplink = True
            port.port_type = "trunk"
            updated_count += 1

        db.commit()
        print(f"\nSuccessfully updated {updated_count} ports!")

        # Verify the fix
        remaining = db.query(Port).filter(
            or_(*conditions),
            or_(Port.is_uplink == False, Port.is_uplink.is_(None))
        ).count()

        print(f"Remaining trunk ports not marked as uplinks: {remaining}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Trunk Port Fixer - Mark Eth-Trunk ports as uplinks")
    print("=" * 60)
    print()
    fix_trunk_ports()
