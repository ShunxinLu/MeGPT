"""
Database Layer - SQLite with FTS5, WAL mode, and Phase 3 summary support.
Phase 4: Environment-aware database paths.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

import httpx

from config import config
from utils.llm_factory import get_llm_config
from exceptions import (
    DatabaseError,
    DatabaseSchemaError,
    DatabaseConnectionError,
    DatabaseQueryError,
    wrap_exception,
)

logger = logging.getLogger(__name__)


def _normalize_base_url(base_url: str) -> str:
    """
    Normalize base URL by stripping trailing /v1 suffix.

    ChatOpenAI and other clients add /v1 automatically, so we need to
    remove it from the base URL to avoid duplication like:
    http://localhost:1234/v1/v1/chat/completions
    """
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    return base_url


def get_db_path() -> Path:
    """Ensure data directory exists and return DB path."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return config.db_path


@contextmanager
def get_connection(timeout: float = 30.0):
    """
    Context manager for database connections with WAL mode.

    Args:
        timeout: Connection timeout in seconds (default: 30)
    """
    conn = sqlite3.connect(get_db_path(), timeout=timeout)
    conn.row_factory = sqlite3.Row

    # Check WAL mode was set successfully
    wal_result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    if wal_result[0] != "wal":
        logger.warning(f"WAL mode not enabled, got: {wal_result[0]}")

    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise wrap_exception(
            e, DatabaseError, details={"operation": "database_connection"}
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database schema with proper indexes, foreign keys, and FTS triggers."""
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
        except sqlite3.OperationalError as e:
            # Only silence "duplicate column" errors
            if "duplicate column" not in str(e).lower():
                wrapped = DatabaseSchemaError(
                    f"Schema migration error: {e}", details={"original_error": str(e)}
                )
                logger.warning(f"Unexpected schema error: {wrapped}")

        # Add email/calendar sync columns if they don't exist (for migration)
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN last_email_sync TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE chats ADD COLUMN last_calendar_sync TEXT")
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

        # Triggers to sync FTS table (INSERT, DELETE, UPDATE)
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

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                UPDATE messages_fts
                SET content = NEW.content, chat_id = NEW.chat_id
                WHERE rowid = OLD.rowid;
            END
        """)

        # Domain: Email tables with foreign key and unique constraint
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                chat_id TEXT,
                thread_id TEXT,
                subject TEXT,
                sender TEXT,
                sender_email TEXT,
                body_markdown TEXT,
                summary TEXT,
                priority TEXT DEFAULT 'normal' CHECK(priority IN ('low', 'normal', 'important', 'critical')),
                category TEXT,
                is_read INTEGER DEFAULT 0,
                is_spam_or_scam INTEGER DEFAULT 0,
                date_received TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                UNIQUE(thread_id, sender_email, date_received)
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts
            USING fts5(subject, sender, body_markdown, content)
        """)

        # CRITICAL FIX: Triggers to sync emails FTS table
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS emails_ai AFTER INSERT ON emails BEGIN
                INSERT INTO emails_fts(rowid, subject, sender, body_markdown, content)
                VALUES (NEW.rowid, NEW.subject, NEW.sender, NEW.body_markdown, NEW.summary);
            END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS emails_ad AFTER DELETE ON emails BEGIN
                DELETE FROM emails_fts WHERE rowid = OLD.rowid;
            END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS emails_au AFTER UPDATE ON emails BEGIN
                UPDATE emails_fts
                SET subject = NEW.subject, sender = NEW.sender,
                    body_markdown = NEW.body_markdown, content = NEW.summary
                WHERE rowid = OLD.rowid;
            END
        """)

        # ========== Email Sync Migration Columns ==========
        # Add new columns for email sync support (with backward compatibility)
        email_migrations = [
            ("source", "TEXT DEFAULT 'gmail'"),
            ("labels", "TEXT"),  # JSON array for Gmail labels
            ("folder", "TEXT"),  # INBOX, SENT
            ("recipients", "TEXT"),  # JSON array of recipients
            ("history_id", "TEXT"),  # Gmail history ID for incremental sync
            ("processed_at", "DATETIME"),  # When email was processed by AI
        ]

        for column_name, column_def in email_migrations:
            try:
                conn.execute(f"ALTER TABLE emails ADD COLUMN {column_name} {column_def}")
                logger.info(f"Added email column: {column_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning(f"Unexpected migration error for {column_name}: {e}")

        # ========== Email Sync State Table ==========
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_sync_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                gmail_history_id TEXT,
                outlook_delta_link TEXT,
                last_sync_at DATETIME,
                sync_window_start DATETIME,
                CONSTRAINT single_row CHECK (id = 1)
            )
        """)

        # Initialize sync state if not exists
        conn.execute("""
            INSERT OR IGNORE INTO email_sync_state (id, gmail_history_id, outlook_delta_link, last_sync_at)
            VALUES (1, NULL, NULL, NULL)
        """)

        # ========== Reminders Table ==========
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL CHECK(source_type IN ('email', 'calendar', 'manual')),
                source_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                due_date DATETIME,
                priority TEXT DEFAULT 'normal' CHECK(priority IN ('low', 'normal', 'important', 'critical')),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'dismissed', 'overdue')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
        """)

        # Index for reminder queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_status_due
            ON reminders(status, due_date)
        """)

        # Domain: Calendar tables with foreign keys and check constraints
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calendar_events (
                id TEXT PRIMARY KEY,
                chat_id TEXT,
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location TEXT,
                description TEXT,
                attendees TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'cancelled')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK(end_time > start_time),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS calendar_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location TEXT,
                description TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK(end_time > start_time),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        # Domain: Documents table for knowledge base
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                chat_id TEXT,
                filename TEXT NOT NULL,
                file_type TEXT,
                file_path TEXT,
                content TEXT,
                summary TEXT,
                chunk_count INTEGER DEFAULT 0,
                metadata TEXT,
                status TEXT DEFAULT 'processing' CHECK(status IN ('processing', 'completed', 'failed')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(filename, content, summary)
        """)

        # Triggers to sync documents FTS table
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, filename, content, summary)
                VALUES (NEW.rowid, NEW.filename, NEW.content, COALESCE(NEW.summary, ''));
            END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = OLD.rowid;
            END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                UPDATE documents_fts
                SET filename = NEW.filename, content = NEW.content, summary = COALESCE(NEW.summary, '')
                WHERE rowid = OLD.rowid;
            END
        """)

        # Domain: Health tables for Garmin data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_daily (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL UNIQUE,
                steps INTEGER DEFAULT 0,
                distance_meters REAL DEFAULT 0,
                calories_total INTEGER DEFAULT 0,
                calories_active INTEGER DEFAULT 0,
                resting_heart_rate INTEGER DEFAULT 0,
                avg_heart_rate INTEGER DEFAULT 0,
                max_heart_rate INTEGER DEFAULT 0,
                stress_avg INTEGER DEFAULT 0,
                body_battery_high INTEGER DEFAULT 0,
                body_battery_low INTEGER DEFAULT 0,
                floors_climbed INTEGER DEFAULT 0,
                intensity_minutes INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_sleep (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL UNIQUE,
                sleep_start TEXT,
                sleep_end TEXT,
                duration_seconds INTEGER DEFAULT 0,
                deep_sleep_seconds INTEGER DEFAULT 0,
                light_sleep_seconds INTEGER DEFAULT 0,
                rem_sleep_seconds INTEGER DEFAULT 0,
                awake_seconds INTEGER DEFAULT 0,
                sleep_score INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_activities (
                id TEXT PRIMARY KEY,
                garmin_activity_id TEXT UNIQUE,
                activity_type TEXT,
                name TEXT,
                start_time TEXT,
                duration_seconds INTEGER DEFAULT 0,
                distance_meters REAL DEFAULT 0,
                avg_heart_rate INTEGER DEFAULT 0,
                max_heart_rate INTEGER DEFAULT 0,
                calories INTEGER DEFAULT 0,
                avg_pace TEXT,
                summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS garmin_sync_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_at DATETIME,
                last_activity_sync_at DATETIME,
                CONSTRAINT single_row CHECK (id = 1)
            )
        """)

        # Create indexes for performance
        _create_indexes(conn)

        env_badge = "PROD" if config.is_production else "DEV"
        logger.info(f"Database initialized [{env_badge}]: {get_db_path()}")


