"""
FastAPI Backend Server - SSE streaming with Vercel AI Data Stream Protocol.
Brain Transplant: Routes through agent_graph.py for proper tool execution.
"""

import asyncio
import json
import logging
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from config import config
from fastapi import Request
from fastapi.responses import JSONResponse
from exceptions import MeGPTError

# Configure logging with rotation (10-day retention)
from utils.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
from database import (
    create_chat,
    get_chats,
    get_chat,
    update_chat_title,
    delete_chat,
    add_message,
    get_messages,
    search_chats,
    get_message_count,
)
from tools.memory_tool import get_all_memories, delete_memory, delete_memories_for_chat
from tools.summary_tool import summarize_chat_background
from tools.backup_tool import (
    create_backup,
    list_backups,
    restore_backup,
    rollback_latest,
)
from tools.email_tools import (
    search_emails,
    get_email_thread,
    list_unread_emails,
    get_email_count,
)
from tools.calendar_tools import (
    get_upcoming_events,
    create_event,
    get_calendar_proposals,
    approve_proposal,
    reject_proposal,
    update_event,
    delete_event,
)
from utils.model_loader import ensure_models_loaded
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

# Import provider management API
from api.providers import router as providers_router

# Import documents API
from api.documents import router as documents_router

# Import email API
from api.email import router as email_router

app = FastAPI(
    title="MeGPT Pro API",
    description="Privacy-first AI assistant with persistent memory",
    version="4.0.0",
)

# Include provider management routes
app.include_router(providers_router)

# Include documents routes
app.include_router(documents_router)

# Include email routes
app.include_router(email_router)


@app.on_event("startup")
async def startup_event():
    """Load models on server startup and start periodic sync scheduler."""
    logger.info("Loading models in LM Studio...")
    success = await ensure_models_loaded()
    if success:
        logger.info("Models ready!")
    else:
        logger.warning("Models may not be loaded - check LM Studio")

    # Validate authentication in production
    if config.is_production and config.api_key is None:
        logger.error("SECURITY WARNING: API_KEY not set in production mode!")
        logger.error("Set API_KEY environment variable to secure your API.")

    # Start periodic sync scheduler and store reference
    logger.info("Starting background sync scheduler...")
    global _sync_scheduler_task
    _sync_scheduler_task = asyncio.create_task(periodic_sync_scheduler())


# Global reference for sync scheduler task
_sync_scheduler_task = None


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    global _sync_scheduler_task
    if _sync_scheduler_task:
        _sync_scheduler_task.cancel()
        try:
            await _sync_scheduler_task
        except asyncio.CancelledError:
            pass


async def periodic_sync_scheduler():
    """
    Run periodic sync tasks for all domains.

    Syncs run on different schedules:
    - Email: Every 30 minutes
    - Calendar: Every 15 minutes
    """
    consecutive_failures = 0

    while True:
        try:
            # Run all syncs
            await run_email_sync("Periodic scheduler")
            await run_calendar_sync("Periodic scheduler")

            consecutive_failures = 0  # Reset on success
            logger.info("Sync cycle complete, waiting 1 hour until next cycle")
            await asyncio.sleep(3600)  # 1 hour in seconds

        except Exception as e:
            consecutive_failures += 1
            logger.error(f"Scheduler error (failure {consecutive_failures}): {e}", exc_info=True)
            if consecutive_failures >= 3:
                logger.critical("[SYNC] Multiple consecutive failures - check services")
            # Wait 5 minutes before retry with exponential backoff
            wait_time = min(300 * (2 ** (consecutive_failures - 1)), 3600)
            await asyncio.sleep(wait_time)


# Enable CORS for Next.js frontend
# Use environment variable for allowed origins in production
import os
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== Exception Handlers ==========

