"""
Memory Tool - Direct Qdrant integration for persistent long-term memory.
Uses local embeddings via LM Studio's embedding endpoint.
Phase 4: Environment-aware collection names.
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional
import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from langchain_core.tools import tool

from config import config

logger = logging.getLogger(__name__)

# Constants - Phase 4: Use config for environment-aware collection
DEFAULT_EMBEDDING_DIM = 768  # nomic-embed-text dimension
_detected_embedding_dim = None


def _get_embedding_dim() -> int:
    """
    Dynamically detect embedding dimension from the model.
    Returns detected dimension or default if detection fails.
    """
    global _detected_embedding_dim

    if _detected_embedding_dim is not None:
        return _detected_embedding_dim

    try:
        # Try to detect dimension by embedding a test string
        test_embedding = _get_embedding("test")
        if test_embedding:
            _detected_embedding_dim = len(test_embedding)
            logger.info(f"Detected embedding dimension: {_detected_embedding_dim}")
            return _detected_embedding_dim
    except Exception as e:
        logger.warning(f"Could not detect embedding dimension: {e}")

    # Fall back to default
    logger.info(f"Using default embedding dimension: {DEFAULT_EMBEDDING_DIM}")
    return DEFAULT_EMBEDDING_DIM


_qdrant_client: Optional[QdrantClient] = None
_qdrant_last_health_check = 0


def _extract_facts(user_input: str, ai_response: str) -> str:
    """
    Extract important facts from conversation using LLM.
    Returns extracted facts or empty string if extraction fails.
    """
    try:
        response = httpx.post(
            f"{config.llm_base_url}/v1/chat/completions",
            json={
                "model": config.llm_model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Extract the most important fact(s) from this conversation.

USER: {user_input}
ASSISTANT: {ai_response}

Instructions:
- Extract only factual information (preferences, decisions, facts about the user)
- Output as a single concise sentence
- If no important facts, output: NONE
- Examples of good facts: "User prefers dark mode", "User is working on a React project"
- Do NOT extract conversational filler like "thanks", "ok", etc.""",
                    }
                ],
                "max_tokens": 100,
                "temperature": 0.2,
            },
            headers={"Authorization": f"Bearer {config.llm_api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        fact = result["choices"][0]["message"]["content"].strip()

        if fact and fact.upper() != "NONE":
            return fact

        return ""
    except httpx.TimeoutException:
        logger.error("Fact extraction timed out")
        return ""
    except httpx.NetworkError as e:
        logger.error(f"Network error during fact extraction: {e}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error during fact extraction: {e}")
        return ""


def get_qdrant_client() -> Optional[QdrantClient]:
    """
    Get or create the Qdrant client (singleton pattern) with health check.
    """
    global _qdrant_client, _qdrant_last_health_check
    import time  # Import at top level to be available in all branches

    # If client exists, perform health check every 60 seconds
    if _qdrant_client is not None:
        current_time = time.time()
        if current_time - _qdrant_last_health_check > 60:
            try:
                # Quick health check - try to get collections
                _qdrant_client.get_collections()
                _qdrant_last_health_check = current_time
            except Exception as e:
                logger.warning(f"Qdrant client health check failed, recreating: {e}")
                _qdrant_client = None
                # Fall through to recreate

    if _qdrant_client is None:
        try:
            _qdrant_client = QdrantClient(
                host=config.qdrant_host,
                port=config.qdrant_port,
                timeout=30.0,
            )
            # Verify connection by getting collections
            _qdrant_client.get_collections()
            # Ensure collection exists
            _ensure_collection()
            _qdrant_last_health_check = time.time()
            logger.info("Qdrant memory store initialized")
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            _qdrant_client = None
        except Exception as e:
            logger.error(f"Qdrant initialization failed: {e}")
            _qdrant_client = None
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
                    size=_get_embedding_dim(),
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created collection: {config.qdrant_collection} (dim: {_get_embedding_dim()})")
    except Exception as e:
        logger.error(f"Collection check/create failed: {e}")


def _get_embedding(text: str) -> Optional[list[float]]:
    """Get embedding from local LM Studio embedding endpoint with retry."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = httpx.post(
                f"{config.embedder_base_url}/v1/embeddings",
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
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                logger.warning(f"Embedding timeout {attempt + 1}, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Embedding timed out after {max_retries} attempts")
                return None
        except httpx.NetworkError as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Embedding network error {attempt + 1}, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"Embedding network error after {max_retries} attempts: {e}")
                return None
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Embedding attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"Embedding failed after {max_retries} attempts: {e}")
                return None
    return None


def retrieve_context(query: str, user_id: str | None = None) -> str:
    """
    Search memory for relevant context based on the query.

    Now searches BOTH conversation memories AND email facts.

    Args:
        query: The user's current message/question
        user_id: Optional user identifier for personalized memory

    Returns:
        Formatted string of relevant memories, or empty if none found
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        logger.warning("Memory client not available, skipping recall")
        return ""

    try:
        logger.debug(f"Searching memories for user {user_id}...")

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
            limit=10,  # Increased to include email facts
            with_payload=True,
        )

        if not results or not results.points:
            logger.debug("No memories found")
            return ""

        # Separate conversation facts from email facts
        conversation_facts = []
        email_facts = []

        for hit in results.points:
            if hit.score and hit.score > 0.4:  # Lowered threshold for more results
                mem_type = hit.payload.get("type", "transcript")
                memory = hit.payload.get('memory', '')

                if mem_type == "email_fact":
                    email_facts.append(memory)
                else:
                    conversation_facts.append(f"- {memory}")

        # Format combined results
        parts = []
        if conversation_facts:
            parts.append("Here is what you remember about this user:")
            parts.extend(conversation_facts)

        if email_facts:
            if conversation_facts:
                parts.append("\n\nFrom emails:")
            parts.extend([f"- {fact}" for fact in email_facts])

        if parts:
            logger.debug(f"Found {len(conversation_facts)} conversation facts, {len(email_facts)} email facts")
            return "\n".join(parts)

        logger.debug("No relevant memories found")
        return ""
    except Exception as e:
        logger.error(f"Memory search failed: {e}")
        return ""


