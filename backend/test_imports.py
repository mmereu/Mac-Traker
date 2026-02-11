#!/usr/bin/env python
"""Test if all API modules can be imported."""
import sys
sys.path.insert(0, '.')

try:
    from app.api import switches
    print("✓ switches")
except Exception as e:
    print(f"✗ switches: {e}")

try:
    from app.api import groups
    print("✓ groups")
except Exception as e:
    print(f"✗ groups: {e}")

try:
    from app.api import dashboard
    print("✓ dashboard")
except Exception as e:
    print(f"✗ dashboard: {e}")

try:
    from app.api import alerts
    print("✓ alerts")
except Exception as e:
    print(f"✗ alerts: {e}")

try:
    from app.api import macs
    print("✓ macs")
except Exception as e:
    print(f"✗ macs: {e}")

try:
    from app.api import discovery
    print("✓ discovery")
except Exception as e:
    print(f"✗ discovery: {e}")

try:
    from app.api import topology
    print("✓ topology")
except Exception as e:
    print(f"✗ topology: {e}")

try:
    from app.api import settings
    print("✓ settings")
except Exception as e:
    print(f"✗ settings: {e}")

try:
    from app.api import backup
    print("✓ backup")
except Exception as e:
    print(f"✗ backup: {e}")

print("\nDone testing imports")
