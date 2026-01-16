"""
Summary Tool - Background summarization for Phase 3 rolling memory.
Generates concise summaries of conversations to maintain context without token explosion.
"""
import httpx
from config import config
import database as db


def summarize_chat_background(chat_id: str) -> None:
    """
    Reads recent messages and the current summary, then generates a new 
    condensed summary. Updates the 'chats' table in SQLite.
    
    This should be called as a background task to avoid blocking the chat response.
    
    Args:
        chat_id: The chat ID to summarize
    """
    try:
        # 1. Fetch current data
        current_summary = db.get_summary(chat_id)
        recent_history = db.get_recent_messages_text(chat_id, limit=20)
        
        if not recent_history:
            return  # No messages to summarize
        
        # 2. Build prompt with strict token budget
        prompt = f"""You are a Memory Manager. Update the conversation summary based on new messages.

[OLD SUMMARY]:
{current_summary if current_summary else "No previous summary."}

[NEW MESSAGES]:
{recent_history}

Instructions:
- Output a concise paragraph (max 150 words) capturing the key context
- Include important facts, preferences, and ongoing topics
- Do NOT output a conversational response
- Just output the summary text, nothing else"""

        # 3. Generate summary using local LLM
        response = httpx.post(
            f"{config.llm_base_url}/chat/completions",
            json={
                "model": config.llm_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,  # Lower temp for consistent summaries
            },
            headers={"Authorization": f"Bearer {config.llm_api_key}"},
            timeout=60.0,
        )
        response.raise_for_status()
        
        data = response.json()
        new_summary = data["choices"][0]["message"]["content"].strip()
        
        # 4. Save updated summary
        db.update_summary(chat_id, new_summary)
        print(f"✓ Background summary updated for chat {chat_id[:8]}...")
        
    except Exception as e:
        print(f"⚠ Background summarization failed: {e}")


def get_context_for_prompt(chat_id: str, user_id: str, query: str) -> dict:
    """
    Build the 3-tier context for the LLM prompt.
    
    Returns:
        dict with keys: summary, facts, recent_messages
    """
    from tools.memory_tool import retrieve_context
    
    # Tier 3: Rolling Summary
    summary = db.get_summary(chat_id) if chat_id else ""
    
    # Tier 2: Semantic Facts from Vector DB
    facts = retrieve_context(query, user_id)
    
    # Tier 1: Recent Messages (last 10)
    recent_messages = db.get_messages(chat_id, limit=10) if chat_id else []
    
    return {
        "summary": summary,
        "facts": facts,
        "recent_messages": recent_messages,
    }