def save_interaction(
    user_input: str,
    ai_response: str,
    user_id: str | None = None,
    chat_id: str | None = None,
) -> None:
    """
    Save the interaction to memory for future recall.
    Now extracts facts using the LLM for better recall.

    Args:
        user_input: The user's message
        ai_response: The AI's response
        user_id: Optional user identifier
        chat_id: Optional chat ID for cascading delete
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        logger.warning("Memory client not available, skipping save")
        return

    try:
        # Extract facts using LLM for better memory quality
        fact_text = _extract_facts(user_input, ai_response)

        # Check if extraction succeeded (got a fact, not just transcript)
        is_extracted = bool(fact_text) and not fact_text.startswith("User said:")

        if not fact_text:
            # Fallback to transcript if extraction fails
            fact_text = f"User said: {user_input}\nAssistant responded: {ai_response}"
            is_extracted = False

        # Get embedding
        embedding = _get_embedding(fact_text)
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
                "memory": fact_text,
                "user_input": user_input,
                "type": "extracted_fact" if is_extracted else "transcript",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        logger.debug(f"Saving memory for user {user_id}...")
        client.upsert(collection_name=config.qdrant_collection, points=[point])
        logger.debug(f"Memory saved: {point_id}")

    except Exception as e:
        logger.error(f"Memory save failed: {e}")


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
        logger.warning("Memory client not available, skipping add_memory")
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
            },
        )

        client.upsert(collection_name=config.qdrant_collection, points=[point])
        logger.debug(f"Added memory: {fact[:50]}...")
    except Exception as e:
        logger.error(f"Memory add failed: {e}")


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
            memories.append(
                {
                    "id": str(point.id),
                    "memory": point.payload.get("memory", ""),
                    "created_at": point.payload.get("created_at"),
                    "metadata": {
                        "chat_id": point.payload.get("chat_id"),
                        "user_input": point.payload.get("user_input"),
                    },
                }
            )

        return memories
    except Exception as e:
        logger.error(f"Memory get_all failed: {e}")
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
        logger.error(f"Memory delete failed: {e}")
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
        logger.error(f"Cascading memory delete failed: {e}")
        return 0


# ========== Email Ingestion to Knowledge Base ==========


def _extract_facts_from_email(email_data: dict) -> list[str]:
    """
    Extract important facts from an email using the LLM.

    Extracts: action items, deadlines, commitments, decisions, contacts, preferences

    Args:
        email_data: Dictionary with email fields (subject, sender, body, date_received, etc.)

    Returns:
        List of extracted facts as strings
    """
    try:
        # Build email context for fact extraction
        email_context = f"""
