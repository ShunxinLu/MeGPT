"""
Memory Tool - Mem0 integration for persistent long-term memory.
Uses local embeddings to maintain privacy.
"""
from mem0 import Memory
from config import config

# Mem0 configuration with explicit local embedder
# CRITICAL: This ensures embeddings don't call OpenAI cloud
_mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": config.qdrant_host,
            "port": config.qdrant_port,
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": config.llm_model_name,
            "openai_base_url": config.llm_base_url,
            "openai_api_key": config.llm_api_key,
        }
    },
    # CRITICAL: Define embedder explicitly to avoid default OpenAI calls
    "embedder": {
        "provider": "openai",
        "config": {
            "model": config.embedder_model_name,
            "openai_base_url": config.embedder_base_url,
            "openai_api_key": config.embedder_api_key,
        }
    }
}

# Lazy initialization of memory client
_memory_client: Memory | None = None


def get_memory_client() -> Memory | None:
    """Get or create the Mem0 memory client (singleton pattern)."""
    global _memory_client
    if _memory_client is None:
        try:
            _memory_client = Memory.from_config(_mem0_config)
            print("✓ Mem0 initialized with local embeddings")
        except Exception as e:
            print(f"⚠ Mem0 initialization failed: {e}")
            return None
    return _memory_client


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
    memory = get_memory_client()
    
    try:
        results = memory.search(query, user_id=user_id, limit=5)
        
        if not results or not results.get("results"):
            return ""
        
        # Format memories as context
        memories = []
        for item in results["results"]:
            if "memory" in item:
                memories.append(f"- {item['memory']}")
        
        if memories:
            return "Here is what you remember about this user:\n" + "\n".join(memories)
        return ""
    except Exception as e:
        print(f"⚠ Memory search failed: {e}")
        return ""


def save_interaction(user_input: str, ai_response: str, user_id: str | None = None, chat_id: str | None = None) -> None:
    """
    Save the interaction to memory for future recall.
    Combines user input and AI response for context.
    
    Args:
        user_input: The user's message
        ai_response: The AI's response
        user_id: Optional user identifier
        chat_id: Optional chat ID for cascading delete
    """
    user_id = user_id or config.user_id
    memory = get_memory_client()
    
    try:
        # Save the interaction as a memory with chat_id metadata
        interaction = f"User said: {user_input}\nAssistant responded: {ai_response}"
        metadata = {"chat_id": chat_id} if chat_id else {}
        memory.add(interaction, user_id=user_id, metadata=metadata)
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
    memory = get_memory_client()
    
    try:
        memory.add(fact, user_id=user_id)
    except Exception as e:
        print(f"⚠ Memory add failed: {e}")


def get_all_memories(user_id: str | None = None) -> list[dict]:
    """
    Get all stored memories for a user.
    
    Args:
        user_id: Optional user identifier
    
    Returns:
        List of memory dictionaries with id, memory, created_at
    """
    user_id = user_id or config.user_id
    memory = get_memory_client()
    
    if memory is None:
        return []
    
    try:
        results = memory.get_all(user_id=user_id)
        return results.get("results", []) if results else []
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
    memory = get_memory_client()
    
    try:
        memory.delete(memory_id)
        return True
    except Exception as e:
        print(f"⚠ Memory delete failed: {e}")
        return False


def delete_memories_for_chat(chat_id: str, user_id: str | None = None) -> int:
    """
    Delete all memories associated with a specific chat.
    Uses metadata filtering if available, otherwise searches and deletes.
    
    Args:
        chat_id: The chat ID whose memories should be deleted
        user_id: Optional user identifier
    
    Returns:
        Number of memories deleted
    """
    user_id = user_id or config.user_id
    memory = get_memory_client()
    deleted_count = 0
    
    try:
        # Get all memories and filter by chat_id in metadata
        all_memories = memory.get_all(user_id=user_id)
        if not all_memories or not all_memories.get("results"):
            return 0
        
        for mem in all_memories["results"]:
            metadata = mem.get("metadata", {})
            if metadata.get("chat_id") == chat_id:
                try:
                    memory.delete(mem["id"])
                    deleted_count += 1
                except Exception:
                    pass
        
        return deleted_count
    except Exception as e:
        print(f"⚠ Cascading memory delete failed: {e}")
        return deleted_count