@app.exception_handler(MeGPTError)
async def megpt_exception_handler(request: Request, exc: MeGPTError):
    """Handle MeGPT custom exceptions."""
    # Log error with context
    logger.error(f"MeGPTError: {exc} | details: {exc.details}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions with consistent formatting."""
    # Log the error (HTTPException might not have full context)
    logger.warning(f"HTTPException: {exc.detail}")
    
    # Preserve existing FastAPI format for backward compatibility
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions with sanitized error messages."""
    # Log the full error for debugging
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Sanitize error message for production
    error_msg = str(exc) if not config.is_production else "Internal server error"
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": error_msg,
            "error_code": "internal_server_error",
        },
    )


# ========== Pydantic Models ==========


class Message(BaseModel):
    role: str
    content: str

    @field_validator("content")
    @classmethod
    def validate_content_length(cls, v: str) -> str:
        """Validate message content doesn't exceed maximum length."""
        max_length = 50000
        if len(v) > max_length:
            raise ValueError(
                f"Message content exceeds maximum length of {max_length} characters"
            )
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is one of the allowed values."""
        allowed_roles = {"user", "assistant", "system"}
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of {allowed_roles}")
        return v


class ChatRequest(BaseModel):
    messages: list[Message]
    user_id: Optional[str] = None
    chat_id: Optional[str] = None


class ChatCreate(BaseModel):
    title: Optional[str] = None


class ChatUpdate(BaseModel):
    title: str


class HealthResponse(BaseModel):
    status: str
    llm_url: str
    qdrant_host: str


class CreateEventRequest(BaseModel):
    """Request to create a calendar event."""
    title: str
    start_time: str
    end_time: str
    location: str = ""
    description: str = ""
    attendees: list[str] = []
    chat_id: str = ""

    @field_validator("attendees", mode="before")
    @classmethod
    def parse_attendees(cls, v):
        """Parse attendees from JSON string if needed."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse attendees JSON: {e}")
                return []
        return v


class UpdateEventRequest(BaseModel):
    """Request to update a calendar event."""
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: Optional[list[str]] = None


class RejectProposalRequest(BaseModel):
    """Request to reject a calendar proposal."""
    reason: str = ""


# ========== NOTE: SYSTEM_PROMPT is now in agent_graph.py ==========
# The Agent Graph manages all context and tool execution.


# ========== Authentication ==========


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """
    Optional API key verification.
    If API_KEY is set in config, the request must include a matching X-API-Key header.
    If API_KEY is not set, authentication is disabled (default for local use).
    """
    if config.api_key is not None:
        if x_api_key is None:
            raise HTTPException(
                status_code=401,
                detail="API key required. Set X-API-Key header or disable API_KEY in config.",
            )
        if x_api_key != config.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")