Email Subject: {email_data.get('subject', '')}
From: {email_data.get('sender', '')}
Date: {email_data.get('date_received', '')}

{email_data.get('summary', '')}

Body (first 2000 chars):
{email_data.get('body_markdown', '')[:2000]}
"""

        response = httpx.post(
            f"{config.llm_base_url}/v1/chat/completions",
            json={
                "model": config.llm_model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Extract important facts from this email that would be useful to remember in future conversations.

{email_context}

Extract ONLY facts that are actionable or reference-worthy:
- Action items (tasks to do, deadlines, meetings)
- Commitments made by anyone
- Important decisions made
- Contact information (names, roles, emails)
- Dates and times mentioned
- Preferences or requirements
- Shipping/delivery/tracking information

Output each fact as a separate line starting with "FACT:".
If nothing important to remember, output: "FACT: NONE"

Examples:
- FACT: User needs to reply to John by Friday
- FACT: Meeting scheduled for March 15th at 2pm
- FACT: Shipping address: 123 Main St, City, State 12345
- FACT: Alice (alice@company.com) requested the quarterly report""",
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.2,
            },
            headers={"Authorization": f"Bearer {config.llm_api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Parse out the facts
        facts = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("FACT:"):
                fact = line[5:].strip()
                if fact and fact.upper() != "NONE":
                    facts.append(f"[Email] {fact}")

        return facts

    except Exception as e:
        logger.error(f"Email fact extraction failed: {e}")
        return []


def ingest_email_to_memory(
    email_data: dict,
    user_id: str | None = None,
    chat_id: str | None = None,
) -> dict:
    """
    Ingest an email into the vector knowledge base.

    Extracts facts from the email using the LLM and stores them in Qdrant
    for semantic retrieval in future conversations.

    Args:
        email_data: Dictionary with email fields
            - id: Email ID
            - subject: Email subject
            - sender: Sender name
            - sender_email: Sender email
            - body_markdown: Email body
            - date_received: Date received
            - summary: Optional summary
            - priority: Email priority
        user_id: User identifier
        chat_id: Optional chat ID for cascading delete

    Returns:
        Dictionary with ingestion results:
        - success: bool
        - facts_extracted: int
        - fact_ids: list of stored fact IDs
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        return {
            "success": False,
            "error": "Memory client not available",
            "facts_extracted": 0,
            "fact_ids": [],
        }

    try:
        logger.debug(f"Ingesting email to memory: {email_data.get('subject', 'No subject')[:50]}...")

        # Extract facts from email
        facts = _extract_facts_from_email(email_data)

        if not facts:
            # Store basic email info as a fact
            basic_fact = (
                f"[Email] {email_data.get('sender', 'Unknown')} sent: "
                f"{email_data.get('subject', 'No subject')}. "
                f"Date: {email_data.get('date_received', 'Unknown')}"
            )
            facts = [basic_fact]

        # Store each fact in Qdrant
        fact_ids = []
        for fact in facts:
            try:
                # Create metadata payload
                payload = {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "memory": fact,
                    "type": "email_fact",
                    "email_id": email_data.get("id"),
                    "email_subject": email_data.get("subject"),
                    "email_sender": email_data.get("sender"),
                    "created_at": datetime.utcnow().isoformat(),
                }

                # Get embedding
                embedding = _get_embedding(fact)
                if embedding is None:
                    continue

                # Create point
                point_id = str(uuid.uuid4())
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )

                client.upsert(collection_name=config.qdrant_collection, points=[point])
                fact_ids.append(point_id)

            except Exception as e:
                logger.error(f"Failed to store email fact: {e}")

        logger.debug(f"Email ingested: {len(fact_ids)} facts stored")
        return {
            "success": True,
            "facts_extracted": len(fact_ids),
            "fact_ids": fact_ids,
        }

    except Exception as e:
        logger.error(f"Email ingestion failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "facts_extracted": 0,
            "fact_ids": [],
        }


def ingest_emails_from_db(
    user_id: str | None = None,
    chat_id: str | None = None,
    limit: int = 50,
    priority_filter: list[str] | None = None,
) -> dict:
    """
    Ingest recent emails from the database into the knowledge base.

    Useful for:
    - Initial bulk import of emails
    - Catching up on missed emails
    - Re-ingesting with improved fact extraction

    Args:
        user_id: User identifier
        chat_id: Optional chat ID for grouping memories
        limit: Maximum number of emails to ingest (default: 50)
        priority_filter: Only ingest emails with these priorities (default: ["critical", "important"])

    Returns:
        Dictionary with ingestion results:
        - success: bool
        - emails_processed: int
        - total_facts_extracted: int
    """
    from database import get_connection

    user_id = user_id or config.user_id

    # Default to important emails only
    if priority_filter is None:
        priority_filter = ["critical", "important"]

    try:
        with get_connection() as conn:
            # Build query
            placeholders = ",".join("?" * len(priority_filter))
            query = f"""
                SELECT id, subject, sender, sender_email, body_markdown,
                       date_received, summary, priority
                FROM emails
                WHERE priority IN ({placeholders})
                ORDER BY date_received DESC
                LIMIT ?
            """
            params = priority_filter + [limit]

            cursor = conn.execute(query, params)
            emails = cursor.fetchall()

        if not emails:
            return {
                "success": True,
                "emails_processed": 0,
                "total_facts_extracted": 0,
                "message": "No emails found to ingest",
            }

        logger.info(f"Ingesting {len(emails)} emails to memory...")

        emails_processed = 0
        total_facts = 0

        for email in emails:
            result = ingest_email_to_memory(
                {
                    "id": email["id"],
                    "subject": email["subject"],
                    "sender": email["sender"],
                    "sender_email": email["sender_email"],
                    "body_markdown": email["body_markdown"],
                    "date_received": email["date_received"],
                    "summary": email["summary"],
                    "priority": email["priority"],
                },
                user_id=user_id,
                chat_id=chat_id,
            )

            if result["success"]:
                emails_processed += 1
                total_facts += result["facts_extracted"]

        return {
            "success": True,
            "emails_processed": emails_processed,
            "total_facts_extracted": total_facts,
            "message": f"Ingested {emails_processed} emails with {total_facts} facts",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "emails_processed": 0,
            "total_facts_extracted": 0,
        }


def search_email_memories(query: str, user_id: str | None = None) -> list[dict]:
    """
    Search the knowledge base for information from emails.

    This uses the vector database to semantically search for facts
    that were extracted from emails.

    Args:
        query: Search query
        user_id: User identifier

    Returns:
        List of matching email facts with metadata
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        return []

    try:
        # Get query embedding
        query_embedding = _get_embedding(query)
        if query_embedding is None:
            return []

        # Search in Qdrant
        from qdrant_client.http.models import QueryRequest, Filter, FieldCondition, MatchValue

        results = client.query_points(
            collection_name=config.qdrant_collection,
            query=query_embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="type", match=MatchValue(value="email_fact")),
                ]
            ),
            limit=10,
            with_payload=True,
        )

        if not results or not results.points:
            return []

        # Format results
        memories = []
        for hit in results:
            if hit.score and hit.score > 0.4:  # Relevance threshold
                memories.append({
                    "id": str(hit.id),
                    "memory": hit.payload.get("memory", ""),
                    "score": hit.score,
                    "metadata": {
                        "email_id": hit.payload.get("email_id"),
                        "email_subject": hit.payload.get("email_subject"),
                        "email_sender": hit.payload.get("email_sender"),
                    },
                })

        return memories

    except Exception as e:
        logger.error(f"Email memory search failed: {e}")
        return []


