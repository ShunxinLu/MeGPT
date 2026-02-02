"""
Email API Routes

Endpoints for:
- Email sync status and control
- Email classification configuration
- Reminders management
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Literal
import logging

from config import (
    get_email_classification_config,
    save_email_classification_config,
    EmailConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])


# ========== Request/Response Models ==========


class ClassificationConfigResponse(BaseModel):
    """Email classification model configuration"""
    provider_id: str
    model: str


class ClassificationConfigRequest(BaseModel):
    """Request to update email classification model"""
    provider_id: str
    model: str


class SyncStatusResponse(BaseModel):
    """Email sync status"""
    gmail_enabled: bool
    gmail_connected: bool
    gmail_last_sync: Optional[str] = None
    outlook_enabled: bool
    outlook_connected: bool
    outlook_last_sync: Optional[str] = None
    background_sync_running: bool


class SyncRequest(BaseModel):
    """Request to trigger sync"""
    force_full: bool = False


class ReminderResponse(BaseModel):
    """Reminder item"""
    id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: str


# ========== Endpoints ==========


@router.get("/config/classification", response_model=ClassificationConfigResponse)
async def get_classification_config() -> ClassificationConfigResponse:
    """
    Get the current email classification model configuration.

    Returns the provider_id and model used for email processing.
    """
    config = get_email_classification_config()
    return ClassificationConfigResponse(
        provider_id=config["provider_id"],
        model=config.get("model", ""),
    )


@router.post("/config/classification")
async def set_classification_config(request: ClassificationConfigRequest) -> dict:
    """
    Set the email classification model configuration.

    Args:
        request: ClassificationConfigRequest with provider_id and model

    Returns:
        Success message
    """
    try:
        save_email_classification_config(request.provider_id, request.model)
        logger.info(f"Email classification model updated: {request.provider_id}/{request.model}")
        return {"status": "success", "message": "Classification model updated"}
    except Exception as e:
        logger.error(f"Failed to update classification model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status() -> SyncStatusResponse:
    """
    Get email sync status for all providers.

    Returns connection status and last sync time for Gmail and Outlook.
    """
    from database import get_connection

    with get_connection() as conn:
        # Get sync state
        cursor = conn.execute("""
            SELECT gmail_history_id, outlook_delta_link, last_sync_at
            FROM email_sync_state
            WHERE id = 1
        """)
        row = cursor.fetchone()

        last_sync = row["last_sync_at"] if row else None

        # Check if credentials exist (connection status)
        gmail_connected = row and row["gmail_history_id"] is not None
        outlook_connected = row and row["outlook_delta_link"] is not None

    return SyncStatusResponse(
        gmail_enabled=True,
        gmail_connected=gmail_connected,
        gmail_last_sync=last_sync,
        outlook_enabled=True,
        outlook_connected=outlook_connected,
        outlook_last_sync=last_sync,
        background_sync_running=False,  # TODO: Track actual background sync state
    )


@router.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks, request: SyncRequest = SyncRequest()) -> dict:
    """
    Trigger email sync for all configured providers.

    Args:
        background_tasks: FastAPI background tasks
        request: Optional force_full flag to force full sync

    Returns:
        Sync status message
    """
    async def run_sync():
        """Run email sync in background"""
        try:
            from services.email_sync_service import get_sync_service
            sync_service = get_sync_service()
            await sync_service.sync_all(force_initial=request.force_full)
        except Exception as e:
            logger.error(f"Background sync failed: {e}")

    # Run sync in background
    background_tasks.add_task(run_sync)

    return {
        "status": "started",
        "message": "Email sync started in background",
        "force_full": request.force_full,
    }


@router.post("/start-background")
async def start_background_sync() -> dict:
    """Start background periodic email sync."""
    # TODO: Implement background sync service
    return {"status": "started", "message": "Background sync started"}


@router.post("/stop-background")
async def stop_background_sync() -> dict:
    """Stop background periodic email sync."""
    # TODO: Implement background sync service
    return {"status": "stopped", "message": "Background sync stopped"}


@router.get("/reminders", response_model=list[ReminderResponse])
async def get_reminders(
    limit: int = 10,
    status: Optional[Literal["pending", "completed", "overdue"]] = None
) -> list[ReminderResponse]:
    """
    Get reminders with optional filtering.

    Args:
        limit: Maximum number of reminders to return
        status: Filter by status (pending, completed, overdue)

    Returns:
        List of reminders
    """
    from database import get_connection

    query = "SELECT id, title, description, due_date, priority, status FROM reminders"
    params = []

    if status == "pending":
        query += " WHERE status = 'pending' AND (due_date IS NULL OR due_date > datetime('now')"
    elif status == "overdue":
        query += " WHERE status = 'pending' AND due_date < datetime('now')"
    elif status == "completed":
        query += " WHERE status = 'completed'"

    query += " ORDER BY due_date ASC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    return [
        ReminderResponse(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            due_date=row["due_date"],
            priority=row["priority"],
            status=row["status"],
        )
        for row in rows
    ]


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str) -> dict:
    """
    Mark a reminder as completed.

    Args:
        reminder_id: ID of the reminder to complete

    Returns:
        Success message
    """
    from database import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE reminders SET status = 'completed' WHERE id = ?",
            (reminder_id,)
        )

    return {"status": "success", "message": "Reminder marked as completed"}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str) -> dict:
    """
    Delete a reminder.

    Args:
        reminder_id: ID of the reminder to delete

    Returns:
        Success message
    """
    from database import get_connection

    with get_connection() as conn:
        conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    return {"status": "success", "message": "Reminder deleted"}


# ========== Email List Endpoints ==========


class EmailResponse(BaseModel):
    """Email item with action items"""
    id: str
    threadId: str
    subject: str
    sender: str
    senderEmail: str
    body: str
    date: str
    priority: Literal["critical", "important", "normal", "low", "spam"]
    category: str
    isRead: bool
    isSpam: bool
    hasAttachments: bool
    summary: str
    actionItems: list[str]


class EmailListResponse(BaseModel):
    """Paginated email list response"""
    emails: list[EmailResponse]
    total: int
    page: int
    perPage: int


@router.get("/emails", response_model=EmailListResponse)
async def list_emails(
    page: int = 1,
    per_page: int = 50,
    priority: Optional[Literal["critical", "important", "normal", "low", "spam"]] = None,
    category: Optional[str] = None,
    is_read: Optional[bool] = None,
    search: Optional[str] = None,
) -> EmailListResponse:
    """
    List emails with pagination and filtering.

    Args:
        page: Page number (1-indexed)
        per_page: Items per page
        priority: Filter by priority level
        category: Filter by category
        is_read: Filter by read status
        search: Full-text search query

    Returns:
        Paginated email list with action items
    """
    from database import get_connection

    # Build query with filters
    query = """
        SELECT
            e.id,
            e.thread_id,
            e.subject,
            e.sender,
            e.sender_email,
            e.body_markdown,
            e.summary,
            e.priority,
            e.category,
            e.is_read,
            e.is_spam_or_scam,
            e.date_received,
            e.source,
            e.folder,
            e.labels
        FROM emails e
        WHERE 1=1
    """
    params = []

    # Apply filters
    if priority:
        query += " AND e.priority = ?"
        params.append(priority)

    if category:
        query += " AND e.category = ?"
        params.append(category)

    if is_read is not None:
        query += " AND e.is_read = ?"
        params.append(1 if is_read else 0)

    if search:
        # Use FTS for search - subquery pattern
        query = """
            SELECT
                e.id,
                e.thread_id,
                e.subject,
                e.sender,
                e.sender_email,
                e.body_markdown,
                e.summary,
                e.priority,
                e.category,
                e.is_read,
                e.is_spam_or_scam,
                e.date_received,
                e.source,
                e.folder,
                e.labels
            FROM emails e
            WHERE e.rowid IN (
                SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?
            )
        """
        params.append(search)

        # Add additional filters to FTS query
        if priority:
            query += " AND e.priority = ?"
            params.append(priority)
        if category:
            query += " AND e.category = ?"
            params.append(category)
        if is_read is not None:
            query += " AND e.is_read = ?"
            params.append(1 if is_read else 0)

    # Order by date descending
    query += " ORDER BY e.date_received DESC"

    # Get total count
    count_query = f"SELECT COUNT(*) as count FROM ({query})"
    with get_connection() as conn:
        count_row = conn.execute(count_query, params).fetchone()
        total = count_row["count"] if count_row else 0

    # Add pagination
    offset = (page - 1) * per_page
    query += " LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    # Fetch emails
    with get_connection() as conn:
        email_rows = conn.execute(query, params).fetchall()

    # Build response with action items from reminders
    emails = []
    for row in email_rows:
        email_id = row["id"]

        # Fetch action items for this email
        with get_connection() as conn:
            reminder_rows = conn.execute(
                """
                SELECT title, description
                FROM reminders
                WHERE source_type = 'email' AND source_id = ?
                ORDER BY created_at DESC
                """,
                (email_id,),
            ).fetchall()

        action_items = [r["title"] for r in reminder_rows if r["title"]]

        # Check for attachments (from labels)
        has_attachments = False
        if row["labels"]:
            try:
                import json
                labels = json.loads(row["labels"])
                has_attachments = any(
                    label.lower() in ["attachment", "attachments", "has_attachment"]
                    for label in labels
                )
            except (json.JSONDecodeError, TypeError):
                pass

        emails.append(
            EmailResponse(
                id=row["id"],
                threadId=row["thread_id"] or "",
                subject=row["subject"] or "(No subject)",
                sender=row["sender"] or "Unknown",
                senderEmail=row["sender_email"] or "",
                body=row["body_markdown"] or "",
                date=row["date_received"] or "",
                priority=row["priority"] or "normal",
                category=row["category"] or "other",
                isRead=bool(row["is_read"]),
                isSpam=bool(row["is_spam_or_scam"]),
                hasAttachments=has_attachments,
                summary=row["summary"] or "",
                actionItems=action_items,
            )
        )

    return EmailListResponse(
        emails=emails,
        total=total,
        page=page,
        perPage=per_page,
    )


@router.get("/emails/{email_id}", response_model=EmailResponse)
async def get_email(email_id: str) -> EmailResponse:
    """
    Get a single email by ID with action items.

    Args:
        email_id: ID of the email

    Returns:
        Email with action items
    """
    from database import get_connection
    import json

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                e.id,
                e.thread_id,
                e.subject,
                e.sender,
                e.sender_email,
                e.body_markdown,
                e.summary,
                e.priority,
                e.category,
                e.is_read,
                e.is_spam_or_scam,
                e.date_received,
                e.source,
                e.folder,
                e.labels
            FROM emails e
            WHERE e.id = ?
            """,
            (email_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    # Fetch action items for this email
    with get_connection() as conn:
        reminder_rows = conn.execute(
            """
            SELECT title, description
            FROM reminders
            WHERE source_type = 'email' AND source_id = ?
            ORDER BY created_at DESC
            """,
            (email_id,),
        ).fetchall()

    action_items = [r["title"] for r in reminder_rows if r["title"]]

    # Check for attachments
    has_attachments = False
    if row["labels"]:
        try:
            labels = json.loads(row["labels"])
            has_attachments = any(
                label.lower() in ["attachment", "attachments", "has_attachment"]
                for label in labels
            )
        except (json.JSONDecodeError, TypeError):
            pass

    return EmailResponse(
        id=row["id"],
        threadId=row["thread_id"] or "",
        subject=row["subject"] or "(No subject)",
        sender=row["sender"] or "Unknown",
        senderEmail=row["sender_email"] or "",
        body=row["body_markdown"] or "",
        date=row["date_received"] or "",
        priority=row["priority"] or "normal",
        category=row["category"] or "other",
        isRead=bool(row["is_read"]),
        isSpam=bool(row["is_spam_or_scam"]),
        hasAttachments=has_attachments,
        summary=row["summary"] or "",
        actionItems=action_items,
    )


@router.post("/emails/{email_id}/read")
async def mark_email_read(email_id: str) -> dict:
    """
    Mark an email as read.

    Args:
        email_id: ID of the email to mark as read

    Returns:
        Success message
    """
    from database import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE emails SET is_read = 1 WHERE id = ?",
            (email_id,)
        )

    return {"status": "success", "message": "Email marked as read"}


@router.delete("/emails/{email_id}")
async def delete_email(email_id: str) -> dict:
    """
    Delete an email.

    Args:
        email_id: ID of the email to delete

    Returns:
        Success message
    """
    from database import get_connection

    with get_connection() as conn:
        conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))

    return {"status": "success", "message": "Email deleted"}
