"""
FastAPI Backend Server - SSE streaming with Vercel AI Data Stream Protocol.
Brain Transplant: Routes through agent_graph.py for proper tool execution.
"""
import json
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import config
from database import (
    create_chat, get_chats, get_chat, update_chat_title, delete_chat,
    add_message, get_messages, search_chats, get_message_count
)
from tools.memory_tool import get_all_memories, delete_memory, delete_memories_for_chat
from tools.summary_tool import summarize_chat_background
from tools.backup_tool import (
    create_backup, list_backups, restore_backup, rollback_latest, get_backup_info
)
from utils.model_loader import ensure_models_loaded
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

app = FastAPI(
    title="MeGPT Pro API",
    description="Privacy-first AI assistant with persistent memory",
    version="4.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Load models on server startup."""
    print("🔄 Loading models in LM Studio...")
    success = await ensure_models_loaded()
    if success:
        print("✓ Models ready!")
    else:
        print("⚠ Models may not be loaded - check LM Studio")


# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== Pydantic Models ==========

class Message(BaseModel):
    role: str
    content: str


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


# ========== NOTE: SYSTEM_PROMPT is now in agent_graph.py ==========
# The Agent Graph manages all context and tool execution.


# ========== Helpers ==========

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
    return f'0:{json.dumps({"type": event_type, "content": content})}\n'


async def stream_response(
    messages: list[Message], 
    user_id: str, 
    chat_id: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None
):
    """
    Stream the LLM response through the Agent Graph.
    Brain Transplant: Routes through agent_graph.py for proper tool execution.
    """
    from agent_graph import agent
    from langchain_core.messages import HumanMessage
    
    # Get the last user message
    user_messages = [m for m in messages if m.role == "user"]
    last_user_input = user_messages[-1].content if user_messages else ""
    
    # Status: Starting
    yield format_event("status", "🧠 Recalling memories...")
    
    # ========== CONTEXT TRUNCATION (Prevent 4k overflow) ==========
    # STRATEGY: Rely on Tier 3 (Summary) for older context, pass minimal raw history
    # With long responses (Italy itinerary = 700+ tokens each), even 8 messages overflow
    # The summary contains the full conversation context in ~200 tokens
    MAX_HISTORY = 3  # Only last 3 messages - summary covers the rest
    
    # Exclude the very last message (current input) to process it separately
    recent_messages = messages[:-1] if len(messages) > 1 else []
    
    # Truncate to last N messages
    if len(recent_messages) > MAX_HISTORY:
        recent_messages = recent_messages[-MAX_HISTORY:]
        print(f"✂️ Truncated history to last {MAX_HISTORY} messages (was {len(messages)-1})")
    
    # Convert to LangChain format
    history = convert_messages(recent_messages) if recent_messages else []
    
    # Add the current user message
    history.append(HumanMessage(content=last_user_input))
    
    full_response = ""
    last_node = ""
    
    try:
        # Stream from LangGraph using astream (yields state updates per node)
        async for state_update in agent.astream(
            input={
                "messages": history,
                "user_input": last_user_input,
                "chat_id": chat_id,
                "user_id": user_id,
                "context": {},
                "final_response": "",
                "tool_call_count": 0
            },
            stream_mode="updates"  # Get updates per node
        ):
            # state_update is a dict with node name as key
            for node_name, node_output in state_update.items():
                print(f"🔄 Node '{node_name}' completed")
                
                # Track status based on node
                if node_name == "recall":
                    yield format_event("status", "🧠 Context loaded...")
                elif node_name == "reason":
                    yield format_event("status", "💭 Thinking...")
                elif node_name == "tools":
                    yield format_event("status", "🔎 Using web_search...")
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
                if msg_count > 0 and msg_count % 5 == 0:
                    background_tasks.add_task(summarize_chat_background, chat_id)
            except Exception:
                pass
        
    except Exception as e:
        print(f"❌ Stream error: {e}")
        import traceback
        traceback.print_exc()
        yield format_event("error", str(e))


# ========== Health Check ==========

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        llm_url=config.llm_base_url,
        qdrant_host=f"{config.qdrant_host}:{config.qdrant_port}"
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
    return search_chats(uid, q)


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
    """
    uid = user_id or config.user_id
    
    print(f"🗑️ Starting cascading delete for chat {chat_id[:8]}...")
    
    # STEP 1: Vector Wipe (Tier 2) - Delete related memories from Qdrant
    deleted_memories = delete_memories_for_chat(chat_id, uid)
    
    # STEP 2: SQL Wipe (Tier 1 & Tier 3) - ON DELETE CASCADE handles messages
    delete_chat(chat_id)
    
    print(f"✓ Chat and {deleted_memories} memories permanently scrubbed")
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


# ========== Chat Streaming Endpoint ==========

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
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
        }
    )


# ========== Admin Endpoints (Phase 4) ==========

class BackupCreate(BaseModel):
    description: Optional[str] = ""


class RestoreRequest(BaseModel):
    confirm: bool = False


@app.get("/api/admin/env")
async def get_environment():
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
async def list_backups_endpoint():
    """List all available backups."""
    backups = list_backups()
    return [{"id": b.id, "timestamp": b.timestamp, "env_mode": b.env_mode,
             "chat_count": b.chat_count, "message_count": b.message_count,
             "memory_count": b.memory_count} for b in backups]


@app.post("/api/admin/backup")
async def create_backup_endpoint(data: BackupCreate):
    """Create a new backup."""
    backup = create_backup(data.description)
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
async def restore_backup_endpoint(backup_id: str, data: RestoreRequest):
    """Restore from a specific backup."""
    # Require confirmation for production
    if config.is_production and not data.confirm:
        raise HTTPException(
            status_code=400, 
            detail="Production restore requires confirm=true"
        )
    
    success = restore_backup(backup_id)
    if not success:
        raise HTTPException(status_code=500, detail="Restore failed")
    return {"success": True, "restored_from": backup_id}


@app.post("/api/admin/rollback")
async def rollback_endpoint(data: RestoreRequest):
    """Rollback to the most recent backup."""
    # Require confirmation for production
    if config.is_production and not data.confirm:
        raise HTTPException(
            status_code=400,
            detail="Production rollback requires confirm=true"
        )
    
    success = rollback_latest()
    if not success:
        raise HTTPException(status_code=500, detail="Rollback failed")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    config.validate()
    print("🚀 Starting MeGPT Pro API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
