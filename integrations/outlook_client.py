"""
OutlookClient - Microsoft Graph API email synchronization.

Ported from personal_assist. Syncs emails from Outlook/Hotmail accounts
using MSAL authentication.
"""

import base64
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Try to import Outlook API dependencies
try:
    import msal
    import requests

    OUTLOOK_AVAILABLE = True
except ImportError:
    OUTLOOK_AVAILABLE = False
    logger.warning("MSAL or requests not available. Install: msal requests")

from integrations.vault_manager import VaultManager
from integrations.privacy_guard import PrivacyGuard


class OutlookClient:
    """
    Outlook/Hotmail synchronization engine using Microsoft Graph API.

    - Authenticates via MSAL with device code or interactive flow
    - Syncs from Inbox and Sent folders
    - Uses deltaLink for efficient incremental syncs
    """

    GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
    SCOPES = ["https://graph.microsoft.com/Mail.Read"]

    def __init__(
        self,
        vault: VaultManager | None = None,
        privacy_guard: PrivacyGuard | None = None,
        creds_path: Path | str | None = None,
    ):
        """
        Initialize OutlookClient.

        Args:
            vault: VaultManager for token storage
            privacy_guard: Optional PrivacyGuard for sanitization
            creds_path: Path to Outlook credentials JSON
        """
        if not OUTLOOK_AVAILABLE:
            raise RuntimeError("MSAL or requests not available. Install required packages.")

        from config import config

        self.vault = vault or VaultManager()
        self.privacy_guard = privacy_guard or PrivacyGuard()

        # Try multiple locations for credentials
        if creds_path:
            self.creds_path = Path(creds_path)
        else:
            # Try project root credentials folder
            self.creds_path = Path(__file__).parent.parent / "credentials" / "outlook" / "outlook_creds.json"

        self._access_token: str | None = None
        self._app: Any = None

        self._load_credentials()

    def _load_credentials(self) -> None:
        """Load Outlook OAuth credentials from JSON file."""
        if not self.creds_path.exists():
            raise FileNotFoundError(f"Outlook credentials not found: {self.creds_path}")

        with open(self.creds_path) as f:
            creds = json.load(f)

        self.client_id = creds["client_id"]
        self.client_secret = creds.get("client_secret")
        self.tenant_id = creds.get("tenant_id", "consumers")
        # For personal accounts (Hotmail/Outlook.com), use /consumers
        self.authority = "https://login.microsoftonline.com/consumers"

        # Initialize MSAL app
        self._app = msal.PublicClientApplication(
            self.client_id,
            authority=self.authority,
        )

    def authenticate(self) -> str:
        """
        Authenticate with Microsoft Graph API.

        Uses cached refresh token if available, otherwise initiates device code flow.
        Similar approach to Gmail - store only minimal token data in vault.

        Returns:
            Valid access token
        """
        # Try to load existing refresh token from vault
        refresh_token = self.vault.retrieve_token(VaultManager.KEY_OUTLOOK_REFRESH)

        if refresh_token:
            # Use refresh token to get new access token
            try:
                result = self._app.acquire_token_by_refresh_token(
                    refresh_token,
                    scopes=self.SCOPES
                )
                if result and "access_token" in result:
                    self._access_token = result["access_token"]
                    # Update stored refresh token if a new one was provided
                    if result.get("refresh_token") and result["refresh_token"] != refresh_token:
                        self._save_token(result)
                    logger.info("Outlook: Token refreshed successfully")
                    return self._access_token
            except Exception as e:
                logger.warning(f"Failed to refresh Outlook token: {e}")

        # Need fresh authentication - use device code flow
        logger.info("Outlook: Starting device code authentication...")
        flow = self._app.initiate_device_flow(scopes=self.SCOPES)

        if "user_code" not in flow:
            raise Exception(f"Failed to create device flow: {flow.get('error_description')}")

        print(f"\n{'='*60}")
        print("OUTLOOK AUTHENTICATION REQUIRED")
        print(f"{'='*60}")
        print(flow["message"])
        print(f"{'='*60}\n")

        # Wait for user to authenticate
        result = self._app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise Exception(f"Authentication failed: {result.get('error_description')}")

        self._access_token = result["access_token"]
        self._save_token(result)

        logger.info("Outlook: Authentication successful")
        return self._access_token

    def _save_token(self, result: dict) -> None:
        """Save only refresh token to vault (access tokens are fetched fresh)."""
        # Only store refresh_token - it's small enough for Windows Credential Manager
        # Access tokens are large (~1400 bytes) and expire in 1 hour anyway
        if result.get("refresh_token"):
            self.vault.store_token(VaultManager.KEY_OUTLOOK_REFRESH, result["refresh_token"])

    def _get_headers(self) -> dict:
        """Get headers for Graph API requests."""
        if not self._access_token:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }

    def _graph_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a request to Microsoft Graph API."""
        url = f"{self.GRAPH_API_ENDPOINT}{endpoint}"
        response = requests.get(url, headers=self._get_headers(), params=params)

        if response.status_code == 401:
            # Token expired, re-authenticate
            logger.warning("Outlook: Token expired, re-authenticating...")
            self._access_token = None
            self.authenticate()
            response = requests.get(url, headers=self._get_headers(), params=params)

        response.raise_for_status()
        return response.json()

    def is_authenticated(self) -> bool:
        """Check if valid credentials exist."""
        refresh_token = self.vault.retrieve_token(VaultManager.KEY_OUTLOOK_REFRESH)
        return refresh_token is not None

    def perform_initial_sync(
        self,
        months: int = 12,
        on_email: Callable[[dict], None] | None = None
    ) -> tuple[int, str | None]:
        """
        Perform full sync of emails from the past N months.

        Args:
            months: Number of months to sync
            on_email: Callback for each email

        Returns:
            Tuple of (email count, delta_link for future syncs)
        """
        self.authenticate()

        since_date = datetime.now() - timedelta(days=months * 30)
        filter_date = since_date.strftime("%Y-%m-%dT00:00:00Z")

        count = 0
        delta_link = None

        # Sync both inbox and sent items
        for folder in ["inbox", "sentitems"]:
            folder_label = "INBOX" if folder == "inbox" else "SENT"
            logger.info(f"Outlook: Syncing {folder_label} since {filter_date}")

            # Use regular messages endpoint with filter (not delta - delta doesn't support $filter)
            endpoint = f"/me/mailFolders/{folder}/messages"
            params = {
                "$filter": f"receivedDateTime ge {filter_date}",
                "$select": "id,subject,from,toRecipients,receivedDateTime,body,isRead,conversationId",
                "$orderby": "receivedDateTime desc",
                "$top": 100
            }

            folder_count = 0
            page_num = 0

            while True:
                page_num += 1
                try:
                    result = self._graph_request(endpoint, params)
                except Exception as e:
                    logger.error(f"Outlook: Failed to fetch {folder} page {page_num}: {e}")
                    break

                messages = result.get("value", [])
                logger.info(f"Outlook: {folder_label} page {page_num} - {len(messages)} messages")

                for msg in messages:
                    try:
                        email_data = self._parse_message(msg, folder_label)
                        if email_data and on_email:
                            on_email(email_data)
                        count += 1
                        folder_count += 1
                    except Exception as e:
                        logger.error(f"Outlook: Failed to parse message: {e}")

                # Check for next page
                next_link = result.get("@odata.nextLink")
                if next_link:
                    # Extract endpoint from full URL
                    endpoint = next_link.replace(self.GRAPH_API_ENDPOINT, "")
                    params = None  # Next link includes params
                else:
                    break

            logger.info(f"Outlook: {folder_label} sync complete - {folder_count} emails")

        # Get delta link for future incremental syncs (from inbox only)
        try:
            delta_result = self._graph_request("/me/mailFolders/inbox/messages/delta", {"$select": "id"})
            # Skip through pages to get final delta link
            while "@odata.nextLink" in delta_result:
                next_url = delta_result["@odata.nextLink"].replace(self.GRAPH_API_ENDPOINT, "")
                delta_result = self._graph_request(next_url)
            delta_link = delta_result.get("@odata.deltaLink")
        except Exception as e:
            logger.warning(f"Outlook: Failed to get delta link: {e}")

        logger.info(f"Outlook: Initial sync complete - {count} emails")
        return count, delta_link

    def incremental_sync(
        self,
        delta_link: str,
        on_email: Callable[[dict], None] | None = None
    ) -> tuple[int, str | None]:
        """
        Perform incremental sync using delta link.

        Args:
            delta_link: Delta link from previous sync
            on_email: Callback for each email

        Returns:
            Tuple of (email count, new delta_link)
        """
        self.authenticate()

        count = 0
        new_delta_link = None

        # Use the delta link directly
        endpoint = delta_link.replace(self.GRAPH_API_ENDPOINT, "")

        while True:
            try:
                result = self._graph_request(endpoint)
            except requests.HTTPError as e:
                if e.response.status_code == 410:
                    # Delta link expired, need full sync
                    logger.warning("Outlook: Delta link expired, full sync required")
                    return count, None
                raise

            messages = result.get("value", [])

            for msg in messages:
                try:
                    # Determine folder from context or default to INBOX
                    folder = "INBOX"
                    email_data = self._parse_message(msg, folder)
                    if email_data and on_email:
                        on_email(email_data)
                    count += 1
                except Exception as e:
                    logger.error(f"Outlook: Failed to parse message: {e}")

            # Check for next page
            next_link = result.get("@odata.nextLink")
            if next_link:
                endpoint = next_link.replace(self.GRAPH_API_ENDPOINT, "")
            else:
                new_delta_link = result.get("@odata.deltaLink")
                break

        logger.info(f"Outlook: Incremental sync - {count} new emails")
        return count, new_delta_link

    def _parse_message(self, msg: dict, folder: str) -> dict[str, Any] | None:
        """Parse a Graph API message into our email format."""
        try:
            msg_id = msg.get("id", "")
            if not msg_id:
                return None

            # Extract sender
            from_field = msg.get("from", {}).get("emailAddress", {})
            sender = f"{from_field.get('name', '')} <{from_field.get('address', '')}>"

            # Extract recipients
            to_recipients = msg.get("toRecipients", [])
            recipients = [
                r.get("emailAddress", {}).get("address", "")
                for r in to_recipients
            ]

            # Parse date
            received_str = msg.get("receivedDateTime", "")
            if received_str:
                # Parse ISO format: 2024-01-15T10:30:00Z
                received_dt = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
                date_received = int(received_dt.timestamp())
            else:
                date_received = int(datetime.now().timestamp())

            # Extract body (HTML or text)
            body_obj = msg.get("body", {})
            body_content = body_obj.get("content", "")
            body_type = body_obj.get("contentType", "text")

            # Sanitize body through privacy guard
            if body_type.lower() == "html":
                body_markdown = self.privacy_guard.strip_and_sanitize(body_content)
            else:
                body_markdown = self.privacy_guard.mask_pii(body_content)

            return {
                "id": f"outlook_{msg_id}",  # Prefix to avoid ID collision with Gmail
                "thread_id": msg.get("conversationId", msg_id),
                "subject": msg.get("subject", ""),
                "sender": sender,
                "recipients": recipients,
                "date_received": date_received,
                "body_markdown": body_markdown,
                "folder": folder,
                "labels": [folder],
                "source": "outlook",
            }

        except Exception as e:
            logger.error(f"Outlook: Error parsing message: {e}")
            return None
