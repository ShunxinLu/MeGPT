"""
Email Sync Service - Background synchronization for Gmail and Outlook.

Handles:
- Initial sync of past N months
- Incremental sync every 2 hours
- Email processing via EmailProcessor
- State persistence for checkpoint recovery
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from config import config
from integrations import GmailClient, OutlookClient, GMAIL_AVAILABLE, OUTLOOK_AVAILABLE
from integrations.privacy_guard import PrivacyGuard
from integrations.vault_manager import VaultManager
from services.email_processor import EmailProcessor
from database import get_connection

logger = logging.getLogger(__name__)


class EmailSyncService:
    """
    Background email synchronization service.

    Runs periodic syncs for Gmail and Outlook.
    """

    def __init__(
        self,
        initial_sync_months: int = None,
        sync_interval_minutes: int = None,
    ):
        """
        Initialize the sync service.

        Args:
            initial_sync_months: Months of history to sync initially
            sync_interval_minutes: Interval between incremental syncs
        """
        self.initial_sync_months = initial_sync_months or config.email.initial_sync_months
        self.sync_interval_minutes = sync_interval_minutes or config.email.incremental_sync_interval_minutes

        self.privacy_guard = PrivacyGuard()
        self.vault = VaultManager()
        self.processor = EmailProcessor()

        self._is_running = False
        self._sync_task: Optional[asyncio.Task] = None

    def get_sync_state(self) -> dict:
        """Get current sync state from database."""
        try:
            with get_connection() as conn:
                conn.row_factory = lambda cursor, row: dict.fromkeys(
                    [col[0] for col in cursor.description], row
                )
                cursor = conn.execute("SELECT * FROM email_sync_state WHERE id = 1")
                state = cursor.fetchone()

                if state:
                    # Parse JSON fields
                    if state.get("last_sync_at"):
                        state["last_sync_at"] = state["last_sync_at"]
                    return state
        except Exception as e:
            logger.error(f"Failed to get sync state: {e}")

        return {
            "gmail_history_id": None,
            "outlook_delta_link": None,
            "last_sync_at": None,
            "sync_window_start": None,
        }

    def update_sync_state(
        self,
        gmail_history_id: str | None = None,
        outlook_delta_link: str | None = None,
        last_sync_at: str | None = None,
        sync_window_start: str | None = None,
    ) -> None:
        """Update sync state in database."""
        try:
            with get_connection() as conn:
                # Check if exists
                cursor = conn.execute("SELECT id FROM email_sync_state WHERE id = 1")
                exists = cursor.fetchone() is not None

                if exists:
                    # Update only provided fields
                    updates = []
                    values = []
                    if gmail_history_id is not None:
                        updates.append("gmail_history_id = ?")
                        values.append(gmail_history_id)
                    if outlook_delta_link is not None:
                        updates.append("outlook_delta_link = ?")
                        values.append(outlook_delta_link)
                    if last_sync_at is not None:
                        updates.append("last_sync_at = ?")
                        values.append(last_sync_at)
                    if sync_window_start is not None:
                        updates.append("sync_window_start = ?")
                        values.append(sync_window_start)

                    if updates:
                        values.append(1)  # WHERE id = 1
                        conn.execute(
                            f"UPDATE email_sync_state SET {', '.join(updates)} WHERE id = 1",
                            tuple(values)
                        )
                else:
                    # Insert initial state
                    conn.execute("""
                        INSERT INTO email_sync_state (id, gmail_history_id, outlook_delta_link, last_sync_at, sync_window_start)
                        VALUES (1, ?, ?, ?, ?)
                    """, (gmail_history_id, outlook_delta_link, last_sync_at, sync_window_start))

                conn.commit()
                logger.debug(f"Sync state updated: gmail={gmail_history_id}, outlook={outlook_delta_link}")

        except Exception as e:
            logger.error(f"Failed to update sync state: {e}")

    async def sync_gmail(self, force_initial: bool = False) -> dict:
        """
        Sync Gmail emails.

        Args:
            force_initial: Force a full initial sync instead of incremental

        Returns:
            Sync results dict
        """
        if not GMAIL_AVAILABLE:
            return {"error": "Gmail not available - install dependencies"}

        state = self.get_sync_state()
        history_id = state.get("gmail_history_id")

        client = GmailClient(
            vault=self.vault,
            privacy_guard=self.privacy_guard,
        )

        if not client.is_authenticated():
            return {"error": "Gmail not authenticated"}

        if force_initial or not history_id:
            # Initial sync
            logger.info(f"Starting Gmail initial sync ({self.initial_sync_months} months)...")
            count, history_id = await asyncio.to_thread(
                client.perform_initial_sync,
                self.initial_sync_months,
                self._process_email_sync,
            )
            self.update_sync_state(gmail_history_id=history_id)
            return {"gmail": "initial_sync_complete", "count": count, "history_id": history_id}
        else:
            # Incremental sync
            logger.info("Starting Gmail incremental sync...")
            count, history_id = await asyncio.to_thread(
                client.incremental_sync,
                history_id,
                self._process_email_sync,
            )

            if history_id is None:
                # History expired, need full sync
                logger.warning("Gmail history ID expired, running full sync...")
                return await self.sync_gmail(force_initial=True)

            self.update_sync_state(gmail_history_id=history_id)
            return {"gmail": "incremental_sync_complete", "count": count, "history_id": history_id}

    async def sync_outlook(self, force_initial: bool = False) -> dict:
        """
        Sync Outlook emails.

        Args:
            force_initial: Force a full initial sync instead of incremental

        Returns:
            Sync results dict
        """
        if not OUTLOOK_AVAILABLE:
            return {"error": "Outlook not available - install dependencies"}

        state = self.get_sync_state()
        delta_link = state.get("outlook_delta_link")

        client = OutlookClient(
            vault=self.vault,
            privacy_guard=self.privacy_guard,
        )

        if not client.is_authenticated():
            return {"error": "Outlook not authenticated"}

        if force_initial or not delta_link:
            # Initial sync
            logger.info(f"Starting Outlook initial sync ({self.initial_sync_months} months)...")
            count, delta_link = await asyncio.to_thread(
                client.perform_initial_sync,
                self.initial_sync_months,
                self._process_email_sync,
            )
            self.update_sync_state(outlook_delta_link=delta_link)
            return {"outlook": "initial_sync_complete", "count": count, "delta_link": delta_link}
        else:
            # Incremental sync
            logger.info("Starting Outlook incremental sync...")
            count, delta_link = await asyncio.to_thread(
                client.incremental_sync,
                delta_link,
                self._process_email_sync,
            )

            if delta_link is None:
                # Delta link expired, need full sync
                logger.warning("Outlook delta link expired, running full sync...")
                return await self.sync_outlook(force_initial=True)

            self.update_sync_state(outlook_delta_link=delta_link)
            return {"outlook": "incremental_sync_complete", "count": count, "delta_link": delta_link}

    def _process_email_sync(self, raw_email: dict) -> None:
        """Callback for each synced email - process and store."""
        try:
            # Run async processing - asyncio.run() creates a new event loop if needed
            asyncio.run(self.processor.process_email(raw_email))
        except Exception as e:
            logger.error(f"Failed to process email {raw_email.get('id')}: {e}")

    async def sync_all(self, force_initial: bool = False) -> dict:
        """
        Sync all configured email providers.

        Args:
            force_initial: Force full initial sync

        Returns:
            Combined sync results
        """
        results = {}

        # Sync Gmail
        if GMAIL_AVAILABLE:
            try:
                results["gmail"] = await self.sync_gmail(force_initial=force_initial)
            except Exception as e:
                logger.error(f"Gmail sync failed: {e}")
                results["gmail"] = {"error": str(e)}

        # Sync Outlook
        if OUTLOOK_AVAILABLE:
            try:
                results["outlook"] = await self.sync_outlook(force_initial=force_initial)
            except Exception as e:
                logger.error(f"Outlook sync failed: {e}")
                results["outlook"] = {"error": str(e)}

        # Update last sync time
        self.update_sync_state(last_sync_at=datetime.now().isoformat())

        return results

    async def start_background_sync(self) -> None:
        """Start the background sync service."""
        if self._is_running:
            logger.warning("Background sync already running")
            return

        self._is_running = True
        logger.info(f"Starting background email sync (every {self.sync_interval_minutes} minutes)")

        # Initial sync first
        logger.info("Running initial email sync...")
        await self.sync_all(force_initial=True)

        # Then start periodic syncs
        async def _sync_loop():
            while self._is_running:
                try:
                    await asyncio.sleep(self.sync_interval_minutes * 60)
                    if self._is_running:
                        await self.sync_all(force_initial=False)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Background sync error: {e}")
                    # Continue running even if sync fails

        self._sync_task = asyncio.create_task(_sync_loop())

    async def stop_background_sync(self) -> None:
        """Stop the background sync service."""
        self._is_running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("Background email sync stopped")

    @property
    def is_running(self) -> bool:
        """Check if background sync is running."""
        return self._is_running


# Global sync service instance
_sync_service: EmailSyncService | None = None


def get_sync_service() -> EmailSyncService:
    """Get or create the global sync service instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = EmailSyncService()
    return _sync_service
