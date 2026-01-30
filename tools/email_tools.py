"""
Email Tools for MeGPT Domain Integration

This module provides email search and retrieval functionality
using the unified database schema from personal-assist integration.
"""

from langchain_core.tools import tool
from typing import Optional
from database import get_connection


@tool
def search_emails(query: str, limit: int = 5, priority: str = "all") -> str:
    """
    Search emails by content using full-text search.

    Supports filtering by priority level (critical, important, normal, low, spam)
    Returns formatted email results with key information.

    Args:
        query: Search query string
        limit: Maximum number of results to return (default: 5)
        priority: Filter by priority level (default: all)

    Returns:
        Formatted string with search results
    """
    print(f"🔍 Searching emails for: {query}")

    with get_connection() as conn:
        # Build SQL query with filters
        sql_query = """
            SELECT id, subject, sender, sender_email, date_received, priority, category, summary
            FROM emails_fts
            WHERE emails_fts MATCH ?
        """
        params = [query]

        # Add priority filter if specified
        if priority and priority != "all":
            sql_query += " AND priority = ?"
            params.append(priority)

        sql_query += " ORDER BY date_received DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(sql_query, tuple(params))
        results = cursor.fetchall()

        if not results:
            return "No emails found matching your query."

        # Format results
        formatted = []
        for row in results:
            priority_icon = {
                "critical": "🔴",
                "important": "🟠",
                "normal": "🔵",
                "low": "🟢",
                "spam": "🟣",
            }.get(row["priority"], "🔵")

            formatted.append(
                f"{priority_icon} [{row['date_received']}] {row['sender']}\n"
                f"Subject: {row['subject']}\n"
                f"Priority: {row['priority'].upper()} | Category: {row['category']}\n"
                f"Summary: {row['summary']}\n"
                f"Email ID: {row['id']}\n"
            )

        return "\n---\n".join(formatted)


@tool
def get_email_thread(email_id: str) -> str:
    """
    Get full email thread with replies.

    Retrieves all emails in the same thread_id ordered chronologically.
    Useful for understanding conversation history or context.

    Args:
        email_id: ID of any email in the thread

    Returns:
        Formatted thread with all emails in the conversation
    """
    print(f"📧 Getting email thread for ID: {email_id}")

    with get_connection() as conn:
        # First get the thread_id of the specified email
        cursor = conn.execute("SELECT thread_id FROM emails WHERE id = ?", (email_id,))
        thread_result = cursor.fetchone()

        if not thread_result:
            return "Email not found."

        thread_id = thread_result["thread_id"]

        # Get all emails in the thread
        cursor.execute(
            """
            SELECT id, subject, sender, sender_email, body_markdown, date_received, priority
            FROM emails
            WHERE thread_id = ?
            ORDER BY date_received ASC
            LIMIT 20
        """,
            (thread_id,),
        )

        results = cursor.fetchall()

        if not results:
            return "No emails found in this thread."

        # Format thread
        formatted = []
        for row in results:
            priority_icon = {
                "critical": "🔴",
                "important": "🟠",
                "normal": "🔵",
                "low": "🟢",
                "spam": "🟣",
            }.get(row["priority"], "🔵")

            formatted.append(
                f"{priority_icon} [{row['date_received']}] {row['sender']}\n"
                f"Subject: {row['subject']}\n"
                f"{row['body_markdown'][:500]}...\n"
                if row["body_markdown"]
                else f"[No content]\n{'─' * 60}\n"
            )

        return f"EMAIL THREAD (Thread ID: {thread_id})\n\n" + "".join(formatted)


@tool
def list_unread_emails(limit: int = 10) -> str:
    """
    List all unread emails across all threads.

    Useful for quick inbox review and processing.

    Args:
        limit: Maximum number of unread emails to return (default: 10)

    Returns:
        Formatted list of unread emails
    """
    print(f"📬 Listing unread emails (limit: {limit})")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, subject, sender, date_received, priority
            FROM emails
            WHERE is_spam_or_scam = 0 AND is_read = 0
            ORDER BY date_received DESC
            LIMIT ?
        """,
            (limit,),
        )

        results = cursor.fetchall()

        if not results:
            return "No unread emails found."

        # Format results
        formatted = []
        for idx, row in enumerate(results, 1):
            priority_icon = {
                "critical": "🔴",
                "important": "🟠",
                "normal": "🔵",
                "low": "🟢",
                "spam": "🟣",
            }.get(row["priority"], "🔵")

            formatted.append(
                f"{idx}. {priority_icon} {row['sender']}: {row['subject']}\n"
                f"   Date: {row['date_received']}\n"
                f"   Priority: {row['priority'].upper()}\n"
                f"   Email ID: {row['id']}\n"
            )

        return f"📬 UNREAD EMAILS ({len(results)} messages)\n\n" + "".join(formatted)


@tool
def get_email_count(priority: str = "all") -> str:
    """
    Get count of emails by priority level.

    Useful for inbox management and triage.

    Args:
        priority: Priority level to count (default: all)

    Returns:
        Formatted count breakdown
    """
    print(f"📊 Getting email counts (priority: {priority})")

    with get_connection() as conn:
        if priority == "all":
            cursor = conn.execute("""
                SELECT priority, COUNT(*) as count
                FROM emails
                WHERE is_spam_or_scam = 0
                GROUP BY priority
                ORDER BY 
                    CASE priority
                        WHEN 'critical' THEN 1
                        WHEN 'important' THEN 2
                        WHEN 'normal' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END
            """)
        else:
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM emails
                WHERE priority = ? AND is_spam_or_scam = 0
            """,
                (priority,),
            )
            results = cursor.fetchall()

            if not results:
                return f"0 emails with priority: {priority}"
            else:
                count = results[0]["count"]
                return f"{count} emails with priority: {priority}"

        results = cursor.fetchall()

        # Format results
        if priority == "all":
            formatted = "\n".join(
                [
                    f"🔴 Critical: {r['count']} emails",
                    f"🟠 Important: {r['count']} emails",
                    f"🔵 Normal: {r['count']} emails",
                    f"🟢 Low: {r['count']} emails",
                ]
            )
            total = sum(r["count"] for r in results)
            formatted += f"\n\n📊 Total: {total} emails"
        else:
            formatted = f"{sum(r['count'] for r in results)} emails found"

        return formatted


# Export email tools list for use in agent_graph.py
EMAIL_TOOLS = [
    search_emails,
    get_email_thread,
    list_unread_emails,
    get_email_count,
]
