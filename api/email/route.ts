"""
Email API - Email sync, authentication, and configuration endpoints.
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== Request/Response Models ==========


class SyncStatusResponse(BaseModel):
    """Email sync status response."""
    gmail_authenticated: bool
    outlook_authenticated: bool
    last_sync: str | None
    gmail_count: int = 0
    outlook_count: int = 0


class SyncRequest(BaseModel):
    """Request to trigger email sync."""
    force_initial: bool = False


class EmailClassificationConfigRequest(BaseModel):
    """Request to set email classification configuration."""
    provider_id: str
    model: str = ""  # Empty = use provider's default
    enabled: bool = True


# ========== Sync Endpoints ==========


@router.get("/status")
async def get_sync_status() -> SyncStatusResponse:
    """Get the current email sync status."""
    from database import get_connection
    from integrations import GMAIL_AVAILABLE, OUTLOOK_AVAILABLE, VaultManager
    from services.email_sync_service import get_sync_service

    sync_service = get_sync_service()
    state = sync_service.get_sync_state()

    # Get email counts
    gmail_count = 0
    outlook_count = 0

    try:
        with get_connection() as conn:
            # Gmail count
            if GMAIL_AVAILABLE:
                cursor = conn.execute("SELECT COUNT(*) as count FROM emails WHERE source = 'gmail'")
                row = cursor.fetchone()
                gmail_count = row["count"] if row else 0

            # Outlook count
            if OUTLOOK_AVAILABLE:
                cursor = conn.execute("SELECT COUNT(*) as count FROM emails WHERE source = 'outlook'")
                row = cursor.fetchone()
                outlook_count = row["count"] if row else 0
    except Exception as e:
        logger.error(f"Failed to get email counts: {e}")

    # Check authentication status
    vault = VaultManager()
    gmail_auth = vault.has_token(VaultManager.KEY_GMAIL_TOKEN) if GMAIL_AVAILABLE else False
    outlook_auth = vault.has_token(VaultManager.KEY_OUTLOOK_REFRESH) if OUTLOOK_AVAILABLE else False

    return SyncStatusResponse(
        gmail_authenticated=gmail_auth,
        outlook_authenticated=outlook_auth,
        last_sync=state.get("last_sync_at"),
        gmail_count=gmail_count,
        outlook_count=outlook_count,
    )


@router.post("/sync")
async def trigger_sync(request: SyncRequest) -> dict:
    """
    Trigger an email sync (initial or incremental).

    Args:
        request: Sync request with optional force_initial flag

    Returns:
        Sync results
    """
    from services.email_sync_service import get_sync_service

    sync_service = get_sync_service()

    try:
        results = await sync_service.sync_all(force_initial=request.force_initial)

        # Format results
        formatted = {}
        for provider, result in results.items():
            if "error" in result:
                formatted[f"{provider}_error"] = result["error"]
            else:
                formatted[f"{provider}_count"] = result.get("count", 0)

        formatted["last_sync"] = sync_service.get_sync_state().get("last_sync_at")
        return {"success": True, **formatted}

    except Exception as e:
        logger.error(f"Email sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start-background")
async def start_background_sync() -> dict:
    """Start the background email sync service."""
    from services.email_sync_service import get_sync_service

    sync_service = get_sync_service()

    if sync_service.is_running:
        return {"success": True, "message": "Background sync already running"}

    asyncio.create_task(sync_service.start_background_sync())
    return {"success": True, "message": "Background sync started"}


@router.post("/stop-background")
async def stop_background_sync() -> dict:
    """Stop the background email sync service."""
    from services.email_sync_service import get_sync_service

    sync_service = get_sync_service()

    if not sync_service.is_running:
        return {"success": True, "message": "Background sync not running"}

    await sync_service.stop_background_sync()
    return {"success": True, "message": "Background sync stopped"}


@router.get("/background-status")
async def background_sync_status() -> dict:
    """Check if background sync is running."""
    from services.email_sync_service import get_sync_service

    sync_service = get_sync_service()
    return {"running": sync_service.is_running}


# ========== Authentication Endpoints ==========


@router.get("/auth/gmail/url")
async def get_gmail_auth_url() -> dict:
    """
    Get Gmail OAuth URL (for browser-based OAuth flow).

    This is an alternative to the loopback flow - useful for web UI.
    The user will need to visit this URL and paste the authorization code back.
    """
    # For now, we use the loopback flow which is simpler
    # This endpoint can be extended to support OAuth callback
    return {
        "message": "Gmail uses loopback flow. Run sync to trigger authentication.",
        "instructions": "Click 'Sync' to open a browser for OAuth authentication."
    }


@router.post("/auth/gmail/revoke")
async def revoke_gmail_auth() -> dict:
    """Revoke Gmail authentication (delete stored tokens)."""
    from integrations import VaultManager

    vault = VaultManager()
    vault.delete_token(VaultManager.KEY_GMAIL_TOKEN)
    vault.delete_token(VaultManager.KEY_GMAIL_REFRESH)

    return {"success": True, "message": "Gmail authentication revoked"}


@router.post("/auth/outlook/revoke")
async def revoke_outlook_auth() -> dict:
    """Revoke Outlook authentication (delete stored tokens)."""
    from integrations import VaultManager

    vault = VaultManager()
    vault.delete_token(VaultManager.KEY_OUTLOOK_REFRESH)

    return {"success": True, "message": "Outlook authentication revoked"}


# ========== Configuration Endpoints ==========


@router.get("/config/classification")
async def get_classification_config() -> dict:
    """Get the email classification model configuration."""
    from config import get_email_classification_config

    config_data = get_email_classification_config()

    # Get available providers
    from config import get_all_provider_configs

    providers = []
    for provider_id, provider_data in get_all_provider_configs().items():
        if provider_data.get("enabled", True):
            providers.append({
                "id": provider_id,
                "model": provider_data["config"].get("model", ""),
            })

    return {
        "current": config_data,
        "available_providers": providers,
    }


@router.post("/config/classification")
async def set_classification_config(request: EmailClassificationConfig) -> dict:
    """
    Set the email classification model configuration.

    Args:
        request: Classification configuration request

    Returns:
        Success status
    """
    from config import save_email_classification_config

    # Validate provider exists
    from config import get_all_provider_configs

    providers = get_all_provider_configs()
    if request.provider_id not in providers:
        raise HTTPException(status_code=404, detail=f"Provider not found: {request.provider_id}")

    # Save configuration
    save_email_classification_config(
        request.provider_id,
        {"model": request.model}
    )

    logger.info(f"Email classification config updated: {request.provider_id}/{request.model}")
    return {"success": True}


# ========== Reminders Endpoints ==========


class ReminderListResponse(BaseModel):
    """List of reminders response."""
    reminders: list[dict]
    total: int


@router.get("/reminders")
async def get_reminders(
    status: str = "pending",
    limit: int = 20,
) -> ReminderListResponse:
    """
    Get reminders with optional filtering.

    Args:
        status: Filter by status (pending, completed, dismissed, overdue)
        limit: Maximum results

    Returns:
        List of reminders
    """
    from database import get_connection
    from datetime import datetime

    try:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: dict.fromkeys(
                [col[0] for col in cursor.description], row
            )

            query = "SELECT * FROM reminders WHERE 1=1"
            params = []

            if status and status != "all":
                if status == "overdue":
                    query += " AND status = 'pending' AND (due_date IS NULL OR due_date < datetime('now'))"
                else:
                    query += " AND status = ?"
                    params.append(status)

            query += " ORDER BY due_date ASC, created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, tuple(params))
            reminders = cursor.fetchall()

            return ReminderListResponse(
                reminders=reminders,
                total=len(reminders),
            )

    except Exception as e:
        logger.error(f"Failed to get reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str) -> dict:
    """Mark a reminder as completed."""
    from database import get_connection
    from datetime import datetime

    try:
        with get_connection() as conn:
            conn.execute("""
                UPDATE reminders
                SET status = 'completed', completed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), reminder_id))
            conn.commit()

        return {"success": True, "reminder_id": reminder_id}

    except Exception as e:
        logger.error(f"Failed to complete reminder {reminder_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reminders/{reminder_id}/dismiss")
async def dismiss_reminder(reminder_id: str) -> dict:
    """Dismiss a reminder."""
    from database import get_connection

    try:
        with get_connection() as conn:
            conn.execute("""
                UPDATE reminders
                SET status = 'dismissed'
                WHERE id = ?
            """, (reminder_id,))
            conn.commit()

        return {"success": True, "reminder_id": reminder_id}

    except Exception as e:
        logger.error(f"Failed to dismiss reminder {reminder_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