def _create_indexes(conn: sqlite3.Connection) -> None:
    """Create database indexes for performance optimization."""
    indexes = [
        # Chats table indexes
        ("idx_chats_user_updated", "chats", "(user_id, updated_at DESC)"),
        ("idx_chats_updated", "chats", "(updated_at DESC)"),
        # Messages table indexes
        ("idx_messages_chat_created", "messages", "(chat_id, created_at ASC)"),
        # Emails table indexes
        ("idx_emails_chat", "emails", "(chat_id)"),
        ("idx_emails_date", "emails", "(date_received DESC)"),
        ("idx_emails_priority", "emails", "(priority)"),
        ("idx_emails_read", "emails", "(is_read)"),
        ("idx_emails_priority_date", "emails", "(priority, date_received DESC)"),
        # Calendar events indexes
        ("idx_events_chat", "calendar_events", "(chat_id)"),
        ("idx_events_start", "calendar_events", "(start_time)"),
        ("idx_events_status", "calendar_events", "(status)"),
        ("idx_events_status_start", "calendar_events", "(status, start_time)"),
        # Calendar proposals indexes
        ("idx_proposals_chat", "calendar_proposals", "(chat_id)"),
        ("idx_proposals_status", "calendar_proposals", "(status)"),
        ("idx_proposals_created", "calendar_proposals", "(created_at DESC)"),
        # Documents indexes
        ("idx_documents_chat", "documents", "(chat_id)"),
        ("idx_documents_status", "documents", "(status)"),
        ("idx_documents_type", "documents", "(file_type)"),
        ("idx_documents_created", "documents", "(created_at DESC)"),
        # Health tables indexes
        ("idx_health_daily_date", "health_daily", "(date)"),
        ("idx_health_daily_steps", "health_daily", "(steps DESC)"),
        ("idx_health_sleep_date", "health_sleep", "(date)"),
        ("idx_health_sleep_score", "health_sleep", "(sleep_score)"),
        ("idx_activities_start", "health_activities", "(start_time DESC)"),
        ("idx_activities_type", "health_activities", "(activity_type)"),
    ]

    for idx_name, table, columns in indexes:
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}{columns}")
        except sqlite3.OperationalError as e:
            wrapped = DatabaseSchemaError(
                f"Failed to create index {idx_name}: {e}",
                details={"index_name": idx_name, "table": table, "columns": columns},
            )
            logger.warning(f"{wrapped}")

    logger.info("Database indexes created")


