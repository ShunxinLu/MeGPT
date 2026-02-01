"""
Email Processor - AI-powered email classification and fact extraction.

Processes emails through a pipeline:
1. Priority classification (critical/important/normal/low/spam)
2. Action item extraction with deadlines
3. Summary generation
4. Fact extraction for Qdrant

Uses MeGPT's configured LLM and embedding providers.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass

import httpx

from config import config, get_email_classification_llm
from utils.llm_factory import get_llm_config, get_embedding_config
from database import get_connection, get_connection as db_conn

logger = logging.getLogger(__name__)


@dataclass
class ProcessedEmail:
    """Result of email processing."""
    id: str
    subject: str
    sender: str
    body_markdown: str
    summary: str
    priority: str  # critical, important, normal, low, spam
    category: str
    action_items: list[dict]
    deadlines: list[dict]
    is_spam_or_scam: bool
    source: str
    folder: str
    date_received: int


class EmailProcessor:
    """
    AI-powered email processing pipeline.

    Uses MeGPT's LLM provider for:
    - Priority classification
    - Action item extraction
    - Summary generation
    - Fact extraction
    """

    # Priority levels in order of importance
    PRIORITIES = ["critical", "important", "normal", "low", "spam"]

    def __init__(self):
        """Initialize EmailProcessor with MeGPT's LLM config."""
        # Use separate classification model (configurable via UI)
        self.llm_base_url, self.llm_api_key, self.llm_model = get_email_classification_llm()
        self.embed_base_url, _, self.embed_model = get_embedding_config()

    async def process_email(self, raw_email: dict[str, Any]) -> ProcessedEmail:
        """
        Process a raw email through the AI pipeline.

        Args:
            raw_email: Raw email dict from Gmail/Outlook client

        Returns:
            ProcessedEmail with all AI-generated fields
        """
        email_id = raw_email.get("id")
        subject = raw_email.get("subject", "")
        sender = raw_email.get("sender", "")
        body_markdown = raw_email.get("body_markdown", "")
        source = raw_email.get("source", "gmail")
        folder = raw_email.get("folder", "INBOX")

        # Truncate body if too long (avoid token overflow)
        body_for_processing = (body_markdown or "")[:8000]

        # Run AI classification (in parallel where possible)
        is_spam = raw_email.get("is_spam_or_scam", False)

        if is_spam:
            priority = "spam"
            category = "spam"
            summary = "[Spam] " + (subject or "")
            action_items = []
            deadlines = []
        else:
            # Run classification and extraction in parallel
            priority, category = await self._classify_priority(subject, body_for_processing)
            summary = await self._generate_summary(subject, body_for_processing)
            action_items, deadlines = await self._extract_action_items(subject, body_for_processing)

        # If no summary was generated, create a basic one
        if not summary or summary.isspace():
            summary = f"Email from {sender}: {subject or '(no subject)'}"

        processed = ProcessedEmail(
            id=email_id,
            subject=subject,
            sender=sender,
            body_markdown=body_markdown,
            summary=summary,
            priority=priority,
            category=category,
            action_items=action_items,
            deadlines=deadlines,
            is_spam_or_scam=is_spam,
            source=source,
            folder=folder,
            date_received=raw_email.get("date_received", int(datetime.now().timestamp())),
        )

        # Store in database
        await self._store_email(processed)

        # Extract and save facts to Qdrant for semantic search
        if not processed.is_spam_or_scam:
            await self._save_facts_to_qdrant(processed)

        return processed

    async def _classify_priority(self, subject: str, body: str) -> tuple[str, str]:
        """
        Classify email priority and category using LLM.

        Returns:
            Tuple of (priority, category)
        """
        prompt = f"""Classify this email by priority and category.

Subject: {subject}
Body: {body[:3000]}

Respond in JSON format:
{{
    "priority": "critical" | "important" | "normal" | "low",
    "category": "work" | "personal" | "finance" | "shopping" | "social" | "travel" | "other"
}}

Priority guidelines:
- CRITICAL: Requires immediate action, urgent deadlines, legal/financial consequences
- IMPORTANT: Work-related, important dates, but not time-sensitive
- NORMAL: Standard communication
- LOW: Newsletters, notifications, non-essential

Respond ONLY with valid JSON, no other text."""

        try:
            response = httpx.post(
                f"{self.llm_base_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 100,
                },
                headers={"Authorization": f"Bearer {self.llm_api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            # Try to parse JSON
            import json
            try:
                # Remove markdown code blocks if present
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                data = json.loads(content)
                return data.get("priority", "normal"), data.get("category", "other")
            except json.JSONDecodeError:
                # Fallback to regex
                pass

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")

        # Fallback: rule-based classification
        subject_lower = subject.lower()
        body_lower = body.lower()

        # Priority keywords
        if any(kw in subject_lower or kw in body_lower for kw in
               ["urgent", "asap", "deadline", "overdue", "immediate", "action required"]):
            priority = "important"
        elif any(kw in subject_lower for kw in
                 ["newsletter", "unsubscribe", "notification"]):
            priority = "low"
        else:
            priority = "normal"

        # Category keywords
        if any(kw in subject_lower or kw in body_lower for kw in
               ["invoice", "payment", "refund", "order"]):
            category = "finance"
        elif any(kw in subject_lower or kw in body_lower for kw in
                 ["meeting", "project", "deadline", "report"]):
            category = "work"
        elif any(kw in subject_lower or kw in body_lower for kw in
                 ["booking", "flight", "hotel", "trip"]):
            category = "travel"
        else:
            category = "other"

        return priority, category

    async def _generate_summary(self, subject: str, body: str) -> str:
        """Generate a 1-2 sentence summary of the email."""
        # For very short emails, just use subject
        if len(body) < 200:
            return f"{subject}: {body[:100]}..."

        prompt = f"""Summarize this email in 1-2 sentences (max 50 words).

Subject: {subject}
Body: {body[:2000]}

Focus on: main topic, any action required, key dates/times.

Summary:"""

        try:
            response = httpx.post(
                f"{self.llm_base_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 150,
                },
                headers={"Authorization": f"Bearer {self.llm_api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            # Fallback summary
            return f"{subject or '(No subject)'} - {body[:100]}..."

    async def _extract_action_items(self, subject: str, body: str) -> tuple[list[dict], list[dict]]:
        """
        Extract action items and deadlines from email.

        Returns:
            Tuple of (action_items, deadlines)
        """
        prompt = f"""Extract action items and deadlines from this email.

Subject: {subject}
Body: {body[:2000]}

Respond in JSON format:
{{
    "action_items": [
        {{"description": "short description", "who": "who needs to act"}},
        ...
    ],
    "deadlines": [
        {{"date": "ISO date string", "description": "what is due"}},
        ...
    ]
}}

If no action items or deadlines, return empty arrays.
Respond ONLY with valid JSON, no other text."""

        action_items = []
        deadlines = []

        try:
            response = httpx.post(
                f"{self.llm_base_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
                headers={"Authorization": f"Bearer {self.llm_api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            # Parse JSON
            import json
            try:
                # Remove markdown code blocks if present
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                data = json.loads(content)
                action_items = data.get("action_items", [])
                deadlines = data.get("deadlines", [])
            except json.JSONDecodeError:
                pass

        except Exception as e:
            logger.debug(f"Action item extraction failed: {e}")

        return action_items, deadlines

    async def _store_email(self, email: ProcessedEmail) -> None:
        """Store processed email in database."""
        try:
            import json

            with db_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO emails (
                        id, subject, sender, body_markdown, summary,
                        priority, category, is_spam_or_scam,
                        date_received, source, folder,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    email.id,
                    email.subject,
                    email.sender,
                    email.body_markdown,
                    email.summary,
                    email.priority,
                    email.category,
                    1 if email.is_spam_or_scam else 0,
                    datetime.fromtimestamp(email.date_received).isoformat() if email.date_received else None,
                    email.source,
                    email.folder,
                    datetime.now().isoformat(),
                ))

                # Store action items as reminders
                for item in email.action_items:
                    due_date = None
                    # Check if this action has a deadline
                    for deadline in email.deadlines:
                        if item.get("description", "").lower() in deadline.get("description", "").lower():
                            due_date = deadline.get("date")
                            break

                    conn.execute("""
                        INSERT OR REPLACE INTO reminders (
                            id, source_type, source_id, title,
                            description, due_date, priority, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"{email.id}_{hash(item.get('description', ''))}",
                        "email",
                        email.id,
                        item.get("description", "")[:100],
                        item.get("description", ""),
                        due_date,
                        email.priority,
                        "pending",
                    ))

                logger.debug(f"Stored email: {email.id}")

        except Exception as e:
            logger.error(f"Failed to store email {email.id}: {e}")

    async def extract_facts_for_memory(self, email: ProcessedEmail) -> list[str]:
        """
        Extract facts from email for storage in Qdrant.

        These facts will be searchable via semantic search.

        Args:
            email: Processed email

        Returns:
            List of fact strings
        """
        prompt = f"""Extract key factual information from this email that would be useful to remember for future conversations.

Subject: {email.subject}
From: {email.sender}
Summary: {email.summary}

Extract facts like:
- Important dates or deadlines
- Commitments made
- Key decisions
- Travel plans
- Financial information

Return as a bulleted list (3-5 facts max).
Each fact should be a standalone sentence."""

        facts = []

        try:
            response = httpx.post(
                f"{self.llm_base_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 300,
                },
                headers={"Authorization": f"Bearer {self.llm_api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            # Parse bullet points
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("•") or line.startswith("*"):
                    fact = line.lstrip("-•*").strip()
                    if fact:
                        facts.append(fact)

        except Exception as e:
            logger.debug(f"Fact extraction failed: {e}")

        return facts

    async def _save_facts_to_qdrant(self, email: ProcessedEmail) -> None:
        """
        Extract facts from email and save them to Qdrant for semantic search.
        """
        try:
            # Extract facts using LLM
            facts = await self.extract_facts_for_memory(email)

            if not facts:
                # Fallback: create basic facts from summary
                facts = [
                    f"Email from {email.sender}: {email.summary}",
                ]

            # Save to Qdrant using memory_tool function
            from tools.memory_tool import save_email_facts
            from config import config

            saved_count = save_email_facts(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                facts=facts,
                user_id=config.user_id,
            )

            if saved_count > 0:
                logger.info(f"Saved {saved_count} facts from {email.id} to Qdrant")

        except Exception as e:
            logger.error(f"Failed to save facts to Qdrant: {e}")
