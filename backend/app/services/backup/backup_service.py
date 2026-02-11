"""Database backup service for Mac-Traker.

Provides automatic and manual backup functionality for the SQLite database.
"""
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.core.config import get_settings


class BackupService:
    """Service for database backup operations."""

    def __init__(self, backup_dir: Optional[str] = None):
        """Initialize backup service.

        Args:
            backup_dir: Directory for storing backups. Defaults to ./backups
        """
        settings = get_settings()
        self.db_path = settings.database_url.replace("sqlite:///", "")
        self.backup_dir = Path(backup_dir or "./backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Default backup retention (keep last N backups)
        self.max_backups = 10

    def create_backup(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Create a database backup.

        Args:
            label: Optional label to include in backup filename

        Returns:
            Dict with backup details (filename, path, size, timestamp)
        """
        if not os.path.exists(self.db_path):
            return {
                "success": False,
                "error": f"Database not found: {self.db_path}",
                "timestamp": datetime.now().isoformat()
            }

        # Generate backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label_part = f"_{label}" if label else ""
        filename = f"mactraker_backup_{timestamp}{label_part}.db"
        backup_path = self.backup_dir / filename

        try:
            # Use SQLite backup API for safe copy while database may be in use
            source_conn = sqlite3.connect(self.db_path)
            dest_conn = sqlite3.connect(str(backup_path))

            with dest_conn:
                source_conn.backup(dest_conn)

            source_conn.close()
            dest_conn.close()

            # Get backup file size
            file_size = os.path.getsize(backup_path)

            # Cleanup old backups
            self._cleanup_old_backups()

            return {
                "success": True,
                "filename": filename,
                "path": str(backup_path),
                "size": file_size,
                "size_formatted": self._format_size(file_size),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups.

        Returns:
            List of backup details sorted by creation time (newest first)
        """
        backups = []

        if not self.backup_dir.exists():
            return backups

        for file in self.backup_dir.glob("mactraker_backup_*.db"):
            stat = file.stat()
            backups.append({
                "filename": file.name,
                "path": str(file),
                "size": stat.st_size,
                "size_formatted": self._format_size(stat.st_size),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """Delete a specific backup file.

        Args:
            filename: Name of the backup file to delete

        Returns:
            Dict with operation result
        """
        backup_path = self.backup_dir / filename

        if not backup_path.exists():
            return {
                "success": False,
                "error": f"Backup not found: {filename}"
            }

        # Security check - only delete files matching backup pattern
        if not filename.startswith("mactraker_backup_") or not filename.endswith(".db"):
            return {
                "success": False,
                "error": "Invalid backup filename"
            }

        try:
            backup_path.unlink()
            return {
                "success": True,
                "message": f"Backup deleted: {filename}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def restore_backup(self, filename: str) -> Dict[str, Any]:
        """Restore database from a backup.

        WARNING: This will overwrite the current database!

        Args:
            filename: Name of the backup file to restore

        Returns:
            Dict with operation result
        """
        backup_path = self.backup_dir / filename

        if not backup_path.exists():
            return {
                "success": False,
                "error": f"Backup not found: {filename}"
            }

        # Security check
        if not filename.startswith("mactraker_backup_") or not filename.endswith(".db"):
            return {
                "success": False,
                "error": "Invalid backup filename"
            }

        try:
            # Create backup of current database before restore
            current_backup = self.create_backup(label="pre_restore")
            if not current_backup.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to backup current database: {current_backup.get('error')}"
                }

            # Use SQLite backup API for safe restore
            source_conn = sqlite3.connect(str(backup_path))
            dest_conn = sqlite3.connect(self.db_path)

            with dest_conn:
                source_conn.backup(dest_conn)

            source_conn.close()
            dest_conn.close()

            return {
                "success": True,
                "message": f"Database restored from {filename}",
                "pre_restore_backup": current_backup.get("filename")
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def verify_backup(self, filename: str) -> Dict[str, Any]:
        """Verify a backup file integrity.

        Args:
            filename: Name of the backup file to verify

        Returns:
            Dict with verification result and table counts
        """
        backup_path = self.backup_dir / filename

        if not backup_path.exists():
            return {
                "success": False,
                "error": f"Backup not found: {filename}"
            }

        try:
            conn = sqlite3.connect(str(backup_path))
            cursor = conn.cursor()

            # Run integrity check
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]

            if integrity_result != "ok":
                conn.close()
                return {
                    "success": False,
                    "error": f"Integrity check failed: {integrity_result}"
                }

            # Get table counts
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]

            table_counts = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]

            conn.close()

            return {
                "success": True,
                "integrity": "ok",
                "tables": table_counts,
                "total_records": sum(table_counts.values())
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _cleanup_old_backups(self):
        """Remove old backups exceeding max_backups limit."""
        backups = self.list_backups()

        if len(backups) > self.max_backups:
            # Keep only max_backups most recent
            for backup in backups[self.max_backups:]:
                try:
                    Path(backup["path"]).unlink()
                except Exception:
                    pass  # Ignore cleanup errors

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"


# Singleton instance
_backup_service: Optional[BackupService] = None


def get_backup_service() -> BackupService:
    """Get the backup service singleton instance."""
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService()
    return _backup_service