# ========== Chat CRUD ==========


def create_chat(user_id: str, title: Optional[str] = None) -> dict:
    """Create a new chat."""
    chat_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chats (id, user_id, title, summary, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, title or "New Chat", "", now, now),
        )

    return {
        "id": chat_id,
        "user_id": user_id,
        "title": title or "New Chat",
        "created_at": now,
    }


def get_chats(user_id: str) -> list[dict]:
    """Get all chats for a user, ordered by most recent."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chats WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
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
            (title, now, chat_id),
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
            "SELECT summary FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()

    return row["summary"] if row and row["summary"] else ""


def update_summary(chat_id: str, summary: str):
    """Update the rolling summary for a chat."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE chats SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, now, chat_id),
        )


def get_message_count(chat_id: str) -> int:
    """Get the count of messages in a chat."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM messages WHERE chat_id = ?", (chat_id,)
        ).fetchone()

    return row["count"] if row else 0


def get_recent_messages_text(chat_id: str, limit: int = 15) -> str:
    """Get recent messages as formatted text for summarization (Tier 1)."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages 
               WHERE chat_id = ? 
               ORDER BY created_at DESC 
               LIMIT ?""",
            (chat_id, limit),
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
            (msg_id, chat_id, role, content, now),
        )
        # Update chat's updated_at
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))

    return {
        "id": msg_id,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "created_at": now,
    }


def get_messages(chat_id: str, limit: Optional[int] = None) -> list[dict]:
    """Get messages for a chat, ordered chronologically. Optional limit for recent messages."""
    with get_connection() as conn:
        if limit:
            # Get last N messages
            rows = conn.execute(
                """SELECT * FROM messages WHERE chat_id = ? 
                   ORDER BY created_at DESC LIMIT ?""",
                (chat_id, limit),
            ).fetchall()
            # Reverse to get chronological order
            rows = list(reversed(rows))
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
                (chat_id,),
            ).fetchall()

    return [dict(row) for row in rows]


# ========== Search ==========


def search_chats(user_id: str, query: str) -> list[dict]:
    """Full-text search across messages, returns matching chats."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT c.* FROM chats c
            JOIN messages_fts fts ON c.id = fts.chat_id
            WHERE c.user_id = ? AND messages_fts MATCH ?
            ORDER BY c.updated_at DESC
        """,
            (user_id, query),
        ).fetchall()

    return [dict(row) for row in rows]


# ========== Adaptive Context (Query-Aware Tier Selection) ==========


def classify_query_intent(user_query: str) -> dict:
    """
    Use LLM to classify query intent for adaptive context selection.

    Returns:
        {
            "intent": str,  # "followup" | "factual" | "overview" | "new_topic"
            "needs_history": bool  # Whether to include recent messages
        }
    """
    try:
        # Get current LLM config from database (not env vars)
        llm_base_url, llm_api_key, llm_model = get_llm_config()

        response = httpx.post(
            f"{llm_base_url}/chat/completions",
            json={
                "model": llm_model,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Classify this query's intent. Reply with ONLY a JSON object.

Query: "{user_query}"

Categories:
- "followup": References previous context ("what about X?", "and then?", "continue", "more details")
- "factual": Asks for specific facts ("what's my favorite?", "where are we staying?", "who am I?")
- "overview": Asks for summary/status ("catch me up", "what have we discussed?", "remind me")
- "new_topic": Starts a fresh topic unrelated to prior context

Reply format: {{"intent": "<category>", "needs_history": true/false}}""",
                    }
                ],
                "max_tokens": 50,
                "temperature": 0,
            },
            headers={"Authorization": f"Bearer {llm_api_key}"},
            timeout=5,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        # Parse JSON from response (handle markdown code blocks)
        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[WARN] Intent classification failed: {e}")
        return {"intent": "general", "needs_history": True}


