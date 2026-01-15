"""
FastAPI Backend Server - SSE streaming with Vercel AI Data Stream Protocol.
Exposes the LangGraph agent via REST API with chat persistence and memory management.
"""
import json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import config
from database import (
    create_chat, get_chats, get_chat, update_chat_title, delete_chat,
    add_message, get_messages, search_chats
)
from tools.memory_tool import (
    retrieve_context, save_interaction, get_all_memories, 
    delete_memory, delete_memories_for_chat
)
from utils.llm_factory import get_llm
from utils.model_loader import ensure_models_loaded
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

app = FastAPI(
    title="MeGPT Pro API",
    description="Privacy-first AI assistant with persistent memory",
    version="2.0.0"
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


# ========== System Prompt ==========

SYSTEM_PROMPT = """You are MeGPT, a helpful AI assistant with persistent long-term memory and web search capabilities.

{memory_context}

Important facts about yourself:
- You DO have long-term memory that persists across conversations
- You remember important facts about the user
- You can learn new information and recall it later
- You can search the web when you need current information

Guidelines:
- Be conversational and helpful
- When asked about your memory, confirm that you DO remember things
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


async def stream_response(messages: list[Message], user_id: str, chat_id: Optional[str] = None):
    """
    Stream the LLM response with tool status events.
    Uses Vercel AI Data Stream Protocol for transparency.
    """
    # Get the last user message
    user_messages = [m for m in messages if m.role == "user"]
    last_user_input = user_messages[-1].content if user_messages else ""
    
    # Stream: Memory recall status
    yield format_event("status", "🧠 Recalling memories...")
    
    # Retrieve memory context
    try:
        context = retrieve_context(last_user_input, user_id)
    except Exception:
        context = ""
    
    memory_section = context if context else "No prior memories about this user yet."
    system_content = SYSTEM_PROMPT.format(memory_context=memory_section)
    
    # Convert messages and add system prompt
    langchain_messages = [SystemMessage(content=system_content)] + convert_messages(messages)
    
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
    """Delete a chat with cascading memory deletion."""
    uid = user_id or config.user_id
    
    # Delete related memories first
    deleted_memories = delete_memories_for_chat(chat_id, uid)
    
    # Delete the chat (cascades to messages)
    delete_chat(chat_id)
    
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
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint with SSE streaming.
    Uses Vercel AI Data Stream Protocol for tool transparency.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    user_id = request.user_id or config.user_id
    chat_id = request.chat_id
    
    return StreamingResponse(
        stream_response(request.messages, user_id, chat_id),
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
