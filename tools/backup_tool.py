"""
Backup Tool - Backup, recovery, and rollback functionality.
Phase 4: Data protection for SQLite and Qdrant.
"""

import json
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from config import config
from exceptions import (
    DatabaseError,
    ExternalServiceError,
    MemoryServiceError,
    wrap_exception,
)

logger = logging.getLogger(__name__)


@dataclass
class BackupInfo:
    """Metadata for a backup."""

    id: str
    timestamp: str
    env_mode: str
    db_file: str
    vectors_file: Optional[str]
    chat_count: int
    message_count: int
    memory_count: int


def _get_manifest_path() -> Path:
    """Get path to backup manifest file."""
    return config.backups_dir / "manifest.json"


def _load_manifest() -> list[dict]:
    """Load backup manifest."""
    manifest_path = _get_manifest_path()
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return []


def _save_manifest(backups: list[dict]):
    """Save backup manifest."""
    manifest_path = _get_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(backups, indent=2))


def _get_db_stats() -> tuple[int, int]:
    """Get chat and message counts from current database."""
    try:
        conn = sqlite3.connect(config.db_path)
        chat_count = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()
        return chat_count, msg_count
    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="get_db_stats")
        logger.debug(f"Database error getting stats: {wrapped}")
        return 0, 0
    except Exception as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="get_db_stats")
        logger.debug(f"Unexpected error getting stats: {wrapped}")
        return 0, 0


def _get_memory_count() -> int:
    """Get memory count from Qdrant."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
        info = client.get_collection(config.qdrant_collection)
        return info.points_count or 0
    except Exception as e:
        wrapped = wrap_exception(e, MemoryServiceError, operation="get_memory_count")
        logger.debug(f"Memory service error getting count: {wrapped}")
        return 0


def _export_qdrant_vectors(output_path: Path) -> bool:
    """Export all vectors from Qdrant collection to JSON."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)

        # Scroll through all points
        all_points = []
        offset = None

        while True:
            results, offset = client.scroll(
                collection_name=config.qdrant_collection,
                limit=100,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )

            for point in results:
                all_points.append(
                    {
                        "id": str(point.id),
                        "vector": point.vector,
                        "payload": point.payload,
                    }
                )

            if offset is None:
                break

        output_path.write_text(json.dumps(all_points, indent=2))
        return True
    except Exception as e:
        wrapped = wrap_exception(e, MemoryServiceError, operation="vector_export")
        logger.error(f"Vector export failed: {wrapped}")
        return False