def get_domain_context(chat_id: str, user_id: Optional[str] = None) -> dict:
    """
    Tier 4: Domain-specific cached context blocks
    Cached per chat to avoid repeated queries

    Returns:
    {
        "emails": str,  # Recent important emails, threads
        "calendar": str,  # Upcoming events, pending proposals
    }
    """
    print(f"🗂 Loading Tier 4 domain contexts for chat {chat_id}...")

    # Email context (last 3 important emails, recent threads)
    email_context = ""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT subject, sender, summary, priority, date_received
            FROM emails
            WHERE chat_id = ?
              AND priority IN ('critical', 'important')
            ORDER BY date_received DESC
            LIMIT 3
        """,
            (chat_id,),
        )

        email_results = cursor.fetchall()

        if email_results:
            email_parts = []
            for row in email_results:
                priority_icon = "🔴" if row["priority"] == "critical" else "🟠"
                email_parts.append(
                    f"{priority_icon} {row['sender']}: {row['subject']}\n"
                    f"Summary: {row['summary']}"
                )
            email_context = "\n\n[RECENT EMAILS]\n" + "\n".join(email_parts)

    # Calendar context (upcoming 7 days, pending proposals)
    calendar_context = ""
    with get_connection() as conn:
        # Upcoming events
        cursor = conn.execute(
            """
            SELECT title, start_time, end_time, location
            FROM calendar_events
            WHERE chat_id = ?
              AND start_time >= datetime('now')
              AND start_time <= datetime('now', '+7 days')
              AND status IN ('pending', 'confirmed')
            ORDER BY start_time ASC
            LIMIT 5
        """,
            (chat_id,),
        )

        event_results = cursor.fetchall()

        # Pending proposals
        cursor.execute(
            """
            SELECT title, start_time, status
            FROM calendar_proposals
            WHERE chat_id = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 3
        """,
            (chat_id,),
        )

        proposal_results = cursor.fetchall()

        calendar_parts = []

        if event_results:
            calendar_parts.append("[UPCOMING EVENTS]")
            for row in event_results:
                calendar_parts.append(f"📅 {row['start_time']}: {row['title']}")
                if row["location"]:
                    calendar_parts.append(f"   📍 {row['location']}")

        if proposal_results:
            calendar_parts.append("\n[PENDING PROPOSALS]")
            for row in proposal_results:
                status_icon = "⏳" if row["status"] == "pending" else "✓"
                calendar_parts.append(
                    f"{status_icon} {row['start_time']}: {row['title']}"
                )

        if calendar_parts:
            calendar_context = "\n".join(calendar_parts)

    print(
        f"✅ Tier 4 loaded: emails={bool(email_context)}, calendar={bool(calendar_context)}"
    )

    return {
        "emails": email_context,
        "calendar": calendar_context,
    }


def classify_query_intent_enhanced(user_query: str) -> dict:
    """
    Enhanced intent classification with domain detection

    Returns:
    {
        "intent": str,  # "followup" | "factual" | "overview" | "new_topic"
        "needs_history": bool,  # Whether to include recent messages
        "needs_tier4": bool,  # Whether to include domain contexts
        "domain": str | None,  # "email" | "calendar" | null
    }
    """
    try:
        # Get current LLM config from database (not env vars)
        llm_base_url, llm_api_key, llm_model = get_llm_config()

        response = httpx.post(
            f"{llm_base_url}/chat/completions",
            json={
                "model": llm_model,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Classify this query's intent and domain.

Query: "{user_query}"

Intents:
- followup: References previous context ("what about X?", "and then?", "continue", "more details")
- factual: Asks for specific facts ("what's my favorite?", "where are we staying?")
- overview: Asks for summary/status ("catch me up", "what have we discussed?", "show me my emails")
- new_topic: Starts fresh, unrelated to prior context

Domains (only if applicable):
- email: "show me emails", "search for email about...", "what did X say?", "email from Y"
- calendar: "what's on my schedule?", "add event", "schedule meeting", "upcoming events"

Reply with ONLY a JSON object:
{{
    "intent": "<intent>",
    "needs_history": true/false,
    "needs_tier4": true/false,
    "domain": "email" | "calendar" | null
}}""",
                    }
                ],
                "max_tokens": 50,
                "temperature": 0,
            },
            headers={"Authorization": f"Bearer {llm_api_key}"},
            timeout=5,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        # Parse JSON from response (handle markdown code blocks)
        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        import json

        return json.loads(content)
    except Exception as e:
        print(f"[WARN] Intent classification failed: {e}")
        # Fallback to general if classification fails
        return {
            "intent": "general",
            "needs_history": True,
            "needs_tier4": False,
            "domain": None,
        }


