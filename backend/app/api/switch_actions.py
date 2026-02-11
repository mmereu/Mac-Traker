"""Switch action endpoints (bulk operations)."""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import delete, or_

from app.db.database import get_db
from app.db.models import Switch, MacLocation, Port, Alert, MacHistory, TopologyLink, DiscoveryLog
from app.api.schemas import DeleteResult, BulkDeleteRequest

router = APIRouter()


@router.post("/bulk-delete", response_model=DeleteResult)
def bulk_delete_switches(
    request: BulkDeleteRequest,
    db: Session = Depends(get_db)
):
    """Delete multiple switches and all related data in cascade."""
    switch_ids = request.switch_ids

    if not switch_ids:
        raise HTTPException(status_code=400, detail="Nessun ID switch fornito")

    try:
        # Delete related data in order (cascade)
        db.execute(delete(Alert).where(Alert.switch_id.in_(switch_ids)))
        db.execute(delete(MacHistory).where(MacHistory.switch_id.in_(switch_ids)))
        db.execute(delete(MacLocation).where(MacLocation.switch_id.in_(switch_ids)))
        db.execute(delete(TopologyLink).where(
            or_(
                TopologyLink.local_switch_id.in_(switch_ids),
                TopologyLink.remote_switch_id.in_(switch_ids)
            )
        ))
        db.execute(delete(DiscoveryLog).where(DiscoveryLog.switch_id.in_(switch_ids)))
        db.execute(delete(Port).where(Port.switch_id.in_(switch_ids)))
        result = db.execute(delete(Switch).where(Switch.id.in_(switch_ids)))
        deleted_count = result.rowcount

        db.commit()
        return DeleteResult(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")


@router.post("/delete-all", response_model=DeleteResult)
def delete_all_switches(
    confirm_delete: str = Header(None, alias="X-Confirm-Delete-All"),
    db: Session = Depends(get_db)
):
    """Delete ALL switches and all related data. Requires confirmation header."""
    if confirm_delete != "true":
        raise HTTPException(
            status_code=400,
            detail="Richiesto header X-Confirm-Delete-All con valore 'true' per confermare"
        )

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
        return DeleteResult(deleted_count=deleted_count, success=True)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante la cancellazione: {str(e)}")
