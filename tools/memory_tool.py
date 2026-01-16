"""
Memory Tool - Direct Qdrant integration for persistent long-term memory.
Uses local embeddings via LM Studio's embedding endpoint.
Phase 4: Environment-aware collection names.
"""
import uuid
import json
from datetime import datetime
from typing import Optional
import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    VectorParams, Distance, PointStruct, 
    Filter, FieldCondition, MatchValue
)

from config import config

# Constants - Phase 4: Use config for environment-aware collection
EMBEDDING_DIM = 768  # nomic-embed-text dimension

# Lazy initialization
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> Optional[QdrantClient]:
    """Get or create the Qdrant client (singleton pattern)."""
    global _qdrant_client
    if _qdrant_client is None:
        try:
            _qdrant_client = QdrantClient(
                host=config.qdrant_host,
                port=config.qdrant_port,
            )
            # Ensure collection exists
            _ensure_collection()
            print("✓ Qdrant memory store initialized")
        except Exception as e:
            print(f"⚠ Qdrant initialization failed: {e}")
            return None
    return _qdrant_client


def _ensure_collection():
    """Create the collection if it doesn't exist."""
    client = _qdrant_client
    if client is None:
        return
    
    try:
        collections = client.get_collections().collections
        exists = any(c.name == config.qdrant_collection for c in collections)
        
        if not exists:
            client.create_collection(
                collection_name=config.qdrant_collection,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            print(f"✓ Created collection: {config.qdrant_collection}")
    except Exception as e:
        print(f"⚠ Collection check/create failed: {e}")


def _get_embedding(text: str) -> Optional[list[float]]:
    """Get embedding from local LM Studio embedding endpoint."""
    try:
        response = httpx.post(
            f"{config.embedder_base_url}/embeddings",
            json={
                "model": config.embedder_model_name,
                "input": text,
            },
            headers={"Authorization": f"Bearer {config.embedder_api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"⚠ Embedding failed: {e}")
        return None


def retrieve_context(query: str, user_id: str | None = None) -> str:
    """
    Search memory for relevant context based on the query.
    
    Args:
        query: The user's current message/question
        user_id: Optional user identifier for personalized memory
    
    Returns:
        Formatted string of relevant memories, or empty if none found
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()
    
    if client is None:
        print("⚠ Memory client not available, skipping recall")
        return ""
    
    try:
        print(f"🔍 Searching memories for user {user_id}...")
        
        # Get query embedding
        query_embedding = _get_embedding(query)
        if query_embedding is None:
            return ""
        
        # Search in Qdrant using query_points (newer API)
        from qdrant_client.http.models import QueryRequest
        results = client.query_points(
            collection_name=config.qdrant_collection,
            query=query_embedding,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            limit=5,
            with_payload=True,
        )
        
        if not results or not results.points:
            print("  No memories found")
            return ""
        
        # Format memories as context
        memories = []
        for hit in results.points:
            if hit.score and hit.score > 0.5:  # Only include relevant memories
                memories.append(f"- {hit.payload.get('memory', '')}")
        
        if memories:
            print(f"  Found {len(memories)} memories")
            return "Here is what you remember about this user:\n" + "\n".join(memories)
        
        print("  No relevant memories found")
        return ""
    except Exception as e:
        print(f"⚠ Memory search failed: {e}")
        return ""


def save_interaction(
    user_input: str, 
    ai_response: str, 
    user_id: str | None = None, 
    chat_id: str | None = None
) -> None:
    """
    Save the interaction to memory for future recall.
    
    Args:
        user_input: The user's message
        ai_response: The AI's response
        user_id: Optional user identifier
        chat_id: Optional chat ID for cascading delete
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()
    
    if client is None:
        print("⚠ Memory client not available, skipping save")
        return
    
    try:
        # Create memory text (we save the key user info)
        memory_text = f"User said: {user_input}\nAssistant responded: {ai_response}"
        
        # Get embedding
        embedding = _get_embedding(memory_text)
        if embedding is None:
            return
        
        # Create point
        point_id = str(uuid.uuid4())
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "user_id": user_id,
                "chat_id": chat_id,
                "memory": memory_text,
                "user_input": user_input,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        
        print(f"💾 Saving memory for user {user_id}...")
        client.upsert(collection_name=config.qdrant_collection, points=[point])
        print(f"✓ Memory saved: {point_id}")
        
    except Exception as e:
        print(f"⚠ Memory save failed: {e}")


def add_memory(fact: str, user_id: str | None = None) -> None:
    """
    Add a specific fact to memory.
    
    Args:
        fact: The fact to remember
        user_id: Optional user identifier
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()
    
    if client is None:
        return
    
    try:
        embedding = _get_embedding(fact)
        if embedding is None:
            return
        
        point_id = str(uuid.uuid4())
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "user_id": user_id,
                "memory": fact,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        
        client.upsert(collection_name=config.qdrant_collection, points=[point])
        print(f"✓ Added memory: {fact[:50]}...")
    except Exception as e:
        print(f"⚠ Memory add failed: {e}")


def get_all_memories(user_id: str | None = None) -> list[dict]:
    """
    Get all stored memories for a user.
    
    Args:
        user_id: Optional user identifier
    
    Returns:
        List of memory dictionaries
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()
    
    if client is None:
        return []
    
    try:
        # Scroll through all points for this user
        results, _ = client.scroll(
            collection_name=config.qdrant_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            limit=100,
            with_payload=True,
        )
        
        memories = []
        for point in results:
            memories.append({
                "id": str(point.id),
                "memory": point.payload.get("memory", ""),
                "created_at": point.payload.get("created_at"),
                "metadata": {
                    "chat_id": point.payload.get("chat_id"),
                    "user_input": point.payload.get("user_input"),
                }
            })
        
        return memories
    except Exception as e:
        print(f"⚠ Memory get_all failed: {e}")
        return []


def delete_memory(memory_id: str) -> bool:
    """
    Delete a specific memory by ID.
    
    Args:
        memory_id: The memory ID to delete
    
    Returns:
        True if deleted successfully
    """
    client = get_qdrant_client()
    
    if client is None:
        return False
    
    try:
        client.delete(
            collection_name=config.qdrant_collection,
            points_selector=[memory_id],
        )
        return True
    except Exception as e:
        print(f"⚠ Memory delete failed: {e}")
        return False


def delete_memories_for_chat(chat_id: str, user_id: str | None = None) -> int:
    """
    Delete all memories associated with a specific chat.
    
    Args:
        chat_id: The chat ID whose memories should be deleted
        user_id: Optional user identifier
    
    Returns:
        Number of memories deleted
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()
    
    if client is None:
        return 0
    
    try:
        # Get all memories for this chat
        results, _ = client.scroll(
            collection_name=config.qdrant_collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="chat_id", match=MatchValue(value=chat_id)),
                ]
            ),
            limit=100,
            with_payload=False,
        )
        
        if not results:
            return 0
        
        # Delete all matching points
        point_ids = [str(point.id) for point in results]
        client.delete(
            collection_name=config.qdrant_collection,
            points_selector=point_ids,
        )
        
        return len(point_ids)
    except Exception as e:
        print(f"⚠ Cascading memory delete failed: {e}")
        return 0
