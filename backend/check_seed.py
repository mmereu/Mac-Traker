#!/usr/bin/env python
"""Check if seed endpoint imports correctly."""
try:
    from app.api.discovery import seed_discovery, SeedDiscoveryRequest, SeedDiscoveryResult
    print("SUCCESS: seed_discovery imports correctly")
    print(f"SeedDiscoveryRequest fields: {SeedDiscoveryRequest.model_fields.keys()}")
    print(f"SeedDiscoveryResult fields: {SeedDiscoveryResult.model_fields.keys()}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
