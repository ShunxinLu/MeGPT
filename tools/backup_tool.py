"""
Backup Tool - Backup, recovery, and rollback functionality.
Phase 4: Data protection for SQLite and Qdrant.
"""

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from config import config


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
    except Exception:
        return 0, 0


def _get_memory_count() -> int:
    """Get memory count from Qdrant."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
        info = client.get_collection(config.qdrant_collection)
        return info.points_count or 0
    except Exception:
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
        print(f"⚠ Vector export failed: {e}")
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
        except Exception:
            pass

        # Detect embedding dimension from first point
        embedding_dim = 768
        if points_data:
            first_vector = points_data[0].get("vector")
            if first_vector:
                embedding_dim = len(first_vector)
                print(f"✓ Detected embedding dimension: {embedding_dim}")

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
        print(f"⚠ Vector import failed: {e}")
        return False


def create_backup(description: str = "") -> Optional[BackupInfo]:
    """
    Create a new backup of SQLite database and Qdrant vectors.

    Args:
        description: Optional description for the backup

    Returns:
        BackupInfo if successful, None otherwise
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"{timestamp}_{config.env_mode}"

        # Ensure backup directory exists
        config.backups_dir.mkdir(parents=True, exist_ok=True)

        # Backup SQLite (with WAL checkpoint first)
        db_backup_name = f"{backup_id}_megpt.db"
        db_backup_path = config.backups_dir / db_backup_name

        if config.db_path.exists():
            # Checkpoint WAL to ensure all data is in main file
            conn = sqlite3.connect(config.db_path)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()

            shutil.copy2(config.db_path, db_backup_path)

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

        print(f"✓ Backup created: {backup_id}")
        print(f"  Chats: {chat_count}, Messages: {msg_count}, Memories: {memory_count}")

        return backup

    except Exception as e:
        print(f"⚠ Backup failed: {e}")
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
            print(f"⚠ Backup not found: {backup_id}")
            return False

        # Auto-backup before restore (safety net)
        if config.auto_backup_before_restore:
            print("📦 Creating safety backup before restore...")
            create_backup("auto_before_restore")

        # Restore SQLite
        db_backup_path = config.backups_dir / backup["db_file"]
        if db_backup_path.exists():
            # Close any connections and replace file
            shutil.copy2(db_backup_path, config.db_path)
            print(f"✓ Database restored from {backup['db_file']}")

        # Restore Qdrant vectors
        if backup.get("vectors_file"):
            vectors_backup_path = config.backups_dir / backup["vectors_file"]
            if vectors_backup_path.exists():
                _import_qdrant_vectors(vectors_backup_path)
                print(f"✓ Vectors restored from {backup['vectors_file']}")

        print(f"✓ Restore complete: {backup_id}")
        return True

    except Exception as e:
        print(f"⚠ Restore failed: {e}")
        return False


def rollback_latest() -> bool:
    """
    Rollback to the most recent backup.

    Returns:
        True if successful
    """
    backups = list_backups()

    if not backups:
        print("⚠ No backups available for rollback")
        return False

    # Skip the very first if it's an auto-backup we just created
    latest = backups[0]
    print(f"🔄 Rolling back to: {latest.id}")

    return restore_backup(latest.id)


def get_backup_info(backup_id: str) -> Optional[BackupInfo]:
    """Get info for a specific backup."""
    manifest = _load_manifest()
    backup = next((b for b in manifest if b["id"] == backup_id), None)
    return BackupInfo(**backup) if backup else None