def _import_qdrant_vectors(input_path: Path) -> bool:
    """Import vectors from JSON back to Qdrant collection."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import PointStruct, VectorParams, Distance

        client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)

        # Load points from backup
        points_data = json.loads(input_path.read_text())

        if not points_data:
            return True  # Nothing to restore

        # Recreate collection (drop if exists)
        try:
            client.delete_collection(config.qdrant_collection)
            logger.info(f"Deleted existing collection for restore")
        except Exception as e:
            logger.warning(f"Collection delete failed (may not exist): {e}")

        # Detect embedding dimension from first point
        embedding_dim = 768
        if points_data:
            first_vector = points_data[0].get("vector")
            if first_vector:
                embedding_dim = len(first_vector)
                logger.info(f"Detected embedding dimension: {embedding_dim}")

        client.create_collection(
            collection_name=config.qdrant_collection,
            vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
        )

        # Insert points in batches
        batch_size = 100
        points = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points_data
        ]

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(collection_name=config.qdrant_collection, points=batch)

        return True
    except Exception as e:
        wrapped = wrap_exception(e, MemoryServiceError, operation="vector_import")
        logger.error(f"Vector import failed: {wrapped}")
        return False


def create_backup(description: str = "") -> Optional[BackupInfo]:
    """
    Create a new backup of SQLite database and Qdrant vectors.

    Args:
        description: Optional description for the backup

    Returns:
        BackupInfo if successful, None otherwise
    """
    conn = None
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"{timestamp}_{config.env_mode}"

        # Ensure backup directory exists
        config.backups_dir.mkdir(parents=True, exist_ok=True)

        # Backup SQLite (with WAL checkpoint while holding lock)
        db_backup_name = f"{backup_id}_megpt.db"
        db_backup_path = config.backups_dir / db_backup_name

        if config.db_path.exists():
            # Open connection and keep it open during copy
            conn = sqlite3.connect(config.db_path)
            conn.execute("BEGIN IMMEDIATE")  # Lock database

            try:
                # Checkpoint WAL to ensure all data is in main file
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

                # Copy WHILE holding lock
                shutil.copy2(config.db_path, db_backup_path)

                conn.commit()
            finally:
                conn.close()
                conn = None

        # Backup Qdrant vectors
        vectors_backup_name = f"{backup_id}_vectors.json"
        vectors_backup_path = config.backups_dir / vectors_backup_name
        vectors_exported = _export_qdrant_vectors(vectors_backup_path)

        # Get stats
        chat_count, msg_count = _get_db_stats()
        memory_count = _get_memory_count()

        # Create backup info
        backup = BackupInfo(
            id=backup_id,
            timestamp=datetime.now().isoformat(),
            env_mode=config.env_mode,
            db_file=db_backup_name,
            vectors_file=vectors_backup_name if vectors_exported else None,
            chat_count=chat_count,
            message_count=msg_count,
            memory_count=memory_count,
        )

        # Update manifest
        manifest = _load_manifest()
        manifest.insert(0, asdict(backup))

        # Enforce retention limit
        if len(manifest) > config.backup_retention_count:
            # Remove old backups
            for old in manifest[config.backup_retention_count :]:
                old_db = config.backups_dir / old.get("db_file", "")
                old_vec = config.backups_dir / old.get("vectors_file", "")
                if old_db.exists():
                    old_db.unlink()
                if old_vec.exists():
                    old_vec.unlink()
            manifest = manifest[: config.backup_retention_count]

        _save_manifest(manifest)

        logger.info(f"Backup created: {backup_id}")
        logger.info(
            f"  Chats: {chat_count}, Messages: {msg_count}, Memories: {memory_count}"
        )

        return backup

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="create_backup")
        logger.error(f"Backup failed (database): {wrapped}")
        if conn:
            try:
                conn.close()
            except:
                pass
        return None
    except MemoryServiceError as e:
        logger.error(f"Backup failed (memory service): {e}")
        if conn:
            try:
                conn.close()
            except:
                pass
        return None
    except (OSError, IOError) as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="create_backup")
        logger.error(f"Backup failed (file I/O): {wrapped}")
        if conn:
            try:
                conn.close()
            except:
                pass
        return None
    except Exception as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="create_backup")
        logger.error(f"Backup failed: {wrapped}")
        if conn:
            try:
                conn.close()
            except:
                pass
        return None


def list_backups() -> list[BackupInfo]:
    """Get list of available backups."""
    manifest = _load_manifest()
    return [BackupInfo(**b) for b in manifest]


def restore_backup(backup_id: str) -> bool:
    """
    Restore from a specific backup.

    Args:
        backup_id: The backup ID to restore

    Returns:
        True if successful
    """
    try:
        manifest = _load_manifest()
        backup = next((b for b in manifest if b["id"] == backup_id), None)

        if not backup:
            logger.warning(f"Backup not found: {backup_id}")
            return False

        # Auto-backup before restore (safety net)
        if config.auto_backup_before_restore:
            logger.info("Creating safety backup before restore...")
            create_backup("auto_before_restore")

        # Restore SQLite
        db_backup_path = config.backups_dir / backup["db_file"]
        if db_backup_path.exists():
            # Validate backup file before restore
            if db_backup_path.stat().st_size == 0:
                logger.error(f"Backup file is empty: {backup['db_file']}")
                return False
            # Close any connections and replace file
            shutil.copy2(db_backup_path, config.db_path)
            logger.info(f"Database restored from {backup['db_file']}")

        # Restore Qdrant vectors
        if backup.get("vectors_file"):
            vectors_backup_path = config.backups_dir / backup["vectors_file"]
            if vectors_backup_path.exists():
                _import_qdrant_vectors(vectors_backup_path)
                logger.info(f"Vectors restored from {backup['vectors_file']}")

        logger.info(f"Restore complete: {backup_id}")
        return True

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="restore_backup")
        logger.error(f"Restore failed (database): {wrapped}")
        return False
    except MemoryServiceError as e:
        logger.error(f"Restore failed (memory service): {e}")
        return False
    except (OSError, IOError) as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="restore_backup")
        logger.error(f"Restore failed (file I/O): {wrapped}")
        return False
    except Exception as e:
        wrapped = wrap_exception(e, ExternalServiceError, operation="restore_backup")
        logger.error(f"Restore failed: {wrapped}")
        return False


def rollback_latest() -> bool:
    """
    Rollback to the most recent backup.

    Returns:
        True if successful
    """
    backups = list_backups()

    if not backups:
        logger.warning("No backups available for rollback")
        return False

    # Skip the very first if it's an auto-backup we just created
    latest = backups[0]
    logger.info(f"Rolling back to: {latest.id}")

    return restore_backup(latest.id)


def get_backup_info(backup_id: str) -> Optional[BackupInfo]:
    """Get info for a specific backup."""
    manifest = _load_manifest()
    backup = next((b for b in manifest if b["id"] == backup_id), None)
    return BackupInfo(**backup) if backup else None
