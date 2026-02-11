"""MAC history cleanup service for Mac-Traker.

Provides automatic cleanup of old MAC history records based on retention policy.
Default retention is 90 days as per project specification.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.db.models import MacHistory
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


class HistoryCleanupService:
    """Service for cleaning up old MAC history records."""

    def __init__(self, retention_days: int = 90):
        """Initialize cleanup service.

        Args:
            retention_days: Number of days to retain history. Default is 90.
        """
        self.retention_days = retention_days
        self._last_cleanup_result: Optional[Dict[str, Any]] = None

    def set_retention_days(self, days: int):
        """Update the retention period.

        Args:
            days: New retention period in days (minimum 1)
        """
        self.retention_days = max(1, days)
        logger.info(f"History retention set to {self.retention_days} days")

    def get_retention_days(self) -> int:
        """Get the current retention period in days."""
        return self.retention_days

    def cleanup_old_history(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Remove MAC history records older than retention period.

        Args:
            db: Optional database session. If not provided, creates a new one.

        Returns:
            Dict with cleanup results (deleted_count, cutoff_date, etc.)
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)

            # Count records to be deleted
            count_before = db.query(func.count(MacHistory.id)).filter(
                MacHistory.event_at < cutoff_date
            ).scalar() or 0

            if count_before == 0:
                result = {
                    "success": True,
                    "deleted_count": 0,
                    "retention_days": self.retention_days,
                    "cutoff_date": cutoff_date.isoformat(),
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": "Nessun record da eliminare"
                }
                self._last_cleanup_result = result
                logger.info(f"No history records older than {self.retention_days} days to clean up")
                return result

            # Delete old records
            delete_stmt = delete(MacHistory).where(MacHistory.event_at < cutoff_date)
            result_proxy = db.execute(delete_stmt)
            db.commit()

            deleted_count = result_proxy.rowcount

            result = {
                "success": True,
                "deleted_count": deleted_count,
                "retention_days": self.retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"Eliminati {deleted_count} record di storico"
            }
            self._last_cleanup_result = result

            logger.info(f"Cleaned up {deleted_count} MAC history records older than {cutoff_date}")
            return result

        except Exception as e:
            db.rollback()
            error_result = {
                "success": False,
                "error": str(e),
                "retention_days": self.retention_days,
                "timestamp": datetime.utcnow().isoformat()
            }
            self._last_cleanup_result = error_result
            logger.error(f"Error cleaning up MAC history: {e}")
            return error_result

        finally:
            if close_db:
                db.close()

    def get_stats(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Get statistics about MAC history records.

        Args:
            db: Optional database session.

        Returns:
            Dict with history statistics (total_records, oldest_record, records_to_delete, etc.)
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)

            # Total records
            total_records = db.query(func.count(MacHistory.id)).scalar() or 0

            # Oldest record
            oldest = db.query(func.min(MacHistory.event_at)).scalar()

            # Records that would be deleted
            records_to_delete = db.query(func.count(MacHistory.id)).filter(
                MacHistory.event_at < cutoff_date
            ).scalar() or 0

            # Records by event type
            from sqlalchemy import distinct
            event_types = db.query(
                MacHistory.event_type,
                func.count(MacHistory.id)
            ).group_by(MacHistory.event_type).all()

            event_type_counts = {et: count for et, count in event_types}

            return {
                "total_records": total_records,
                "oldest_record": oldest.isoformat() if oldest else None,
                "retention_days": self.retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "records_to_delete": records_to_delete,
                "records_to_keep": total_records - records_to_delete,
                "event_type_counts": event_type_counts,
                "last_cleanup": self._last_cleanup_result
            }

        except Exception as e:
            logger.error(f"Error getting history stats: {e}")
            return {
                "error": str(e),
                "retention_days": self.retention_days
            }

        finally:
            if close_db:
                db.close()

    def get_last_cleanup_result(self) -> Optional[Dict[str, Any]]:
        """Get the result of the last cleanup operation."""
        return self._last_cleanup_result


# Singleton instance
_cleanup_service: Optional[HistoryCleanupService] = None


def get_history_cleanup_service() -> HistoryCleanupService:
    """Get the history cleanup service singleton instance."""
    global _cleanup_service
    if _cleanup_service is None:
        _cleanup_service = HistoryCleanupService()
    return _cleanup_service