# ========== LangChain Tools for Agent ==========


@tool
def ingest_emails(limit: int = 20, priority: str = "important") -> str:
    """
    Ingest recent emails into the knowledge base for future reference.

    Extracts facts from emails (action items, deadlines, commitments, contacts)
    and stores them in the vector database for semantic search.

    Useful when:
    - "Remember my recent emails"
    - "Add emails to memory"
    - "Learn from my emails"
    - "What did I get in email recently?"

    Args:
        limit: Number of recent emails to ingest (default: 20)
        priority: Only ingest emails of this priority or higher (critical/important/normal, default: important)

    Returns:
        Summary of ingestion results
    """
    # Map priority to filter
    priority_map = {
        "critical": ["critical"],
        "important": ["critical", "important"],
        "normal": ["critical", "important", "normal"],
        "all": ["critical", "important", "normal", "low"],
    }

    priority_filter = priority_map.get(priority, ["critical", "important"])

    result = ingest_emails_from_db(
        user_id=config.user_id,
        limit=limit,
        priority_filter=priority_filter,
    )

    if result["success"]:
        return (
            f"✓ Successfully ingested {result['emails_processed']} emails "
            f"and extracted {result['total_facts_extracted']} facts. "
            f"{result.get('message', '')}"
        )
    else:
        return f"✗ Email ingestion failed: {result.get('error', 'Unknown error')}"


