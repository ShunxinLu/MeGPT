"""
Summary Tool - Background summarization for Phase 3 rolling memory.
Generates concise summaries of conversations to maintain context without token explosion.
"""

import httpx
from utils.llm_factory import get_llm_config
from config import config
import database as db
import sqlite3
from exceptions import DatabaseError, LLMError, ExternalServiceError, wrap_exception


def _normalize_base_url(base_url: str) -> str:
    """
    Normalize base URL by stripping trailing /v1 suffix.

    ChatOpenAI and other clients add /v1 automatically, so we need to
    remove it from the base URL to avoid duplication like:
    http://localhost:1234/v1/v1/chat/completions
    """
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    return base_url


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
        recent_history = db.get_recent_messages_text(chat_id, limit=config.context.summary_recent_limit)

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
        # Get current LLM config from database (not env vars)
        llm_base_url, llm_api_key, llm_model = get_llm_config()

        response = httpx.post(
            f"{llm_base_url}/chat/completions",
            json={
                "model": llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,  # Lower temp for consistent summaries
            },
            headers={"Authorization": f"Bearer {llm_api_key}"},
            timeout=60,
        )
        response.raise_for_status()

        data = response.json()
        new_summary = data["choices"][0]["message"]["content"].strip()

        # 4. Save updated summary
        db.update_summary(chat_id, new_summary)
        print(f"✓ Background summary updated for chat {chat_id[:8]}...")

    except sqlite3.Error as e:
        wrapped = wrap_exception(e, DatabaseError, operation="background_summarization")
        print(f"[WARN] Background summarization failed (database): {wrapped}")
    except httpx.TimeoutException as e:
        wrapped = wrap_exception(e, LLMError, operation="background_summarization")
        print(f"[WARN] Background summarization failed (timeout): {wrapped}")
    except httpx.HTTPStatusError as e:
        wrapped = wrap_exception(e, LLMError, operation="background_summarization")
        print(f"[WARN] Background summarization failed (HTTP error): {wrapped}")
    except httpx.RequestError as e:
        wrapped = wrap_exception(e, LLMError, operation="background_summarization")
        print(f"[WARN] Background summarization failed (request error): {wrapped}")
    except Exception as e:
        wrapped = wrap_exception(
            e, ExternalServiceError, operation="background_summarization"
        )
        print(f"[WARN] Background summarization failed: {wrapped}")


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

    # Tier 1: Recent Messages
    recent_messages = db.get_messages(chat_id, limit=config.context.summary_context_limit) if chat_id else []

    return {
        "summary": summary,
        "facts": facts,
        "recent_messages": recent_messages,
    }
