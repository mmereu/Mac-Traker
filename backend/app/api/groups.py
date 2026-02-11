"""Switch Groups API endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.db.models import Switch, SwitchGroup
from app.api.schemas import (
    SwitchGroupCreate,
    SwitchGroupUpdate,
    SwitchGroupResponse,
    SwitchGroupListResponse,
)

router = APIRouter()


def get_group_with_count(db: Session, group: SwitchGroup) -> dict:
    """Get group data with switch_count."""
    switch_count = db.query(func.count(Switch.id)).filter(
        Switch.group_id == group.id
    ).scalar() or 0

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "ssh_username": group.ssh_username,
        "ssh_port": group.ssh_port,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "switch_count": switch_count,
    }


@router.get("", response_model=SwitchGroupListResponse)
def list_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all switch groups."""
    query = db.query(SwitchGroup)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (SwitchGroup.name.ilike(search_term)) |
            (SwitchGroup.description.ilike(search_term))
        )

    total = query.count()
    groups = query.order_by(SwitchGroup.name).offset(skip).limit(limit).all()

    items = [get_group_with_count(db, g) for g in groups]

    return SwitchGroupListResponse(items=items, total=total)


@router.post("", response_model=SwitchGroupResponse, status_code=201)
def create_group(group_data: SwitchGroupCreate, db: Session = Depends(get_db)):
    """Create a new switch group."""
    # Check for duplicate name
    existing = db.query(SwitchGroup).filter(SwitchGroup.name == group_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Gruppo con questo nome esiste gia'")

    # Encrypt password if provided (placeholder - should use proper encryption)
    data = group_data.model_dump()
    if data.get("ssh_password"):
        data["ssh_password_encrypted"] = data.pop("ssh_password")  # Should encrypt this
    else:
        data.pop("ssh_password", None)

    group = SwitchGroup(**data)
    db.add(group)
    db.commit()
    db.refresh(group)

    return get_group_with_count(db, group)


@router.get("/{group_id}", response_model=SwitchGroupResponse)
def get_group(group_id: int, db: Session = Depends(get_db)):
    """Get a specific group by ID."""
    group = db.query(SwitchGroup).filter(SwitchGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")

    return get_group_with_count(db, group)


@router.put("/{group_id}", response_model=SwitchGroupResponse)
def update_group(group_id: int, group_data: SwitchGroupUpdate, db: Session = Depends(get_db)):
    """Update a switch group."""
    group = db.query(SwitchGroup).filter(SwitchGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")

    update_data = group_data.model_dump(exclude_unset=True)

    # Check for duplicate name if updating
    if "name" in update_data and update_data["name"] != group.name:
        existing = db.query(SwitchGroup).filter(
            SwitchGroup.name == update_data["name"],
            SwitchGroup.id != group_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Gruppo con questo nome esiste gia'")

    # Handle password update
    if "ssh_password" in update_data:
        if update_data["ssh_password"]:
            update_data["ssh_password_encrypted"] = update_data.pop("ssh_password")
        else:
            update_data.pop("ssh_password")

    for field, value in update_data.items():
        setattr(group, field, value)

    db.commit()
    db.refresh(group)

    return get_group_with_count(db, group)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    """Delete a switch group."""
    group = db.query(SwitchGroup).filter(SwitchGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")

    # Check if any switches are using this group
    switch_count = db.query(func.count(Switch.id)).filter(
        Switch.group_id == group_id
    ).scalar()

    if switch_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Impossibile eliminare: {switch_count} switch usano questo gruppo"
        )

    db.delete(group)
    db.commit()
    return None
