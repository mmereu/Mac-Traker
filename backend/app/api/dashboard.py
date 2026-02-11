"""Dashboard API endpoints."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.db.database import get_db
from app.db.models import MacAddress, Switch, Alert, DiscoveryLog
from app.api.schemas import DashboardStats

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics."""
    # Count active MACs
    mac_count = db.query(func.count(MacAddress.id)).filter(
        MacAddress.is_active == True
    ).scalar() or 0

    # Count active switches
    switch_count = db.query(func.count(Switch.id)).filter(
        Switch.is_active == True
    ).scalar() or 0

    # Count unread alerts
    alert_count = db.query(func.count(Alert.id)).filter(
        Alert.is_read == False
    ).scalar() or 0

    # Get last discovery timestamp
    last_log = db.query(DiscoveryLog).filter(
        DiscoveryLog.status == "success"
    ).order_by(DiscoveryLog.completed_at.desc()).first()

    last_discovery = last_log.completed_at if last_log else None

    return DashboardStats(
        mac_count=mac_count,
        switch_count=switch_count,
        alert_count=alert_count,
        last_discovery=last_discovery,
    )


@router.get("/mac-breakdown")
def get_mac_breakdown(db: Session = Depends(get_db)):
    """Get MAC count breakdown by type: real (globally unique), random (locally administered), multicast."""
    # Locally Administered bit = second hex char in {2,3,6,7,A,B,E,F,a,b,e,f}
    # We use substr on mac_address field (format: XX:XX:XX:XX:XX:XX)
    la_chars = ('2', '3', '6', '7', 'A', 'B', 'E', 'F', 'a', 'b', 'e', 'f')

    total = db.query(func.count(MacAddress.id)).filter(
        MacAddress.is_active == True
    ).scalar() or 0

    # Multicast MACs (first byte odd = bit 0 set, or well-known prefixes)
    multicast = db.query(func.count(MacAddress.id)).filter(
        MacAddress.is_active == True,
        MacAddress.mac_address.op('LIKE')('01:%')
        | MacAddress.mac_address.op('LIKE')('33:33:%')
        | MacAddress.mac_address.op('LIKE')('FF:FF:FF%')
        | MacAddress.mac_address.op('LIKE')('01:00:5E%')
        | MacAddress.mac_address.op('LIKE')('01:80:C2%')
    ).scalar() or 0

    # Locally Administered (random) - check second hex character
    random_count = db.query(func.count(MacAddress.id)).filter(
        MacAddress.is_active == True,
        func.substr(MacAddress.mac_address, 2, 1).in_(la_chars)
    ).scalar() or 0

    real_count = total - random_count - multicast

    return {
        "total": total,
        "real": real_count,
        "random": random_count,
        "multicast": multicast,
    }


@router.get("/top-switches")
def get_top_switches(
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """Get top switches by MAC count."""
    from app.db.models import MacLocation

    results = (
        db.query(
            Switch.id,
            Switch.hostname,
            func.count(MacLocation.id).label("mac_count")
        )
        .outerjoin(MacLocation, (MacLocation.switch_id == Switch.id) & (MacLocation.is_current == True))
        .filter(Switch.is_active == True)
        .group_by(Switch.id, Switch.hostname)
        .order_by(func.count(MacLocation.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {"id": r.id, "hostname": r.hostname, "mac_count": r.mac_count}
        for r in results
    ]


@router.get("/trends")
def get_mac_trends(
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Get MAC count trends over time."""
    from app.db.models import MacHistory

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Get new MACs per day
    results = (
        db.query(
            func.date(MacHistory.event_at).label("date"),
            func.count(MacHistory.id).label("count")
        )
        .filter(
            MacHistory.event_at >= start_date,
            MacHistory.event_type == "new"
        )
        .group_by(func.date(MacHistory.event_at))
        .order_by(func.date(MacHistory.event_at))
        .all()
    )

    return [
        {"date": str(r.date), "count": r.count}
        for r in results
    ]


@router.get("/stats-by-site")
def get_stats_by_site(db: Session = Depends(get_db)):
    """Get statistics grouped by site code (extracted from hostname prefix)."""
    from app.db.models import MacLocation

    # Get switches with their site codes and MAC counts
    results = (
        db.query(
            Switch.site_code,
            func.count(Switch.id.distinct()).label("switch_count"),
            func.count(MacLocation.id).label("mac_count")
        )
        .outerjoin(MacLocation, (MacLocation.switch_id == Switch.id) & (MacLocation.is_current == True))
        .filter(Switch.is_active == True, Switch.site_code.isnot(None))
        .group_by(Switch.site_code)
        .order_by(Switch.site_code)
        .all()
    )

    sites = []
    for r in results:
        sites.append({
            "site_code": r.site_code,
            "site_name": f"Sede {r.site_code}",
            "switch_count": r.switch_count,
            "mac_count": r.mac_count
        })

    # Get totals for switches without site code
    no_site = (
        db.query(
            func.count(Switch.id.distinct()).label("switch_count"),
            func.count(MacLocation.id).label("mac_count")
        )
        .outerjoin(MacLocation, (MacLocation.switch_id == Switch.id) & (MacLocation.is_current == True))
        .filter(Switch.is_active == True, Switch.site_code.is_(None))
        .first()
    )

    return {
        "sites": sites,
        "total_sites": len(sites),
        "switches_without_site": no_site.switch_count if no_site else 0,
        "macs_without_site": no_site.mac_count if no_site else 0
    }