async def verify_admin_api_key(x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key")) -> None:
    """
    Admin API key verification for privileged operations.

    Requires ADMIN_API_KEY if set, otherwise falls back to API_KEY.
    In production mode, authentication is always required.
    """
    admin_key = config.admin_api_key or config.api_key

    if admin_key is not None:
        if x_admin_api_key is None:
            raise HTTPException(
                status_code=401,
                detail="Admin API key required. Set X-Admin-API-Key header.",
            )
        if x_admin_api_key != admin_key:
            logger.warning(f"Failed admin API key authentication attempt")
            raise HTTPException(status_code=403, detail="Invalid admin API key")
    elif config.is_production:
        # Production mode requires authentication even if not configured
        raise HTTPException(
            status_code=401,
            detail="Admin API key required in production mode. Set ADMIN_API_KEY environment variable.",
        )


# ========== Helpers ==========


def sanitize_fts5_query(query: str) -> str:
    """
    Sanitize FTS5 search query to prevent injection.

    Removes or escapes FTS5 special characters: *, ", (, ), -, NOT, AND, OR, NEAR
    """
    if not query:
        return ""

    # Remove FTS5 special characters that can be used for injection
    # Replace quotes with spaces, remove wildcards and operators
    sanitized = query.replace('"', ' ')
    sanitized = sanitized.replace('*', ' ')
    sanitized = sanitized.replace('(', ' ')
    sanitized = sanitized.replace(')', ' ')

    # Remove FTS5 operators (case-insensitive)
    import re
    sanitized = re.sub(r'\b(AND|OR|NOT|NEAR)\b', '', sanitized, flags=re.IGNORECASE)

    # Clean up extra whitespace
    sanitized = ' '.join(sanitized.split())

    # Limit query length to prevent DoS
    return sanitized[:500]


def validate_limit(limit: int, default: int = 5, max_val: int = 100) -> int:
    """Validate and clamp limit parameter."""
    if limit < 1:
        return default
    if limit > max_val:
        return max_val
    return limit


def convert_messages(messages: list[Message]) -> list[BaseMessage]:
    """Convert API messages to LangChain message format."""
    result = []
    for msg in messages:
        if msg.role == "user":
            result.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            result.append(AIMessage(content=msg.content))
        elif msg.role == "system":
            result.append(SystemMessage(content=msg.content))
    return result


def format_event(event_type: str, content: str) -> str:
    """Format event for Vercel AI Data Stream Protocol."""
    return f"0:{json.dumps({'type': event_type, 'content': content})}\n"


async def stream_response(
    messages: list[Message],
    user_id: str,
    chat_id: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
):
    """
    Stream LLM response through Agent Graph.
    Brain Transplant: Routes through agent_graph.py for proper tool execution.
    """
    from agent_graph import create_agent_graph
    from langchain_core.messages import HumanMessage

    # Get the last user message
    user_messages = [m for m in messages if m.role == "user"]
    last_user_input = user_messages[-1].content if user_messages else ""

    # Status: Starting
    yield format_event("status", "🧠 Recalling memories...")

    # Agent graph now handles adaptive context management
    # Just send current input - let agent_graph fetch DB history smartly
    history = [HumanMessage(content=last_user_input)]

    full_response = ""
    last_node = ""

    try:
        # Create agent graph
        agent = create_agent_graph()

        # Stream from LangGraph using astream (yields state updates per node)
        async for state_update in agent.astream(
            input={
                "messages": [],
                "user_input": last_user_input,
                "chat_id": chat_id,
                "user_id": user_id,
                "context": {},
                "final_response": "",
                "tool_call_count": 0,
            },
            stream_mode="updates",  # Get updates per node
        ):
            # state_update is a dict with node name as key
            for node_name, node_output in state_update.items():
                print(f"[Node] '{node_name}' completed")

                # Track status based on node
                if node_name == "recall":
                    yield format_event("status", "🧠 Context loaded...")
                elif node_name == "reason":
                    yield format_event("status", "💭 Thinking...")
                elif node_name == "tools":
                    yield format_event("status", "🔎 Using web_search...")
                elif node_name == "answer":
                    yield format_event("status", "💭 Synthesizing answer...")
                elif node_name == "respond":
                    # Get the final response from state
                    final = node_output.get("final_response", "")
                    if final:
                        full_response = final
                        yield format_event("text", final)
                elif node_name == "memorize":
                    yield format_event("status", "💾 Saved to memory")

        # ========== Background Summary ==========
        if chat_id and background_tasks:
            try:
                msg_count = get_message_count(chat_id)
                # Update summary more frequently in long conversations
                # Every 5 messages normally, every 3 if > 15 messages
                trigger_threshold = 3 if msg_count > 15 else 5
                if msg_count > 0 and msg_count % trigger_threshold == 0:
                    background_tasks.add_task(summarize_chat_background, chat_id)
            except Exception as e:
                logger.error(f"Failed to schedule background summarization for chat {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
        # Sanitize error messages before sending to client
        error_msg = str(e) if not config.is_production else "An error occurred during processing"
        yield format_event("error", error_msg)


# ========== Health Check ==========


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Redact internal URLs in production mode
    if config.is_production:
        return HealthResponse(
            status="ok",
            llm_url="(configured)",
            qdrant_host="(configured)",
        )
    return HealthResponse(
        status="ok",
        llm_url=config.llm_base_url,
        qdrant_host=f"{config.qdrant_host}:{config.qdrant_port}",
    )


# ========== Chat Endpoints ==========


@app.get("/api/chats")
async def list_chats(user_id: Optional[str] = None):
    """List all chats for a user."""
    uid = user_id or config.user_id
    return get_chats(uid)


@app.get("/api/chats/search")
async def search_chats_endpoint(q: str, user_id: Optional[str] = None):
    """Full-text search across chat messages."""
    uid = user_id or config.user_id
    sanitized_q = sanitize_fts5_query(q)
    return search_chats(uid, sanitized_q)


@app.post("/api/chats")
async def create_chat_endpoint(data: ChatCreate, user_id: Optional[str] = None):
    """Create a new chat."""
    uid = user_id or config.user_id
    return create_chat(uid, data.title)


@app.get("/api/chats/{chat_id}")
async def get_chat_endpoint(chat_id: str):
    """Get a single chat by ID."""
    chat = get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.patch("/api/chats/{chat_id}")
async def update_chat_endpoint(chat_id: str, data: ChatUpdate):
    """Update a chat's title."""
    update_chat_title(chat_id, data.title)
    return {"success": True}


@app.delete("/api/chats/{chat_id}")
async def delete_chat_endpoint(chat_id: str, user_id: Optional[str] = None):
    """
    Delete a chat with cascading memory deletion.
    Phase 3: Wipes Tier 1 (Archive), Tier 2 (Facts), and Tier 3 (Summary).

    SAFETY: Delete Qdrant memories FIRST, then SQLite.
    This prevents orphaned memories if SQLite delete fails.
    If Qdrant delete fails, we don't delete the chat and user can retry.
    """
    uid = user_id or config.user_id

    logger.info(f"Starting cascading delete for chat {chat_id[:8]}...")

    # STEP 1: Delete Qdrant memories FIRST (prevents orphaning)
    deleted_memories = delete_memories_for_chat(chat_id, uid)

    # STEP 2: Delete SQLite after memories are deleted
    try:
        delete_chat(chat_id)
    except Exception as e:
        logger.error(f"Failed to delete chat from SQLite: {e}")
        # Memories are already deleted, but chat still exists - log this inconsistency
        logger.warning(f"Memories deleted for {chat_id[:8]} but chat record remains")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    logger.info(f"Chat and {deleted_memories} memories permanently deleted")
    return {"success": True, "deleted_memories": deleted_memories}


# ========== Message Endpoints ==========


@app.get("/api/chats/{chat_id}/messages")
async def get_messages_endpoint(chat_id: str):
    """Get all messages for a chat."""
    return get_messages(chat_id)


@app.post("/api/chats/{chat_id}/messages")
async def add_message_endpoint(chat_id: str, msg: Message):
    """Add a message to a chat."""
    return add_message(chat_id, msg.role, msg.content)


# ========== Memory Endpoints ==========


@app.get("/api/memories")
async def list_memories(user_id: Optional[str] = None):
    """List all stored memories for a user."""
    uid = user_id or config.user_id
    return get_all_memories(uid)


@app.delete("/api/memories/{memory_id}")
async def delete_memory_endpoint(memory_id: str):
    """Delete a specific memory."""
    success = delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or delete failed")
    return {"success": True}


# ========== Domain Endpoints: Email ==========


@app.get("/api/emails/search")
async def search_emails_endpoint(
    q: str,
    limit: int = 5,
    priority: str = "all",
    _auth: None = Depends(verify_api_key),
):
    """Search emails by content."""
    validated_limit = validate_limit(limit, default=5, max_val=100)
    sanitized_q = sanitize_fts5_query(q)
    result = search_emails.invoke({"query": sanitized_q, "limit": validated_limit, "priority": priority})
    return {"results": result}


@app.get("/api/emails/{email_id}/thread")
async def get_email_thread_endpoint(
    email_id: str, _auth: None = Depends(verify_api_key)
):
    """Get full email thread."""
    result = get_email_thread.invoke({"email_id": email_id})
    return {"thread": result}


@app.get("/api/emails/unread")
async def list_unread_emails_endpoint(
    limit: int = 10, _auth: None = Depends(verify_api_key)
):
    """List unread emails."""
    validated_limit = validate_limit(limit, default=10, max_val=100)
    result = list_unread_emails.invoke({"limit": validated_limit})
    return {"emails": result}


@app.get("/api/emails/count")
async def get_email_count_endpoint(
    priority: str = "all", _auth: None = Depends(verify_api_key)
):
    """Get email count by priority."""
    result = get_email_count.invoke({"priority": priority})
    return {"counts": result}


@app.get("/api/emails/notifications")
async def get_email_notifications_endpoint(_auth: None = Depends(verify_api_key)):
    """
    Get smart notification counts - only important items worth notifying about.

    Returns:
        Structured counts for critical/important emails (excludes spam/low priority)
    """
    from database import get_connection

    try:
        with get_connection() as conn:
            # Count only critical and important emails that are unread
            cursor = conn.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE priority = 'critical') as critical,
                    COUNT(*) FILTER (WHERE priority = 'important') as important
                FROM emails
                WHERE is_read = 0
                  AND is_spam_or_scam = 0
            """)

            row = cursor.fetchone()
            critical_count = row["critical"] if row else 0
            important_count = row["important"] if row else 0
            total_important = critical_count + important_count

            # Also get a brief summary of the most critical item
            cursor = conn.execute("""
                SELECT subject, sender, priority
                FROM emails
                WHERE is_read = 0
                  AND is_spam_or_scam = 0
                  AND priority = 'critical'
                ORDER BY date_received DESC
                LIMIT 1
            """)

            top_critical = cursor.fetchone()

            return {
                "critical": critical_count,
                "important": important_count,
                "total_important": total_important,
                "summary": f"{critical_count} critical, {important_count} important emails",
                "top_critical": {
                    "subject": top_critical["subject"] if top_critical else None,
                    "sender": top_critical["sender"] if top_critical else None,
                } if top_critical else None
            }
    except Exception as e:
        logger.error(f"Error fetching email notifications: {e}")
        return {"critical": 0, "important": 0, "total_important": 0}


# ========== Domain Endpoints: Calendar ==========


@app.get("/api/calendar/events")
async def get_upcoming_events_endpoint(
    days: int = 7, _auth: None = Depends(verify_api_key)
):
    """Get upcoming calendar events."""
    validated_days = validate_limit(days, default=7, max_val=365)
    result = get_upcoming_events.invoke({"days": validated_days})
    return {"events": result}


@app.post("/api/calendar/events")
async def create_event_endpoint(
    data: CreateEventRequest,
    _auth: None = Depends(verify_api_key),
):
    """Create a new calendar event."""
    result = create_event.invoke(
        {
            "title": data.title,
            "start_time": data.start_time,
            "end_time": data.end_time,
            "location": data.location,
            "description": data.description,
            "attendees": json.dumps(data.attendees),
            "chat_id": data.chat_id,
        }
    )
    return {"event": result}


@app.get("/api/calendar/proposals")
async def get_calendar_proposals_endpoint(_auth: None = Depends(verify_api_key)):
    """Get pending calendar proposals."""
    result = get_calendar_proposals.invoke({})
    return {"proposals": result}


@app.post("/api/calendar/proposals/{proposal_id}/approve")
async def approve_proposal_endpoint(
    proposal_id: int, _auth: None = Depends(verify_api_key)
):
    """Approve a calendar proposal."""
    result = approve_proposal.invoke({"proposal_id": proposal_id})
    return {"proposal": result}


@app.post("/api/calendar/proposals/{proposal_id}/reject")
async def reject_proposal_endpoint(
    proposal_id: str,
    data: RejectProposalRequest = RejectProposalRequest(),
    _auth: None = Depends(verify_api_key),
):
    """Reject a calendar proposal."""
    result = reject_proposal.invoke({"proposal_id": proposal_id, "reason": data.reason})
    return {"proposal": result}


@app.patch("/api/calendar/events/{event_id}")
async def update_event_endpoint(
    event_id: str,
    data: UpdateEventRequest,
    _auth: None = Depends(verify_api_key),
):
    """Update a calendar event."""
    # Filter out None values
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = update_event.invoke({"event_id": event_id, "updates": updates})
    return {"event": result}


@app.delete("/api/calendar/events/{event_id}")
async def delete_event_endpoint(event_id: str, _auth: None = Depends(verify_api_key)):
    """Delete a calendar event."""
    result = delete_event.invoke({"event_id": event_id})
    return {"event": result}


# ========== Sync Endpoints ==========


class SyncRequest(BaseModel):
    """Request to trigger background sync."""
    sync_type: str  # "email", "calendar", or "all"
    model_config = {"json_schema_extra": {"examples": [{"sync_type": "all"}]}}

    @field_validator("sync_type")
    @classmethod
    def validate_sync_type(cls, v: str) -> str:
        """Validate sync_type is one of the allowed values."""
        allowed = {"email", "calendar", "all"}
        if v not in allowed:
            raise ValueError(f"sync_type must be one of {allowed}")
        return v


@app.post("/api/sync/trigger")
async def trigger_sync_endpoint(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    _auth: None = Depends(verify_api_key),
):
    """
    Trigger background sync for specified domain(s).

    This endpoint starts async sync tasks that run in the background.
    Returns immediately while sync continues in background.
    """
    sync_types = request.sync_type.lower()

    if sync_types == "all":
        # Trigger all syncs
        background_tasks.add_task(
            run_email_sync,
            "Triggered via API",
        )
        background_tasks.add_task(
            run_calendar_sync,
            "Triggered via API",
        )
        message = "Sync started for all domains (email, calendar)"
    elif sync_types == "email":
        background_tasks.add_task(
            run_email_sync,
            "Triggered via API",
        )
        message = "Email sync started"
    elif sync_types == "calendar":
        background_tasks.add_task(
            run_calendar_sync,
            "Triggered via API",
        )
        message = "Calendar sync started"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid sync type: {sync_types}")

    return {
        "status": "sync_started",
        "sync_type": sync_types,
        "message": message,
    }


# ========== Domain Endpoints: Health ==========


@app.get("/api/garmin/status")
async def get_garmin_status():
    """Check if Garmin is connected and authenticated."""
    try:
        from integrations.garmin_client import get_garmin_client

        client = get_garmin_client()
        return {"connected": client.is_authenticated}
    except Exception as e:
        logger.error(f"Failed to check Garmin status: {e}")
        return {"connected": False}


@app.post("/api/garmin/auth/start")
async def start_garmin_auth(credentials: dict):
    """Start Garmin authentication (step 1 - detects if MFA needed).

    Request body:
        - username: Garmin username/email
        - password: Garmin password

    Returns:
        - success: True if authentication complete, False if MFA needed
        - needs_mfa: True if MFA code required
        - session_id: Session ID for submitting MFA code (if needs_mfa=True)
        - error: Error message if login failed
    """
    try:
        from integrations.garmin_client import get_garmin_client

        client = get_garmin_client()
        result = client.start_login(
            username=credentials.get("username"),
            password=credentials.get("password"),
        )

        if result.get("success"):
            return {
                "status": "authenticated",
                "message": "Garmin connected successfully",
                "needs_mfa": False,
            }
        elif result.get("needs_mfa"):
            return {
                "status": "mfa_required",
                "message": "Please enter the one-time passcode sent to your email",
                "needs_mfa": True,
                "session_id": result.get("session_id"),
            }
        else:
            error = result.get("error", "Authentication failed")
            raise HTTPException(status_code=401, detail=error)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Garmin auth start error: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")


@app.post("/api/garmin/auth/mfa")
async def submit_garmin_mfa(mfa_data: dict):
    """Submit MFA code to complete Garmin authentication (step 2).

    Request body:
        - session_id: Session ID from /api/garmin/auth/start
        - mfa_code: One-time passcode from email

    Returns:
        - status: "authenticated" if successful
        - error: Error message if failed
    """
    try:
        from integrations.garmin_client import get_garmin_client

        client = get_garmin_client()
        result = client.submit_mfa_code(
            session_id=mfa_data.get("session_id"),
            mfa_code=mfa_data.get("mfa_code"),
        )

        if result.get("success"):
            return {
                "status": "authenticated",
                "message": "Garmin connected successfully",
            }
        else:
            error = result.get("error", "MFA verification failed")
            raise HTTPException(status_code=401, detail=error)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Garmin MFA error: {e}")
        raise HTTPException(status_code=500, detail=f"MFA verification error: {str(e)}")


@app.post("/api/garmin/auth")
async def authenticate_garmin(credentials: dict):
    """Authenticate with Garmin Connect (legacy endpoint - redirects to new flow).

    This endpoint is kept for backward compatibility.
    For new implementations, use /api/garmin/auth/start + /api/garmin/auth/mfa
    """
    # If MFA code is provided, try direct submission
    if credentials.get("session_id") and credentials.get("mfa_code"):
        return await submit_garmin_mfa(credentials)

    # Otherwise, start the auth flow
    return await start_garmin_auth(credentials)


@app.get("/api/garmin/health/daily")
async def get_daily_health(date: str | None = None):
    """Get daily health metrics for a specific date."""
    try:
        from database import get_health_daily

        if not date:
            from datetime import date as date_func
            date = date_func.today().isoformat()

        data = get_health_daily(date)
        if data:
            return data
        else:
            raise HTTPException(status_code=404, detail="No health data for this date")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get daily health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/garmin/health/sleep")
async def get_sleep(date: str | None = None):
    """Get sleep data for a specific date."""
    try:
        from database import get_health_sleep

        if not date:
            from datetime import date as date_func
            date = date_func.today().isoformat()

        data = get_health_sleep(date)
        if data:
            return data
        else:
            raise HTTPException(status_code=404, detail="No sleep data for this date")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sleep data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/garmin/activities")
async def get_activities(limit: int = 10):
    """Get recent workout activities."""
    try:
        from database import get_health_activities

        activities = get_health_activities(limit)
        return {"activities": activities}
    except Exception as e:
        logger.error(f"Failed to get activities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/garmin/sync")
async def trigger_garmin_sync(background_tasks: BackgroundTasks):
    """Trigger Garmin health data sync from background."""
    async def run_garmin_sync():
        """Sync Garmin data in background."""
        try:
            from integrations.garmin_client import get_garmin_client
            from database import (
                store_health_daily,
                store_health_sleep,
                store_health_activity,
                update_garmin_sync_state,
            )
            from datetime import date, datetime

            client = get_garmin_client()
            if not client.ensure_authenticated():
                logger.error("Garmin not authenticated, skipping sync")
                return

            # Sync today's stats
            stats = client.get_todays_stats()
            if stats:
                store_health_daily(stats)

            # Sync sleep data (last night)
            sleep = client.get_sleep_data()
            if sleep:
                store_health_sleep(sleep)

            # Sync recent activities
            activities = client.get_activities(limit=20)
            for activity in activities:
                store_health_activity(activity)

            # Update sync state
            update_garmin_sync_state(
                last_sync_at=datetime.now().isoformat(),
                last_activity_sync_at=datetime.now().isoformat(),
            )

            logger.info("Garmin sync completed successfully")

        except Exception as e:
            logger.error(f"Garmin sync failed: {e}")

    background_tasks.add_task(run_garmin_sync)

    return {
        "status": "sync_started",
        "message": "Garmin data sync started in background",
    }


@app.delete("/api/garmin/auth")
async def disconnect_garmin():
    """Disconnect Garmin Connect and clear credentials."""
    try:
        from integrations.garmin_client import get_garmin_client

        client = get_garmin_client()
        client.disconnect()

        return {"status": "disconnected", "message": "Garmin disconnected successfully"}
    except Exception as e:
        logger.error(f"Garmin disconnect error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect Garmin")


# ========== Sync Functions ==========


async def run_email_sync(reason: str = "Scheduled sync"):
    """
    Run email synchronization task.

    In production, this would connect to Gmail/Outlook APIs,
    download new emails, classify them, and store in database.
    """
    logger.info(f"Email sync started: {reason}")

    # TODO: Implement actual email sync
    # For now, just update sync timestamp in chats table
    from database import get_connection

    with get_connection() as conn:
        # Get most recent chat to update
        cursor = conn.execute("SELECT id FROM chats ORDER BY updated_at DESC LIMIT 1")
        chat_row = cursor.fetchone()

        if chat_row:
            chat_id = chat_row["id"]
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE chats SET last_email_sync = ? WHERE id = ?",
                (now, chat_id),
            )
            conn.commit()
            logger.info(f"Email sync completed. Updated chat {chat_id} with timestamp {now}")

    logger.info("Email sync completed")


async def run_calendar_sync(reason: str = "Scheduled sync"):
    """
    Run calendar synchronization task.

    In production, this would connect to Google Calendar API,
    download events, and sync with proposals.
    """
    logger.info(f"Calendar sync started: {reason}")

    # TODO: Implement actual calendar sync
    # For now, just update sync timestamp in chats table
    from database import get_connection

    with get_connection() as conn:
        # Get most recent chat to update
        cursor = conn.execute("SELECT id FROM chats ORDER BY updated_at DESC LIMIT 1")
        chat_row = cursor.fetchone()

        if chat_row:
            chat_id = chat_row["id"]
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE chats SET last_calendar_sync = ? WHERE id = ?",
                (now, chat_id),
            )
            conn.commit()
            logger.info(f"Calendar sync completed. Updated chat {chat_id} with timestamp {now}")

    logger.info("Calendar sync completed")


# ========== Chat Streaming Endpoint ==========


@app.post("/api/chat")
async def chat_endpoint(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    _auth: None = Depends(verify_api_key),
):
    """
    Chat endpoint with SSE streaming.
    Phase 3: Uses 3-tier memory with background summarization.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    user_id = request.user_id or config.user_id
    chat_id = request.chat_id

    return StreamingResponse(
        stream_response(request.messages, user_id, chat_id, background_tasks),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-vercel-ai-ui-message-stream": "v1",
        },
    )


