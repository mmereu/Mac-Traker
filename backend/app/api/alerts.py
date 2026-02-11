"""Alerts API endpoints."""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db.models import Alert, MacAddress, Switch, Port, MacHistory
from app.api.schemas import AlertResponse, AlertListResponse

router = APIRouter()


@router.get("", response_model=AlertListResponse)
def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    alert_type: Optional[str] = None,
    is_read: Optional[bool] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all alerts with optional filtering.

    Args:
        date_from: Filter alerts from this date (ISO format YYYY-MM-DD)
        date_to: Filter alerts until this date (ISO format YYYY-MM-DD)
    """
    query = db.query(Alert)

    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)

    if is_read is not None:
        query = query.filter(Alert.is_read == is_read)

    # Date range filtering
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Alert.created_at >= from_date)
        except ValueError:
            pass  # Ignore invalid date format

    if date_to:
        try:
            # Add 1 day to include the entire end date
            to_date = datetime.strptime(date_to, "%Y-%m-%d")
            to_date = to_date.replace(hour=23, minute=59, second=59)
            query = query.filter(Alert.created_at <= to_date)
        except ValueError:
            pass  # Ignore invalid date format

    total = query.count()
    unread_count = db.query(func.count(Alert.id)).filter(Alert.is_read == False).scalar() or 0

    alerts = query.order_by(Alert.created_at.desc()).offset(skip).limit(limit).all()

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        unread_count=unread_count,
    )


@router.get("/unread", response_model=AlertListResponse)
def list_unread_alerts(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List unread alerts."""
    query = db.query(Alert).filter(Alert.is_read == False)

    total = query.count()
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        unread_count=total,
    )


@router.put("/{alert_id}/read")
def mark_alert_read(alert_id: int, db: Session = Depends(get_db)):
    """Mark an alert as read."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert non trovato")

    alert.is_read = True
    db.commit()

    return {"message": "Alert marcato come letto"}


@router.put("/read-all")
def mark_all_alerts_read(db: Session = Depends(get_db)):
    """Mark all alerts as read."""
    db.query(Alert).filter(Alert.is_read == False).update({"is_read": True})
    db.commit()

    return {"message": "Tutti gli alert marcati come letti"}


# REMOVED: seed-demo-data endpoint
# Demo endpoints were removed as part of Feature #126 to ensure
# the application only uses real data from SNMP/SSH discovery


@router.post("/create-mac-move-alert")
def create_mac_move_alert_test(
    mac_id: int,
    old_switch_id: int,
    old_port_id: int,
    new_switch_id: int,
    new_port_id: int,
    db: Session = Depends(get_db)
):
    """Create a MAC movement alert for testing the alert feature."""
    # Get MAC address
    mac = db.query(MacAddress).filter(MacAddress.id == mac_id).first()
    if not mac:
        raise HTTPException(status_code=404, detail="MAC non trovato")

    # Get switches and ports
    old_switch = db.query(Switch).filter(Switch.id == old_switch_id).first()
    old_port = db.query(Port).filter(Port.id == old_port_id).first()
    new_switch = db.query(Switch).filter(Switch.id == new_switch_id).first()
    new_port = db.query(Port).filter(Port.id == new_port_id).first()

    if not all([old_switch, old_port, new_switch, new_port]):
        raise HTTPException(status_code=404, detail="Switch o porta non trovati")

    # Create movement alert
    message = (
        f"MAC {mac.mac_address} spostato da "
        f"{old_switch.hostname}:{old_port.port_name} a "
        f"{new_switch.hostname}:{new_port.port_name}"
    )

    alert = Alert(
        alert_type="mac_move",
        mac_id=mac.id,
        switch_id=new_switch.id,
        port_id=new_port.id,
        message=message,
        severity="warning",
        is_read=False,
        is_notified=False,
        created_at=datetime.utcnow(),
    )
    db.add(alert)

    # Also create history entry for completeness
    history = MacHistory(
        mac_id=mac.id,
        switch_id=new_switch.id,
        port_id=new_port.id,
        event_type="move",
        event_at=datetime.utcnow(),
        previous_switch_id=old_switch.id,
        previous_port_id=old_port.id,
    )
    db.add(history)

    db.commit()

    return {
        "message": "Alert di movimento creato",
        "alert_id": alert.id,
        "alert_message": message,
        "mac_address": mac.mac_address,
        "old_location": f"{old_switch.hostname}:{old_port.port_name}",
        "new_location": f"{new_switch.hostname}:{new_port.port_name}"
    }