def get_adaptive_context(
    user_query: str, chat_id: Optional[str] = None, user_id: Optional[str] = None
) -> dict:
    """
    Returns context components based on query intent.
    Uses LLM classification for intelligent tier selection.

    Enhanced with Tier 4 domain-specific contexts for email/calendar/finance.

    Returns:
    {
        "facts": str,  # From Tier 2
        "summary": str,  # From Tier 3
        "recent": str,  # From Tier 1
        "domains": dict,  # From Tier 4 (NEW)
        "intent": str,  # Query intent type
        "needs_history": bool,  # Whether recent messages are needed
    }
    """
    # Import here to avoid circular imports
    from tools.memory_tool import retrieve_context

    # FAST PATH: Skip intent classification for better performance
    # Use simple keyword-based heuristics instead of LLM call (saves 1-3 seconds)
    query_lower = user_query.lower()

    # Simple intent detection without LLM
    intent = "general"
    needs_history = True
    needs_tier4 = False
    domain = None

    # Detect email domain
    email_keywords = ["email", "emails", "inbox", "mail", "message", "unread", "sender"]
    if any(kw in query_lower for kw in email_keywords):
        domain = "email"
        needs_tier4 = True

    # Detect calendar domain
    calendar_keywords = ["calendar", "schedule", "meeting", "event", "appointment", "remind"]
    if any(kw in query_lower for kw in calendar_keywords):
        domain = "calendar"
        needs_tier4 = True

    # Detect intent types
    overview_keywords = ["summary", "summarize", "overview", "catch me up", "what have we", "status"]
    if any(kw in query_lower for kw in overview_keywords):
        intent = "overview"

    followup_keywords = ["and then", "what about", "more about", "continue", "elaborate"]
    if any(kw in query_lower for kw in followup_keywords):
        intent = "followup"

    print(f"[INFO] Query intent: {intent} (domain: {domain}, tier4: {needs_tier4}) [FAST PATH]")

    # 2. Always get vector facts (they're query-relevant by definition)
    facts = retrieve_context(user_query, user_id)

    # 3. Adaptive tier selection based on intent
    summary = ""
    recent = ""
    domains = {
        "emails": "",
        "calendar": "",
    }

    # Load Tier 4 if needed
    if needs_tier4 and chat_id:
        domains = get_domain_context(chat_id, user_id)

    if intent == "overview":
        # Overview → prioritize summary, minimal recent, include domains
        summary = get_summary(chat_id) if chat_id else ""
        recent = get_recent_messages_text(chat_id, limit=config.context.recent_messages_limit_overview) if chat_id else ""
    elif intent == "followup":
        # Follow-up → prioritize recent context, skip summary
        recent = get_recent_messages_text(chat_id, limit=config.context.recent_messages_limit_followup) if chat_id else ""
    elif intent == "factual":
        # Factual → vector facts primary, domain if applicable
        summary = get_summary(chat_id) if (needs_history and chat_id) else ""
        recent = ""
        # Domain-specific fact retrieval
        if domain:
            # Add domain context to facts for domain-specific queries
            if domain in domains and domains[domain]:
                facts = f"{facts}\n\n{domains[domain]}"
    elif intent == "new_topic":
        # New topic → just vector facts, no old context pollution
        summary = ""
        recent = ""
    else:
        # Default (general): include balanced context
        summary = get_summary(chat_id) if chat_id else ""
        recent = get_recent_messages_text(chat_id, limit=config.context.recent_messages_limit_general) if chat_id else ""
        # Include domains for general queries
        domains = get_domain_context(chat_id, user_id) if chat_id else domains

    return {
        "facts": facts,
        "summary": summary,
        "recent": recent,
        "domains": domains,
        "intent": intent,
        "needs_history": needs_history,
    }


