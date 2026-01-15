"""
FastAPI Backend Server - SSE streaming for the Next.js frontend.
Exposes the LangGraph agent via REST API.
"""
import json
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

from config import config
from tools.memory_tool import retrieve_context, save_interaction
from utils.llm_factory import get_llm
from tools.web_search import web_search
from utils.model_loader import ensure_models_loaded

app = FastAPI(
    title="Local Memory Agent API",
    description="Privacy-first AI assistant with persistent memory",
    version="1.0.0"
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


class Message(BaseModel):
    """Chat message schema."""
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    """Chat endpoint request schema."""
    messages: list[Message]
    user_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    llm_url: str
    qdrant_host: str


# System prompt
SYSTEM_PROMPT = """You are a helpful, intelligent AI assistant with access to long-term memory and web search capabilities.

{memory_context}

Guidelines:
- Be conversational and helpful
- Use web search when you need current information
- Remember important facts about the user
- Format code blocks with proper syntax highlighting using ```language
- Be concise but thorough"""


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


async def stream_response(messages: list[Message], user_id: str):
    """
    Stream the LLM response as plain text.
    Compatible with Vercel AI SDK's useChat hook.
    """
    # Get the last user message for context retrieval
    user_messages = [m for m in messages if m.role == "user"]
    last_user_input = user_messages[-1].content if user_messages else ""
    
    # Retrieve memory context
    try:
        context = retrieve_context(last_user_input, user_id)
    except Exception:
        context = ""
    memory_section = context if context else "No prior memories about this user."
    system_content = SYSTEM_PROMPT.format(memory_context=memory_section)
    
    # Convert messages and add system prompt
    langchain_messages = [SystemMessage(content=system_content)] + convert_messages(messages)
    
    # Get streaming LLM
    llm = get_llm(streaming=True)
    
    full_response = ""
    
    try:
        async for chunk in llm.astream(langchain_messages):
            if hasattr(chunk, "content") and chunk.content:
                content = chunk.content
                full_response += content
                # Stream as plain text - Vercel AI SDK format
                yield content
        
        # Save to memory after completion
        if full_response and last_user_input:
            try:
                save_interaction(last_user_input, full_response, user_id)
            except Exception:
                pass
        
    except Exception as e:
        yield f"\n\n[Error: {str(e)}]"


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        llm_url=config.llm_base_url,
        qdrant_host=f"{config.qdrant_host}:{config.qdrant_port}"
    )


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint with SSE streaming.
    Accepts messages and streams response token-by-token.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    user_id = request.user_id or config.user_id
    
    return StreamingResponse(
        stream_response(request.messages, user_id),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn
    config.validate()
    print("🚀 Starting Local Memory Agent API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