# ========== Admin Endpoints (Phase 4) ==========


class BackupCreate(BaseModel):
    description: Optional[str] = ""


class RestoreRequest(BaseModel):
    confirm: bool = False


@app.get("/api/admin/env")
async def get_environment(_auth: None = Depends(verify_admin_api_key)):
    """Get current environment info."""
    return {
        "env_mode": config.env_mode,
        "is_production": config.is_production,
        "data_dir": str(config.data_dir),
        "qdrant_collection": config.qdrant_collection,
        "backup_interval_hours": config.backup_interval_hours,
        "backup_retention_count": config.backup_retention_count,
    }


@app.get("/api/admin/backups")
async def list_backups_endpoint(_auth: None = Depends(verify_admin_api_key)):
    """List all available backups."""
    backups = list_backups()
    return [
        {
            "id": b.id,
            "timestamp": b.timestamp,
            "env_mode": b.env_mode,
            "chat_count": b.chat_count,
            "message_count": b.message_count,
            "memory_count": b.memory_count,
        }
        for b in backups
    ]


@app.post("/api/admin/backup")
async def create_backup_endpoint(
    data: BackupCreate, _auth: None = Depends(verify_admin_api_key)
):
    """Create a new backup."""
    backup = create_backup(data.description or "")
    if not backup:
        raise HTTPException(status_code=500, detail="Backup failed")
    return {
        "success": True,
        "backup_id": backup.id,
        "chat_count": backup.chat_count,
        "message_count": backup.message_count,
        "memory_count": backup.memory_count,
    }


@app.post("/api/admin/restore/{backup_id}")
async def restore_backup_endpoint(
    backup_id: str, data: RestoreRequest, _auth: None = Depends(verify_admin_api_key)
):
    """Restore from a specific backup."""
    # Require confirmation for production
    if config.is_production and not data.confirm:
        raise HTTPException(
            status_code=400, detail="Production restore requires confirm=true"
        )

    success = restore_backup(backup_id)
    if not success:
        raise HTTPException(status_code=500, detail="Restore failed")
    return {"success": True, "restored_from": backup_id}


@app.post("/api/admin/rollback")
async def rollback_endpoint(
    data: RestoreRequest, _auth: None = Depends(verify_admin_api_key)
):
    """Rollback to the most recent backup."""
    # Require confirmation for production
    if config.is_production and not data.confirm:
        raise HTTPException(
            status_code=400, detail="Production rollback requires confirm=true"
        )

    success = rollback_latest()
    if not success:
        raise HTTPException(status_code=500, detail="Rollback failed")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn

    config.validate()
    logger.info("Starting MeGPT Pro API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