# ========== Document CRUD ==========


def create_document(
    chat_id: Optional[str],
    filename: str,
    file_type: str,
    file_path: Optional[str] = None,
    content: str = "",
    summary: str = "",
    metadata: Optional[dict] = None,
) -> dict:
    """Create a new document record."""
    import uuid

    doc_id = str(uuid.uuid4())
    metadata_json = json.dumps(metadata) if metadata else None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, chat_id, filename, file_type, file_path, content, summary, metadata, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing')
            """,
            (
                doc_id,
                chat_id,
                filename,
                file_type,
                file_path,
                content,
                summary,
                metadata_json,
            ),
        )

    return {"id": doc_id, "filename": filename}


def update_document(
    document_id: str,
    content: Optional[str] = None,
    summary: Optional[str] = None,
    status: Optional[str] = None,
    chunk_count: Optional[int] = None,
) -> bool:
    """Update document content, summary, status, or chunk_count."""
    updates = []
    values = []

    if content is not None:
        updates.append("content = ?")
        values.append(content)
    if summary is not None:
        updates.append("summary = ?")
        values.append(summary)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if chunk_count is not None:
        updates.append("chunk_count = ?")
        values.append(chunk_count)

    if not updates:
        return False

    values.append(document_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", values)

    return True


def get_documents(chat_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Get all documents, optionally filtered by chat."""
    with get_connection() as conn:
        if chat_id:
            cursor = conn.execute(
                """
                SELECT id, filename, file_type, summary, chunk_count, status, created_at
                FROM documents
                WHERE chat_id = ? OR chat_id IS NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, filename, file_type, summary, chunk_count, status, created_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

    return [dict(row) for row in cursor.fetchall()]


def get_document(document_id: str) -> Optional[dict]:
    """Get a single document by ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, filename, file_type, file_path, content, summary, metadata, status, created_at
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        )
        row = cursor.fetchone()

    if not row:
        return None

    result = dict(row)
    if result["metadata"]:
        result["metadata"] = json.loads(result["metadata"])
    return result


def delete_document(document_id: str) -> bool:
    """Delete a document by ID."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return cursor.rowcount > 0


def search_documents(
    query: str, chat_id: Optional[str] = None, limit: int = 10
) -> list[dict]:
    """Full-text search across documents."""
    with get_connection() as conn:
        if chat_id:
            cursor = conn.execute(
                """
                SELECT d.id, d.filename, d.file_type, d.summary, d.status, d.created_at,
                       snippet(documents_fts, 2, '<mark>', '</mark>', '...', 30) as preview
                FROM documents d
                JOIN documents_fts fts ON d.rowid = fts.rowid
                WHERE d.chat_id = ?
                  AND documents_fts MATCH ?
                ORDER BY d.created_at DESC
                LIMIT ?
                """,
                (chat_id, query, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT d.id, d.filename, d.file_type, d.summary, d.status, d.created_at,
                       snippet(documents_fts, 2, '<mark>', '</mark>', '...', 30) as preview
                FROM documents d
                JOIN documents_fts fts ON d.rowid = fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY d.created_at DESC
                LIMIT ?
                """,
                (query, limit),
            )

    return [dict(row) for row in cursor.fetchall()]