@tool
def search_email_knowledge(query: str, limit: int = 5) -> str:
    """
    Search the knowledge base for information extracted from emails.

    This searches through facts that were previously extracted from emails,
    including action items, deadlines, commitments, contacts, and decisions.

    Useful for questions like:
    - "What did John ask me to do?"
    - "When is my deadline?"
    - "What commitments did I make?"
    - "What shipping address did I use?"

    Args:
        query: What to search for in email memories
        limit: Maximum results to return (default: 5)

    Returns:
        Formatted results from email knowledge base
    """
    memories = search_email_memories(query, user_id=config.user_id)

    if not memories:
        return f"No relevant information found in email knowledge base for: {query}"

    # Format results
    lines = [f"Found {len(memories)} relevant facts from emails:\n"]
    for mem in memories[:limit]:
        lines.append(f"• {mem['memory']}")
        if mem.get("metadata", {}).get("email_subject"):
            lines.append(f"  (from: {mem['metadata']['email_subject']})")

    return "\n".join(lines)


# Export tools for agent registration
MEMORY_TOOLS = [
    ingest_emails,
    search_email_knowledge,
]


# ========== Document Ingestion to Knowledge Base ==========


def _chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """
    Split text into overlapping chunks for processing.

    Args:
        text: The text to chunk
        chunk_size: Maximum characters per chunk
        overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a sentence boundary
        if end < len(text):
            # Look for sentence endings near the end
            for delimiter in [". ", "! ", "? ", "\n", "  "]:
                last_delim = chunk.rfind(delimiter)
                if last_delim > chunk_size // 2:  # At least half the chunk
                    chunk = chunk[:last_delim + len(delimiter.strip())]
                    break

        chunks.append(chunk.strip())
        start = end - overlap if end < len(text) else len(text)

    return [c for c in chunks if c and len(c.split()) > 10]  # Filter tiny chunks


def _extract_facts_from_document(chunk: str, filename: str) -> list[str]:
    """
    Extract important facts from a document chunk using the LLM.

    Args:
        chunk: A chunk of document text
        filename: Original document filename for context

    Returns:
        List of extracted facts
    """
    try:
        response = httpx.post(
            f"{config.llm_base_url}/v1/chat/completions",
            json={
                "model": config.llm_model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Extract important information from this document chunk.

Document: {filename}

Chunk:
{chunk[:3000]}

Extract ONLY facts that would be useful to remember in future conversations:
- Key concepts, definitions, or explanations
- Important data, statistics, or figures
- Names, dates, places mentioned
- Action items, deadlines, commitments
- Decisions or conclusions
- Contact information, addresses
- Preferences or requirements

Output each fact as a separate line starting with "FACT:".
If nothing important to remember, output: "FACT: NONE"

Keep facts concise but complete.
""",
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.2,
            },
            headers={"Authorization": f"Bearer {config.llm_api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        # Parse out the facts
        facts = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("FACT:"):
                fact = line[5:].strip()
                if fact and fact.upper() != "NONE":
                    facts.append(f"[Document: {filename}] {fact}")

        return facts

    except Exception as e:
        logger.error(f"Document fact extraction failed: {e}")
        # Fallback: store the chunk as-is if extraction fails
        return [f"[Document: {filename}] {chunk[:200]}..."]


def ingest_document_to_memory(
    document_id: str,
    filename: str,
    content: str,
    user_id: str | None = None,
    chat_id: str | None = None,
) -> dict:
    """
    Ingest a processed document into the vector knowledge base.

    Chunks the document and stores key facts in Qdrant for semantic retrieval.

    Args:
        document_id: Document ID
        filename: Original filename
        content: Extracted document content
        user_id: User identifier
        chat_id: Optional chat ID for cascading delete

    Returns:
        Dictionary with ingestion results
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        return {
            "success": False,
            "error": "Memory client not available",
            "chunks_processed": 0,
            "facts_extracted": 0,
        }

    try:
        logger.debug(f"Ingesting document to memory: {filename[:50]}...")

        # Chunk the document
        chunks = _chunk_text(content, chunk_size=1500, overlap=200)

        if not chunks:
            return {
                "success": True,
                "chunks_processed": 0,
                "facts_extracted": 0,
                "message": "Document too short to chunk",
            }

        all_facts = []
        chunk_count = 0

        # Process each chunk
        for i, chunk in enumerate(chunks):
            chunk_count += 1

            # Extract facts from this chunk
            facts = _extract_facts_from_document(chunk, filename)

            if not facts:
                # Store chunk summary as fallback
                fact_text = f"[Document: {filename}] Section {i+1}: {chunk[:200]}..."
                facts = [fact_text]

            # Store each fact in Qdrant
            for fact in facts:
                try:
                    payload = {
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "memory": fact,
                        "type": "document_fact",
                        "document_id": document_id,
                        "document_filename": filename,
                        "chunk_index": i,
                        "created_at": datetime.utcnow().isoformat(),
                    }

                    embedding = _get_embedding(fact)
                    if embedding is None:
                        continue

                    point_id = str(uuid.uuid4())
                    point = PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload,
                    )

                    client.upsert(collection_name=config.qdrant_collection, points=[point])
                    all_facts.append(point_id)

                except Exception as e:
                    logger.error(f"Failed to store document fact: {e}")

        logger.debug(f"Document ingested: {chunk_count} chunks, {len(all_facts)} facts stored")

        # Update document with chunk count
        from database import update_document
        update_document(document_id, chunk_count=chunk_count)

        return {
            "success": True,
            "chunks_processed": chunk_count,
            "facts_extracted": len(all_facts),
            "message": f"Ingested {chunk_count} chunks with {len(all_facts)} facts",
        }

    except Exception as e:
        logger.error(f"Document ingestion failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "chunks_processed": 0,
            "facts_extracted": 0,
        }


def search_document_memories(query: str, user_id: str | None = None, limit: int = 10) -> list[dict]:
    """
    Search the knowledge base for information from documents.

    Args:
        query: Search query
        user_id: User identifier
        limit: Maximum results

    Returns:
        List of matching document facts with metadata
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        return []

    try:
        query_embedding = _get_embedding(query)
        if query_embedding is None:
            return []

        from qdrant_client.http.models import QueryRequest, Filter, FieldCondition, MatchValue

        results = client.query_points(
            collection_name=config.qdrant_collection,
            query=query_embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="type", match=MatchValue(value="document_fact")),
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        if not results or not results.points:
            return []

        memories = []
        for hit in results:
            if hit.score and hit.score > 0.35:  # Lower threshold for broader recall
                memories.append({
                    "id": str(hit.id),
                    "memory": hit.payload.get("memory", ""),
                    "score": hit.score,
                    "metadata": {
                        "document_id": hit.payload.get("document_id"),
                        "document_filename": hit.payload.get("document_filename"),
                        "chunk_index": hit.payload.get("chunk_index"),
                    },
                })

        return memories

    except Exception as e:
        logger.error(f"Document memory search failed: {e}")
        return []


def delete_document_memories(document_id: str, user_id: str | None = None) -> int:
    """
    Delete all memories associated with a specific document.

    Args:
        document_id: The document ID
        user_id: User identifier

    Returns:
        Number of memories deleted
    """
    user_id = user_id or config.user_id
    client = get_qdrant_client()

    if client is None:
        return 0

    try:
        results, _ = client.scroll(
            collection_name=config.qdrant_collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]
            ),
            limit=500,  # Documents can have many chunks
            with_payload=False,
        )

        if not results:
            return 0

        point_ids = [str(point.id) for point in results]
        client.delete(
            collection_name=config.qdrant_collection,
            points_selector=point_ids,
        )

        return len(point_ids)

    except Exception as e:
        logger.error(f"Document memory delete failed: {e}")
        return 0
