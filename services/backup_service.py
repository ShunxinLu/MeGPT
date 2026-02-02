"""
Database Backup Service - Automatic backups before destructive operations.

Creates timestamped backups and provides restore functionality.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import Config
import logging

logger = logging.getLogger(__name__)

# Config
MAX_BACKUPS = 10  # Keep last N backups
BACKUP_DIR = Path(Config().data_dir) / "backups"


def get_backup_path(name: Optional[str] = None) -> Path:
    """Generate a backup file path with timestamp."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}_megpt.db"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_megpt.db"

    return BACKUP_DIR / filename


def create_backup(name: Optional[str] = None) -> Path:
    """Create a backup of the main database.

    Args:
        name: Optional name for the backup (e.g., "before_sync", "before_migration")

    Returns:
        Path to the backup file
    """
    db_path = Config().db_path
    backup_path = get_backup_path(name)

    # Use SQLite backup API for safe online backup
    source = sqlite3.connect(str(db_path))
    dest = sqlite3.connect(str(backup_path))

    logger.info(f"Creating backup: {backup_path.name}")

    def progress(status, remaining, total):
        if remaining == 0:
            logger.info(f"Backup complete: {backup_path.name}")

    try:
        source.backup(dest, pages=1, progress=progress)
    finally:
        dest.close()
        source.close()

    # Clean up old backups
    cleanup_old_backups()

    logger.info(f"Backup created: {backup_path}")
    return backup_path


def cleanup_old_backups():
    """Remove old backups, keeping only the most recent MAX_BACKUPS."""
    backups = sorted(BACKUP_DIR.glob("*_megpt.db"), key=lambda p: p.stat().st_mtime, reverse=True)

    for old_backup in backups[MAX_BACKUPS:]:
        try:
            old_backup.unlink()
            logger.info(f"Removed old backup: {old_backup.name}")
        except Exception as e:
            logger.warning(f"Failed to remove old backup {old_backup}: {e}")


def list_backups() -> list[dict]:
    """List all available backups with metadata."""
    backups = []

    for backup_path in sorted(BACKUP_DIR.glob("*_megpt.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = backup_path.stat()
        backups.append({
            "path": str(backup_path),
            "name": backup_path.name,
            "size_mb": stat.st_size / (1024 * 1024),
            "created": datetime.fromtimestamp(stat.st_mtime),
        })

    return backups


def restore_backup(backup_path: Path) -> bool:
    """Restore a backup to the main database.

    WARNING: This will replace the current database!

    Args:
        backup_path: Path to the backup file

    Returns:
        True if successful
    """
    if not backup_path.exists():
        logger.error(f"Backup not found: {backup_path}")
        return False

    # First backup the current database (in case restore fails)
    current_backup = create_backup("before_restore")

    db_path = Config().db_path

    try:
        # Close any existing connections
        # (This is a simple approach - in production you'd want connection pooling)

        # Copy the backup over the current database
        shutil.copy2(str(backup_path), str(db_path))

        logger.info(f"Restored backup: {backup_path.name}")
        logger.info(f"Previous state backed up to: {current_backup.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        # Try to restore from the pre-restore backup
        if current_backup.exists():
            shutil.copy2(str(current_backup), str(db_path))
            logger.info("Restored from pre-restore backup")
        return False


def restore_latest() -> bool:
    """Restore the most recent backup."""
    backups = list_backups()
    if not backups:
        logger.error("No backups available")
        return False

    latest = backups[0]
    return restore_backup(Path(latest["path"]))


def require_backup(func):
    """Decorator that creates a backup before running a function.

    Usage:
        @require_backup
        def dangerous_operation():
            # Do something that modifies database
            pass
    """
    def wrapper(*args, **kwargs):
        backup_path = create_backup(f"before_{func.__name__}")
        logger.info(f"Backup created before {func.__name__}: {backup_path.name}")
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed, backup available at: {backup_path}")
            raise

    return wrapper


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "create":
            name = sys.argv[2] if len(sys.argv) > 2 else None
            backup = create_backup(name)
            print(f"Backup created: {backup}")

        elif command == "list":
            backups = list_backups()
            print(f"\nFound {len(backups)} backups:")
            for b in backups:
                print(f"  {b['name']} - {b['created']} - {b['size_mb']:.1f} MB")

        elif command == "restore":
            if len(sys.argv) > 2:
                backup_name = sys.argv[2]
                backup_path = BACKUP_DIR / backup_name
                if restore_backup(backup_path):
                    print(f"Restored: {backup_name}")
                else:
                    print(f"Failed to restore: {backup_name}")
            else:
                if restore_latest():
                    print("Restored latest backup")
                else:
                    print("No backups to restore")

        else:
            print("Usage: python backup_service.py [create|list|restore] [name]")
    else:
        print("Usage: python backup_service.py [create|list|restore] [name]")
        print("\nExamples:")
        print("  python backup_service.py create before_sync")
        print("  python backup_service.py list")
        print("  python backup_service.py restore 20260201_120000_before_sync_megpt.db")
