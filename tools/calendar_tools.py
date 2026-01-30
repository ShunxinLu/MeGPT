"""
Calendar Tools for MeGPT Domain Integration

This module provides calendar/event management with proposal approval workflow
using the unified database schema from personal-assist integration.
"""

import json
import logging
import sqlite3
import uuid
from langchain_core.tools import tool
from typing import Optional, List
from datetime import datetime
from database import get_connection, get_db_path

logger = logging.getLogger(__name__)


@tool
def get_upcoming_events(days: int = 7) -> str:
    """
    Get upcoming calendar events for the next N days.
    
    Useful for queries like:
    - "what's on my schedule?"
    - "show me events this week"
    - "any meetings tomorrow?"
    
    Args:
        days: Number of days ahead to look (default: 7)
    
    Returns:
        Formatted string with upcoming events
    """
    print(f"📅 Getting upcoming events (next {days} days)...")
    
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT title, start_time, end_time, location, attendees, status
            FROM calendar_events
            WHERE start_time >= datetime('now')
              AND start_time <= datetime('now', '+' || ? || ' days')
              AND status IN ('pending', 'confirmed')
            ORDER BY start_time ASC
            LIMIT 10
        """, (days,))
        
        results = cursor.fetchall()
        
        if not results:
            return f"No upcoming events found in the next {days} days."
        
        # Format results
        formatted = []
        for row in results:
            status_icon = {
                "pending": "⏳",
                "confirmed": "✅",
            }.get(row["status"], "📋")
            
            formatted.append(
                f"{status_icon} {row['start_time']}: {row['title']}"
            )
            
            if row["location"]:
                formatted[-1] += f"\n   📍 {row['location']}"
            
            # Parse attendees JSON if present
            if row["attendees"]:
                try:
                    attendees = json.loads(row["attendees"])
                    if attendees:
                        formatted[-1] += f"\n   👥 {', '.join(attendees)}"
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse attendees for event {row.get('title', 'unknown')}: {e}")
                except (IndexError, TypeError) as e:
                    logger.error(f"Unexpected data format for event attendees: {e}")
        
        return f"📅 UPCOMING EVENTS (next {days} days)\n\n" + "\n\n".join(formatted)


@tool
def create_event(
    title: str,
    start_time: str,
    end_time: str,
    location: str = "",
    description: str = "",
    attendees: str = "[]",
    chat_id: str = ""
) -> str:
    """
    Create a new calendar event directly.
    
    Useful for queries like:
    - "schedule a meeting with John"
    - "add event tomorrow at 2pm"
    - "book dinner for Friday night"
    
    Args:
        title: Event title
        start_time: Start time (ISO format)
        end_time: End time (ISO format)
        location: Event location (optional)
        description: Event description (optional)
        attendees: JSON array of attendee names (optional)
        chat_id: Link to chat if generated from email
    
    Returns:
        Success message with event ID
    """
    print(f"📅 Creating event: {title}")
    
    with get_connection() as conn:
        # Generate event ID
        event_id = str(uuid.uuid4())
        
        # Parse attendees JSON
        attendees_json = attendees if attendees else "[]"
        
        conn.execute("""
            INSERT INTO calendar_events
            (id, chat_id, google_calendar_id, title, description, start_time, end_time, location, attendees, status, action_type, proposal_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'create', 'manual')
        """, (event_id, chat_id or None, None, title, description, start_time, end_time, location, attendees_json))
        
        print(f"✅ Event created with ID: {event_id}")
        
        # Format confirmation
        formatted = [
            f"📅 Event: {title}",
            f"⏰ Time: {start_time} - {end_time}",
        ]
        
        if location:
            formatted.append(f"📍 Location: {location}")
        
        if description:
            formatted.append(f"📝 Description: {description}")
        
        if attendees and attendees != "[]":
            try:
                attendee_list = json.loads(attendees)
                if attendee_list:
                    formatted.append(f"👥 Attendees: {', '.join(attendee_list)}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse attendees JSON: {e}")
        
        return f"Event created successfully!\n\n" + "\n".join(formatted)


@tool
def get_calendar_proposals() -> str:
    """
    Get all pending calendar proposals awaiting approval.
    
    Useful for queries like:
    - "show me pending calendar proposals"
    - "any events I need to approve?"
    - "what's waiting for my approval?"
    
    Returns:
        Formatted list of pending proposals with approve/reject actions
    """
    print(f"📋 Getting pending calendar proposals...")
    
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT id, title, description, start_time, end_time, location, proposal_source, source_email_id, created_at
            FROM calendar_proposals
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        results = cursor.fetchall()
        
        if not results:
            return "No pending proposals found."
        
        # Format results
        formatted = []
        for idx, row in enumerate(results, 1):
            entry = (
                f"PROPOSAL #{idx}: {row['title']}\n"
                f"📅 Time: {row['start_time']} - {row['end_time']}\n"
            )
            
            if row["location"]:
                entry += f"📍 Location: {row['location']}\n"
            
            if row["description"]:
                entry += f"📝 Description: {row['description']}\n"
            
            if row["proposal_source"]:
                source_icon = "✉️" if row["proposal_source"] == "email" else "💬"
                entry += f"📎 Source: {source_icon} {row['proposal_source']}\n"
            
            entry += f"🆔 Proposal ID: {row['id']}\n"
            entry += f"\n⚠️ Requires your approval"
            
            formatted.append(entry)
        
        return f"📋 PENDING PROPOSALS ({len(results)} proposals)\n\n" + "\n\n".join(formatted)


@tool
def approve_proposal(proposal_id: int) -> str:
    """
    Approve a pending calendar proposal.

    Useful for queries like:
    - "approve the meeting proposal"
    - "yes, schedule that event"
    - "I accept the dinner proposal"

    Args:
        proposal_id: ID of the proposal to approve

    Returns:
        Success message with event details
    """
    logger.info(f"Approving proposal {proposal_id}...")

    # Get a raw connection for manual transaction control
    from database import get_db_path
    conn = None
    try:
        conn = sqlite3.connect(get_db_path(), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE TRANSACTION")

        # Get proposal details
        cursor = conn.execute("""
            SELECT * FROM calendar_proposals WHERE id = ?
        """, (proposal_id,))
        proposal = cursor.fetchone()

        if not proposal:
            conn.rollback()
            return "Proposal not found."

        proposal_dict = dict(proposal)

        # Approve the proposal
        conn.execute("""
            UPDATE calendar_proposals
            SET status = 'approved',
                approved_at = datetime('now')
            WHERE id = ?
        """, (proposal_id,))

        # Create the actual calendar event
        event_id = str(uuid.uuid4())
        proposal_source = proposal_dict.get("proposal_source", "manual")

        conn.execute("""
            INSERT INTO calendar_events
            (id, chat_id, google_calendar_id, title, description, start_time, end_time, location, attendees, status, action_type, proposal_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'create', ?)
        """, (
            event_id,
            proposal_dict.get("chat_id"),
            None,  # google_calendar_id - will be set on sync
            proposal_dict.get("title", ""),
            proposal_dict.get("description", ""),
            proposal_dict.get("start_time"),
            proposal_dict.get("end_time"),
            proposal_dict.get("location", ""),
            proposal_dict.get("attendees", "[]"),
            proposal_source,
        ))

        conn.commit()
        logger.info(f"Proposal approved and event created: {event_id}")

        # Format confirmation
        formatted = [
            f"✅ Proposal Approved: {proposal_dict.get('title', '')}",
            f"📅 Scheduled: {proposal_dict.get('start_time')} - {proposal_dict.get('end_time')}",
        ]

        if proposal_dict.get("location"):
            formatted.append(f"📍 Location: {proposal_dict.get('location')}")

        return f"Proposal approved successfully!\n\n" + "\n".join(formatted)

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error during proposal approval: {e}")
        return f"Approval failed due to database error: {str(e)}"
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error during proposal approval: {e}")
        return f"Approval failed: {str(e)}"
    finally:
        if conn:
            conn.close()


@tool
def reject_proposal(proposal_id: str, reason: str = "") -> str:
    """
    Reject a pending calendar proposal.
    
    Useful for queries like:
    - "reject the meeting proposal"
    - "no, I don't want to attend"
    - "decline the dinner proposal"
    - "reject this event"
    
    Args:
        proposal_id: ID of the proposal to reject
        reason: Reason for rejection (optional)
    
    Returns:
        Success message
    """
    print(f"❌ Rejecting proposal {proposal_id}...")
    
    with get_connection() as conn:
        # Get proposal details
        cursor = conn.execute("""
            SELECT title FROM calendar_proposals WHERE id = ?
        """, (proposal_id,))
        result = cursor.fetchone()
        
        if not result:
            return "Proposal not found."
        
        title = result["title"]
        
        # Reject the proposal
        conn.execute("""
            UPDATE calendar_proposals
            SET status = 'rejected'
            WHERE id = ?
        """, (proposal_id,))
        
        rejection_note = f"\nReason: {reason}" if reason else ""
        
        print(f"✅ Proposal rejected: {title}")
        
        return f"Proposal rejected: {title}{rejection_note}\n\nThe proposal has been removed from your pending approvals list."


@tool
def update_event(event_id: str, updates: dict) -> str:
    """
    Update an existing calendar event.
    
    Useful for queries like:
    - "change the meeting time to 3pm"
    - "update the event location"
    - "add more attendees"
    
    Args:
        event_id: ID of the event to update
        updates: Dictionary of fields to update (title, time, location, attendees, etc.)
    
    Returns:
        Success message
    """
    print(f"📝 Updating event {event_id}...")
    
    allowed_fields = {
        "title": "title",
        "description": "description",
        "start_time": "start_time",
        "end_time": "end_time",
        "location": "location",
    }
    
    # Build update query dynamically
    set_clauses = []
    params = []
    
    for field in allowed_fields:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])
    
    if not set_clauses:
        return "No valid fields to update."
    
    params.append(event_id)
    
    with get_connection() as conn:
        set_clause = ", ".join(set_clauses)
        
        conn.execute(f"""
            UPDATE calendar_events
            SET {set_clause}
            WHERE id = ?
        """, tuple(params))
        
        updated_fields = list(updates.keys())
        print(f"✅ Event updated: {updated_fields}")
        
        return f"Event updated successfully!\n\nChanged fields: {', '.join(updated_fields)}"


@tool
def delete_event(event_id: str) -> str:
    """
    Delete a calendar event.
    
    Useful for queries like:
    - "cancel the meeting"
    - "delete the event"
    - "remove this from my calendar"
    
    Args:
        event_id: ID of the event to delete
    
    Returns:
        Success message
    """
    print(f"🗑️ Deleting event {event_id}...")
    
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
        
        affected_rows = cursor.rowcount
        
        if affected_rows == 0:
            return "Event not found or already deleted."
        
        print(f"✅ Event deleted successfully")
        return f"Event deleted successfully!"


# Export calendar tools list for use in agent_graph.py
CALENDAR_TOOLS = [
    get_upcoming_events,
    create_event,
    get_calendar_proposals,
    approve_proposal,
    reject_proposal,
    update_event,
    delete_event,
]
