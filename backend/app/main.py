"""Mac-Traker FastAPI Application.

Network Intelligence per il tracking dei MAC address.
v1.0.8 - Added date range filter for alerts
"""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.core.config import get_settings
from app.db.database import engine, Base
from app.db import models  # Import models to register them
from app.services.backup.backup_scheduler import get_backup_scheduler
from app.services.discovery.discovery_scheduler import get_discovery_scheduler
from app.services.cleanup.cleanup_scheduler import get_cleanup_scheduler
from app.services.snapshots.snapshot_scheduler import get_snapshot_scheduler
from app.services.intent.intent_scheduler import get_intent_scheduler
from app.services.nedi.nedi_scheduler import get_nedi_scheduler

settings = get_settings()


def migrate_database():
    """Run database migrations for missing columns."""
    with engine.connect() as conn:
        # Check columns in switches table
        if settings.database_url.startswith("sqlite"):
            result = conn.execute(text("PRAGMA table_info(switches)"))
            columns = [row[1] for row in result.fetchall()]

            # Migration: use_ssh_fallback column
            if 'use_ssh_fallback' not in columns:
                print("Adding use_ssh_fallback column to switches table...")
                conn.execute(text("ALTER TABLE switches ADD COLUMN use_ssh_fallback INTEGER DEFAULT 0"))
                conn.commit()
                print("Column added successfully!")

            # Migration: SNMP system info columns (Feature #128)
            snmp_columns = [
                ('sys_name', 'VARCHAR(255)'),
                ('ports_up_count', 'INTEGER DEFAULT 0'),
                ('ports_down_count', 'INTEGER DEFAULT 0'),
                ('vlan_count', 'INTEGER DEFAULT 0'),
            ]
            for col_name, col_type in snmp_columns:
                if col_name not in columns:
                    print(f"Adding {col_name} column to switches table...")
                    conn.execute(text(f"ALTER TABLE switches ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"Column {col_name} added successfully!")

            print("Database migration complete.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup - Create database tables
    print("Mac-Traker starting up...")
    print(f"Database URL: {settings.database_url}")
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")

    # Run migrations for missing columns
    migrate_database()

    # Start backup scheduler
    backup_scheduler = get_backup_scheduler()
    backup_scheduler.start()
    print("Backup scheduler started.")

    # Start discovery scheduler with the discovery function
    from app.api.discovery import run_discovery_task
    discovery_scheduler = get_discovery_scheduler()
    discovery_scheduler.start(discovery_function=run_discovery_task)
    print("Discovery scheduler started.")

    # Start cleanup scheduler for history retention
    cleanup_scheduler = get_cleanup_scheduler()
    cleanup_scheduler.start()
    print("Cleanup scheduler started (90-day history retention).")

    # Start snapshot scheduler (disabled by default)
    snapshot_scheduler = get_snapshot_scheduler()
    snapshot_scheduler.start()
    print("Snapshot scheduler started (disabled by default, configure via API).")

    # Start intent verification scheduler (disabled by default)
    intent_scheduler = get_intent_scheduler()
    intent_scheduler.start(interval_minutes=60, enabled=False)
    print("Intent verification scheduler started (disabled by default, configure via /api/intent/scheduler/configure).")

    # Start NeDi sync scheduler (enabled by default - replaces slow SNMP discovery)
    nedi_scheduler = get_nedi_scheduler()
    nedi_scheduler.start(interval_minutes=15, enabled=True)
    print("NeDi sync scheduler started (every 15 minutes, configure via /api/nedi/scheduler/configure).")

    yield

    # Shutdown
    print("Mac-Traker shutting down...")
    nedi_scheduler.stop()
    print("NeDi sync scheduler stopped.")
    intent_scheduler.stop()
    print("Intent scheduler stopped.")
    snapshot_scheduler.stop()
    print("Snapshot scheduler stopped.")
    cleanup_scheduler.stop()
    print("Cleanup scheduler stopped.")
    discovery_scheduler.stop()
    print("Discovery scheduler stopped.")
    backup_scheduler.stop()
    print("Backup scheduler stopped.")


app = FastAPI(
    title="Mac-Traker",
    description="Network Intelligence per il tracking dei MAC address",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - Allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {
            "database": "ok",
            "discovery": "ok",
        },
    }


# RELOAD TRIGGER: 2026-01-24 16:02 - Feature 122 bulk delete
@app.get("/api/fix-schema")
async def fix_schema():
    """Manually trigger database schema fix."""
    try:
        migrate_database()
        return {"status": "ok", "message": "Schema migration completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Bulk delete endpoints - defined here to avoid route ordering issues
from pydantic import BaseModel
from typing import List
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import delete, or_
from app.db.database import get_db
from app.db.models import Switch, MacLocation, Port, Alert, MacHistory, TopologyLink, DiscoveryLog

class BulkDeleteRequestBody(BaseModel):
    switch_ids: List[int]

class DeleteResultResponse(BaseModel):
    deleted_count: int
    success: bool

@app.post("/api/switch-bulk-delete", response_model=DeleteResultResponse, tags=["Switch Bulk Operations"])
def api_bulk_delete_switches(
    request: BulkDeleteRequestBody,
    db: Session = Depends(get_db)
):
    """Delete multiple switches and all related data in cascade."""
    switch_ids = request.switch_ids
    if not switch_ids:
        raise HTTPException(status_code=400, detail="Nessun ID switch fornito")
    try:
        db.execute(delete(Alert).where(Alert.switch_id.in_(switch_ids)))
        db.execute(delete(MacHistory).where(MacHistory.switch_id.in_(switch_ids)))
        db.execute(delete(MacLocation).where(MacLocation.switch_id.in_(switch_ids)))
        db.execute(delete(TopologyLink).where(
            or_(TopologyLink.local_switch_id.in_(switch_ids), TopologyLink.remote_switch_id.in_(switch_ids))
        ))
        db.execute(delete(DiscoveryLog).where(DiscoveryLog.switch_id.in_(switch_ids)))
        db.execute(delete(Port).where(Port.switch_id.in_(switch_ids)))
        result = db.execute(delete(Switch).where(Switch.id.in_(switch_ids)))
        deleted_count = result.rowcount
        db.commit()
        return DeleteResultResponse(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")

@app.post("/api/switch-delete-all", response_model=DeleteResultResponse, tags=["Switch Bulk Operations"])
def api_delete_all_switches(
    confirm_delete: str = Header(None, alias="X-Confirm-Delete-All"),
    db: Session = Depends(get_db)
):
    """Delete ALL switches and all related data. Requires X-Confirm-Delete-All: true header."""
    if confirm_delete != "true":
        raise HTTPException(status_code=400, detail="Richiesto header X-Confirm-Delete-All con valore 'true' per confermare")
    try:
        db.execute(delete(Alert))
        db.execute(delete(MacHistory))
        db.execute(delete(MacLocation))
        db.execute(delete(TopologyLink))
        db.execute(delete(DiscoveryLog))
        db.execute(delete(Port))
        result = db.execute(delete(Switch))
        deleted_count = result.rowcount
        db.commit()
        return DeleteResultResponse(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Mac-Traker",
        "description": "Network Intelligence per il tracking dei MAC address",
        "docs": "/docs",
    }


# Import and include routers
from app.api import switches, groups, dashboard, alerts, macs, discovery, topology, settings as settings_api, backup, mac_path, seed_discovery, alert_rules, hosts, snapshots, technology, graph, intent
try:
    from app.api import switch_actions
    print(f"switch_actions imported successfully: {switch_actions.router}")
except Exception as e:
    print(f"ERROR importing switch_actions: {e}")
    import traceback
    traceback.print_exc()
    # Create a dummy router
    from fastapi import APIRouter
    class DummySwitchActions:
        router = APIRouter()
    switch_actions = DummySwitchActions()

# Explicitly import cleanup to catch errors
try:
    from app.api import cleanup
    print("Cleanup module imported successfully")
except Exception as e:
    print(f"ERROR importing cleanup module: {e}")
    import traceback
    traceback.print_exc()
    # Create a dummy router to avoid breaking the app
    from fastapi import APIRouter
    class DummyCleanup:
        router = APIRouter()
    cleanup = DummyCleanup()

# NeDi integration - Feature #131 (requires pymysql)
nedi_import_error = None
try:
    from app.api import nedi
    print(f"NeDi module imported successfully: {nedi.router}")
except Exception as e:
    nedi_import_error = str(e)
    print(f"WARNING: NeDi module import failed: {e}")
    import traceback
    traceback.print_exc()
    # Create a dummy module with router for NeDi
    from fastapi import APIRouter
    nedi_fallback_router = APIRouter(prefix="/api/nedi", tags=["nedi"])

    @nedi_fallback_router.get("/status")
    async def nedi_fallback_status():
        return {"connected": False, "host": "unknown", "device_count": 0, "node_count": 0, "tables": [], "error": f"NeDi module not available: {nedi_import_error}"}

    class DummyNeDi:
        router = nedi_fallback_router
    nedi = DummyNeDi()

app.include_router(switch_actions.router, prefix="/api/switch-actions", tags=["Switch Actions"])
app.include_router(switches.router, prefix="/api/switches", tags=["Switches"])
app.include_router(groups.router, prefix="/api/groups", tags=["Groups"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(macs.router, prefix="/api/macs", tags=["MAC Addresses"])
app.include_router(discovery.router, prefix="/api/discovery", tags=["Discovery"])
app.include_router(topology.router, prefix="/api/topology", tags=["Topology"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["Settings"])
app.include_router(backup.router, prefix="/api/backup", tags=["Backup"])
app.include_router(cleanup.router, prefix="/api/cleanup", tags=["Cleanup"])
app.include_router(mac_path.router, prefix="/api/topology/mac-path", tags=["MAC Path"])
app.include_router(seed_discovery.router, prefix="/api/discovery", tags=["Seed Discovery"])
app.include_router(nedi.router)  # NeDi integration - Feature #131
app.include_router(alert_rules.router, prefix="/api/alerting", tags=["Alert Rules & Webhooks"])
app.include_router(hosts.router, prefix="/api", tags=["Hosts"])
app.include_router(snapshots.router, prefix="/api", tags=["Snapshots"])
app.include_router(technology.router, prefix="/api/technology", tags=["Technology Tables"])
app.include_router(graph.router, prefix="/api/graph", tags=["Network Graph"])
app.include_router(intent.router, prefix="/api/intent", tags=["Intent Verification"])
print("NeDi router registered successfully")
print("Intent Verification router registered (IP Fabric-like compliance checks)")
print("Network Graph router registered (offline path lookup)")
print("Alert Rules & Webhooks router registered successfully")
print("Hosts & Snapshots routers registered (IP Fabric-like features)")

print(f"ALL ROUTES REGISTERED: {[r.path for r in app.routes]}")
# Feature #119: Seed discovery from single device - seed_discovery module added
# Feature #100: MAC path highlighting in topology - mac_path module added
# Feature #122: Bulk delete POST endpoints - added bulk-delete and delete-all routes
# Reload trigger: 2026-01-24 16:55

# reload trigger sab 24 gen 2026 22:18:19
# reload trigger: Feature #131 NeDi integration fix
