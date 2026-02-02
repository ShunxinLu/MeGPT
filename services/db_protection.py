"""
Database Protection Layer - Automatic backup before destructive operations.

Provides decorators and utilities to protect all database modifications.
"""
import functools
import sqlite3
from pathlib import Path
from typing import Callable

from config import Config
from services.backup_service import create_backup
import logging

logger = logging.getLogger(__name__)


# Track if backup was already created recently (to avoid duplicates during batch ops)
_last_backup_time = None
_backup_cooldown_seconds = 60  # Don't backup more than once per minute


def require_backup(func: Callable) -> Callable:
    """Decorator that creates a backup before running a destructive function.

    Usage:
        @require_backup
        def delete_all_emails():
            # This will automatically backup first
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import time
        global _last_backup_time

        current_time = time.time()
        # Only backup if we haven't backed up recently (avoid duplicates in batch operations)
        if _last_backup_time is None or (current_time - _last_backup_time) > _backup_cooldown_seconds:
            backup_path = create_backup(f"before_{func.__name__}")
            logger.info(f"Backup created before {func.__name__}: {backup_path.name}")
            _last_backup_time = current_time

        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed, backup available at: {backup_path}")
            raise

    return wrapper


def require_backup_bulk(func: Callable) -> Callable:
    """Decorator for BULK operations - always creates a backup.

    Use this for operations that delete/modify LARGE amounts of data.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        backup_path = create_backup(f"before_bulk_{func.__name__}")
        logger.info(f"BULK operation backup created: {backup_path.name}")

        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"BULK operation {func.__name__} failed, backup at: {backup_path}")
            raise

    return wrapper


class ProtectedConnection:
    """Wrapper around sqlite3.Connection that tracks destructive operations."""

    def __init__(self, conn: sqlite3.Connection, auto_backup: bool = True):
        self._conn = conn
        self._auto_backup = auto_backup
        self._destructive_count = 0
        self._backup_created = False

    def execute(self, sql, *args, **kwargs):
        """Intercept execute to detect destructive operations."""
        sql_upper = sql.strip().upper()

        # Detect destructive operations
        is_destructive = any(keyword in sql_upper for keyword in [
            "DELETE FROM", "DROP TABLE", "TRUNCATE", "ALTER TABLE"
        ])

        # Create backup before first destructive operation
        if is_destructive and self._auto_backup and not self._backup_created:
            # But skip for single-item deletes (have WHERE with specific ID)
            is_single_delete = "WHERE" in sql_upper and any(
                word in sql_upper for word in ["id = ?", "id =", "garmin_activity_id"]
            )

            if not is_single_delete:
                import traceback
                caller = traceback.extract_stack()[-2]
                func_name = caller.name if caller else "unknown"
                backup_path = create_backup(f"before_{func_name}")
                logger.info(f"Auto-backup before destructive SQL in {func_name}: {backup_path.name}")
                self._backup_created = True

        self._destructive_count += is_destructive
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        """Proxy all other attributes to the underlying connection."""
        return getattr(self._conn, name)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


def protected_db(db_path: Path | str = None):
    """Get a protected database connection.

    Usage:
        with protected_db() as conn:
            conn.execute("DELETE FROM emails")  # Auto-backup before this
    """
    if db_path is None:
        db_path = Config().db_path

    raw_conn = sqlite3.connect(str(db_path))
    return ProtectedConnection(raw_conn, auto_backup=True)


if __name__ == "__main__":
    # Test the protection
    import tempfile

    logging.basicConfig(level=logging.INFO)

    # Test with a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = Path(f.name)

    try:
        # Create test table
        conn = sqlite3.connect(test_db)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'test')")
        conn.commit()
        conn.close()

        # Test protected connection
        print("Testing protected connection...")
        with protected_db(test_db) as conn:
            conn.execute("INSERT INTO test VALUES (2, 'test2')")  # No backup needed
            conn.execute("DELETE FROM test WHERE id = 1")  # Single delete, no backup
            conn.execute("DELETE FROM test")  # Bulk delete - creates backup!
            conn.commit()

        print("Test complete!")

    finally:
        test_db.unlink(missing_ok=True)
