"""
FastAPI Backend Server - SSE streaming with Vercel AI Data Stream Protocol.
Phase 3: 3-Tier Memory Architecture with Background Summarization.
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
    add_message, get_messages, search_chats, get_summary, get_message_count
)
from tools.memory_tool import (
    retrieve_context, save_interaction, get_all_memories, 
    delete_memory, delete_memories_for_chat
)
from tools.summary_tool import summarize_chat_background
from utils.llm_factory import get_llm
from utils.model_loader import ensure_models_loaded
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

app = FastAPI(
    title="MeGPT Pro API",
    description="Privacy-first AI assistant with persistent memory",
    version="3.0.0"
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


# ========== Phase 3: System Prompt with 3-Tier Context ==========

SYSTEM_PROMPT = """You are MeGPT, a helpful AI assistant with persistent long-term memory and web search capabilities.

[LONG-TERM MEMORY - What you know about the user]
{memory_facts}

[CURRENT CONVERSATION SUMMARY]
{conversation_summary}

Important facts about yourself:
- You DO have long-term memory that persists across conversations
- You remember important facts about the user
- You can learn new information and recall it later
- You can search the web when you need current information

Guidelines:
- Be conversational and helpful
- When asked about your memory, confirm that you DO remember things
- Use the information from your memory to personalize responses
- Format code blocks with proper syntax highlighting using ```language
- Be concise but thorough"""


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
    Stream the LLM response with 3-tier context.
    Phase 3: Combines Tier 1 (Recent), Tier 2 (Facts), Tier 3 (Summary).
    """
    # Get the last user message
    user_messages = [m for m in messages if m.role == "user"]
    last_user_input = user_messages[-1].content if user_messages else ""
    
    # ========== TIER 2: Semantic Facts from Vector DB ==========
    yield format_event("status", "🧠 Recalling memories...")
    
    try:
        memory_facts = retrieve_context(last_user_input, user_id)
    except Exception:
        memory_facts = ""
    
    facts_section = memory_facts if memory_facts else "No prior memories about this user yet."
    
    # ========== TIER 3: Rolling Conversation Summary ==========
    conversation_summary = ""
    if chat_id:
        try:
            conversation_summary = get_summary(chat_id)
        except Exception:
            pass
    
    summary_section = conversation_summary if conversation_summary else "No summary yet for this conversation."
    
    # Build system prompt with 3-tier context
    system_content = SYSTEM_PROMPT.format(
        memory_facts=facts_section,
        conversation_summary=summary_section
    )
    
    # ========== TIER 1: Recent Messages (already in messages list) ==========
    # Note: Frontend sends only recent messages, but we limit to last 10 for safety
    recent_messages = messages[-10:] if len(messages) > 10 else messages
    
    # Convert messages and add system prompt
    langchain_messages = [SystemMessage(content=system_content)] + convert_messages(recent_messages)
    
    # Stream: Generating status
    yield format_event("status", "💭 Thinking...")
    
    # Get streaming LLM
    llm = get_llm(streaming=True)
    full_response = ""
    
    try:
        async for chunk in llm.astream(langchain_messages):
            if hasattr(chunk, "content") and chunk.content:
                content = chunk.content
                full_response += content
                yield format_event("text", content)
        
        # Save to memory after completion
        if full_response and last_user_input:
            try:
                save_interaction(last_user_input, full_response, user_id, chat_id)
            except Exception:
                pass
        
        # ========== PHASE 3: Trigger Background Summary ==========
        # Every 5th message, update the rolling summary
        if chat_id and background_tasks:
            try:
                msg_count = get_message_count(chat_id)
                if msg_count > 0 and msg_count % 5 == 0:
                    background_tasks.add_task(summarize_chat_background, chat_id)
                    print(f"📝 Scheduled background summary for chat {chat_id[:8]}...")
            except Exception:
                pass
        
    except Exception as e:
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


if __name__ == "__main__":
    import uvicorn
    config.validate()
    print("🚀 Starting MeGPT Pro API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