# ========== Health Data CRUD ==========


def store_health_daily(data: dict) -> bool:
    """Store daily health metrics."""
    import uuid
    from datetime import date

    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO health_daily
            (id, date, steps, distance_meters, calories_total, calories_active,
             resting_heart_rate, avg_heart_rate, max_heart_rate, stress_avg,
             body_battery_high, body_battery_low, floors_climbed, intensity_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            data.get("date", date.today().isoformat()),
            data.get("steps", 0),
            data.get("distance_meters", 0),
            data.get("calories_total", 0),
            data.get("calories_active", 0),
            data.get("resting_heart_rate", 0),
            data.get("avg_heart_rate", 0),
            data.get("max_heart_rate", 0),
            data.get("stress_avg", 0),
            data.get("body_battery_high", 0),
            data.get("body_battery_low", 0),
            data.get("floors_climbed", 0),
            data.get("intensity_minutes", 0),
        ))
        return True


def get_health_daily(date: str) -> dict | None:
    """Get daily health metrics for a specific date."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM health_daily WHERE date = ?", (date,)
        ).fetchone()
        return dict(row) if row else None


def store_health_sleep(data: dict) -> bool:
    """Store sleep data."""
    import uuid

    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO health_sleep
            (id, date, sleep_start, sleep_end, duration_seconds,
             deep_sleep_seconds, light_sleep_seconds, rem_sleep_seconds,
             awake_seconds, sleep_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            data.get("date", ""),
            data.get("sleep_start", ""),
            data.get("sleep_end", ""),
            data.get("duration_seconds", 0),
            data.get("deep_sleep_seconds", 0),
            data.get("light_sleep_seconds", 0),
            data.get("rem_sleep_seconds", 0),
            data.get("awake_seconds", 0),
            data.get("sleep_score", 0),
        ))
        return True


def get_health_sleep(date: str) -> dict | None:
    """Get sleep data for a specific date."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM health_sleep WHERE date = ?", (date,)
        ).fetchone()
        return dict(row) if row else None


def store_health_activity(data: dict) -> bool:
    """Store activity/workout data."""
    import uuid

    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO health_activities
            (id, garmin_activity_id, activity_type, name, start_time,
             duration_seconds, distance_meters, avg_heart_rate, max_heart_rate,
             calories, avg_pace)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            data.get("garmin_activity_id", ""),
            data.get("activity_type", ""),
            data.get("name", ""),
            data.get("start_time", ""),
            data.get("duration_seconds", 0),
            data.get("distance_meters", 0),
            data.get("avg_heart_rate", 0),
            data.get("max_heart_rate", 0),
            data.get("calories", 0),
            data.get("avg_pace", ""),
        ))
        return True


def get_health_activities(limit: int = 10) -> list[dict]:
    """Get recent health activities."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM health_activities ORDER BY start_time DESC LIMIT {limit}"
        ).fetchall()
        return [dict(row) for row in rows]


def update_garmin_sync_state(last_sync_at: str | None = None,
                                  last_activity_sync_at: str | None = None) -> None:
    """Update Garmin sync state."""
    with get_connection() as conn:
        # Ensure the single row exists
        conn.execute("INSERT OR IGNORE INTO garmin_sync_state (id) VALUES (1)")

        updates = []
        params = []

        if last_sync_at:
            updates.append("last_sync_at = ?")
            params.append(last_sync_at)
        if last_activity_sync_at:
            updates.append("last_activity_sync_at = ?")
            params.append(last_activity_sync_at)

        if updates:
            conn.execute(
                f"UPDATE garmin_sync_state SET {', '.join(updates)} WHERE id = 1",
                params
            )


def get_garmin_sync_state() -> dict:
    """Get Garmin sync state."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM garmin_sync_state WHERE id = 1").fetchone()
        return dict(row) if row else {"id": 1, "last_sync_at": None, "last_activity_sync_at": None}


# Initialize on import
init_db()


# Initialize on import
init_db()
