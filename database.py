"""
Database Layer - SQLite with FTS5, WAL mode, and Phase 3 summary support.
"""
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

# Database file location
DB_PATH = Path(__file__).parent / "data" / "megpt.db"


def get_db_path() -> Path:
    """Ensure data directory exists and return DB path."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    """Context manager for database connections with WAL mode."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    # CRITICAL: Enable Write-Ahead Logging to allow simultaneous Read/Write
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database schema."""
    with get_connection() as conn:
        # Core tables - Phase 3: Added summary column
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                summary TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add summary column if it doesn't exist (for migration)
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN summary TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        
        # FTS5 for full-text search
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts 
            USING fts5(content, chat_id UNINDEXED)
        """)
        
        # Triggers to sync FTS table
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, chat_id) 
                VALUES (NEW.rowid, NEW.content, NEW.chat_id);
            END
        """)
        
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = OLD.rowid;
            END
        """)
        
        print("✓ Database initialized with WAL mode")


# ========== Chat CRUD ==========

def create_chat(user_id: str, title: Optional[str] = None) -> dict:
    """Create a new chat."""
    chat_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chats (id, user_id, title, summary, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, title or "New Chat", "", now, now)
        )
    
    return {"id": chat_id, "user_id": user_id, "title": title or "New Chat", "created_at": now}


def get_chats(user_id: str) -> list[dict]:
    """Get all chats for a user, ordered by most recent."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chats WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        ).fetchall()
    
    return [dict(row) for row in rows]


def get_chat(chat_id: str) -> Optional[dict]:
    """Get a single chat by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    
    return dict(row) if row else None


def update_chat_title(chat_id: str, title: str):
    """Update a chat's title."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, chat_id)
        )


def delete_chat(chat_id: str):
    """Delete a chat and all its messages (cascading)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


# ========== Phase 3: Summary Functions ==========

def get_summary(chat_id: str) -> str:
    """Get the rolling summary for a chat (Tier 3)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT summary FROM chats WHERE id = ?", 
            (chat_id,)
        ).fetchone()
    
    return row["summary"] if row and row["summary"] else ""


def update_summary(chat_id: str, summary: str):
    """Update the rolling summary for a chat."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE chats SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, now, chat_id)
        )


def get_message_count(chat_id: str) -> int:
    """Get the count of messages in a chat."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM messages WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
    
    return row["count"] if row else 0


def get_recent_messages_text(chat_id: str, limit: int = 20) -> str:
    """Get recent messages as formatted text for summarization."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages 
               WHERE chat_id = ? 
               ORDER BY created_at DESC 
               LIMIT ?""",
            (chat_id, limit)
        ).fetchall()
    
    # Reverse to get chronological order
    messages = list(reversed(rows))
    return "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages])


# ========== Message CRUD ==========

def add_message(chat_id: str, role: str, content: str) -> dict:
    """Add a message to a chat."""
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, chat_id, role, content, now)
        )
        # Update chat's updated_at
        conn.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (now, chat_id)
        )
    
    return {"id": msg_id, "chat_id": chat_id, "role": role, "content": content, "created_at": now}


def get_messages(chat_id: str, limit: Optional[int] = None) -> list[dict]:
    """Get messages for a chat, ordered chronologically. Optional limit for recent messages."""
    with get_connection() as conn:
        if limit:
            # Get last N messages
            rows = conn.execute(
                """SELECT * FROM messages WHERE chat_id = ? 
                   ORDER BY created_at DESC LIMIT ?""",
                (chat_id, limit)
            ).fetchall()
            # Reverse to get chronological order
            rows = list(reversed(rows))
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
                (chat_id,)
            ).fetchall()
    
    return [dict(row) for row in rows]


# ========== Search ==========

def search_chats(user_id: str, query: str) -> list[dict]:
    """Full-text search across messages, returns matching chats."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT c.* FROM chats c
            JOIN messages_fts fts ON c.id = fts.chat_id
            WHERE c.user_id = ? AND messages_fts MATCH ?
            ORDER BY c.updated_at DESC
        """, (user_id, query)).fetchall()
    
    return [dict(row) for row in rows]


# Initialize on import
init_db()
