"""Test import of seed discovery endpoint."""
try:
    from app.api.discovery import seed_discovery, SeedDiscoveryRequest, SeedDiscoveryResult
    print("SUCCESS: seed_discovery imports correctly")
    print(f"SeedDiscoveryRequest fields: {list(SeedDiscoveryRequest.model_fields.keys())}")
    print(f"SeedDiscoveryResult fields: {list(SeedDiscoveryResult.model_fields.keys())}")
except Exception as e:
    print(f"ERROR importing seed_discovery: {e}")
    import traceback
    traceback.print_exc()
