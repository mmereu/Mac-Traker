"""Test topology import."""
try:
    from app.api import topology
    print("OK - topology imported successfully")
    print(f"Router: {topology.router}")
    print(f"Routes: {[r.path for r in topology.router.routes]}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
