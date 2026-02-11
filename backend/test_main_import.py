"""Test main.py imports."""
import sys
sys.path.insert(0, '.')

print("Testing main.py import...")
try:
    from app import main
    print("Main imported successfully")
    print(f"App: {main.app}")
    print(f"Routes: {[r.path for r in main.app.routes]}")
except Exception as e:
    print(f"ERROR importing main: {e}")
    import traceback
    traceback.print_exc()
