"""
GmailClient - OAuth loopback flow and email synchronization.

Ported from personal_assist. Syncs emails from INBOX and SENT folders
for full context using incremental sync via Gmail history_id.
"""

import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Try to import Gmail API dependencies
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build, Resource

    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    logger.warning("Google API libraries not available. Install: google-api-python-client google-auth-oauthlib")

from integrations.vault_manager import VaultManager
from integrations.privacy_guard import PrivacyGuard


class GmailClient:
    """
    Gmail synchronization engine with OAuth loopback flow.

    - Authenticates via local loopback (no external server needed)
    - Syncs both INBOX and SENT for full conversation context
    - Uses history_id for efficient incremental syncs
    """

    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    SYNC_LABELS = ['INBOX', 'SENT']

    def __init__(
        self,
        vault: VaultManager | None = None,
        privacy_guard: PrivacyGuard | None = None,
        client_secret_path: Path | str | None = None,
    ):
        """
        Initialize GmailClient.

        Args:
            vault: VaultManager for credential storage
            privacy_guard: Optional PrivacyGuard for sanitization
            client_secret_path: Path to OAuth client secret JSON
        """
        if not GMAIL_AVAILABLE:
            raise RuntimeError("Google API libraries not available. Install required packages.")

        from config import config

        self.vault = vault or VaultManager()
        self.privacy_guard = privacy_guard or PrivacyGuard()
        self.client_secret_path = Path(client_secret_path or config.data_dir / "credentials/google/client_secret.json")

        # Try to find client secret in multiple locations
        if not self.client_secret_path.exists():
            # Try project root credentials folder
            alt_path = Path(__file__).parent.parent / "credentials" / "google"
            if alt_path.exists():
                for secret_file in alt_path.glob("client_secret*.json"):
                    self.client_secret_path = secret_file
                    break

        self._service: Resource | None = None

    def authenticate(self) -> Credentials:
        """
        Authenticate with Gmail using OAuth loopback flow.

        On first run, opens browser for user consent.
        On subsequent runs, uses cached refresh token.

        Returns:
            Valid Gmail credentials
        """
        from google.oauth2.credentials import Credentials

        creds = None

        # Try to load existing credentials
        token_data = self.vault.retrieve_token(VaultManager.KEY_GMAIL_TOKEN)
        if token_data:
            try:
                creds = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes")
                )
            except Exception as e:
                logger.warning(f"Failed to load cached credentials: {e}")
                creds = None

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(creds)
                logger.info("Gmail credentials refreshed")
            except Exception as e:
                logger.warning(f"Failed to refresh credentials: {e}")
                creds = None

        # New authentication flow if no valid credentials
        if not creds or not creds.valid:
            if not self.client_secret_path or not self.client_secret_path.exists():
                raise RuntimeError(
                    f"OAuth client secret not found at {self.client_secret_path}. "
                    "Please download from Google Cloud Console."
                )

            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secret_path),
                self.SCOPES
            )

            # Use loopback server for authentication
            creds = flow.run_local_server(
                port=8080,
                prompt="consent",
                success_message="Authentication successful! You can close this window."
            )

            self._save_credentials(creds)
            logger.info("Gmail authentication successful")

        return creds

    def _save_credentials(self, creds: Credentials) -> None:
        """Save credentials to vault."""
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }
        self.vault.store_token(VaultManager.KEY_GMAIL_TOKEN, token_data)

    def get_service(self) -> Resource:
        """Get or create Gmail API service."""
        if not self._service:
            creds = self.authenticate()
            self._service = build('gmail', 'v1', credentials=creds)
        return self._service

    def is_authenticated(self) -> bool:
        """Check if valid credentials exist."""
        token_data = self.vault.retrieve_token(VaultManager.KEY_GMAIL_TOKEN)
        return token_data is not None

    def perform_initial_sync(
        self,
        months: int = 12,
        on_email: Callable[[dict], None] | None = None
    ) -> tuple[int, str | None]:
        """
        Perform initial historical sync of emails.

        Args:
            months: Number of months of history to sync
            on_email: Optional callback for each email (email_dict) -> None

        Returns:
            Tuple of (email_count, latest_history_id)
        """
        service = self.get_service()

        # Calculate date range
        after_date = datetime.now() - timedelta(days=months * 30)
        query = f"after:{after_date.strftime('%Y/%m/%d')}"

        total_count = 0
        latest_history_id = None

        for label in self.SYNC_LABELS:
            logger.info(f"Syncing {label} folder...")
            count, history_id = self._sync_label(
                service, label, query, on_email
            )
            total_count += count
            if history_id:
                latest_history_id = history_id

        logger.info(f"Initial sync complete: {total_count} emails")
        return total_count, latest_history_id

    def _sync_label(
        self,
        service: Resource,
        label: str,
        query: str,
        on_email: Callable[[dict], None] | None = None
    ) -> tuple[int, str | None]:
        """Sync emails from a specific label."""
        count = 0
        history_id = None
        page_token = None

        while True:
            # List messages
            results = service.users().messages().list(
                userId='me',
                labelIds=[label],
                q=query,
                pageToken=page_token,
                maxResults=100
            ).execute()

            messages = results.get('messages', [])

            for msg_ref in messages:
                try:
                    email_data = self._fetch_and_parse_email(service, msg_ref['id'])
                    if email_data:
                        email_data['folder'] = label
                        history_id = email_data.get('history_id', history_id)

                        if on_email:
                            on_email(email_data)

                        count += 1

                except Exception as e:
                    logger.error(f"Failed to fetch email {msg_ref['id']}: {e}")

            page_token = results.get('nextPageToken')
            if not page_token:
                break

        logger.info(f"Synced {count} emails from {label}")
        return count, history_id

    def _fetch_and_parse_email(
        self,
        service: Resource,
        message_id: str
    ) -> dict[str, Any] | None:
        """Fetch and parse a single email message."""
        msg = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}

        # Extract body
        body_html = self._extract_body(msg.get('payload', {}))

        # Sanitize with PrivacyGuard
        body_markdown = self.privacy_guard.strip_and_sanitize(body_html)

        # Check for spam
        is_spam = self.privacy_guard.is_likely_spam(
            body_markdown,
            headers.get('subject', '')
        )

        return {
            'id': msg['id'],
            'thread_id': msg['threadId'],
            'history_id': msg.get('historyId'),
            'subject': headers.get('subject', ''),
            'sender': headers.get('from', ''),
            'recipients': headers.get('to', ''),
            'date_received': self._parse_date(headers.get('date', '')),
            'body_markdown': body_markdown,
            'labels': msg.get('labelIds', []),
            'is_spam_or_scam': is_spam,
            'source': 'gmail',
        }

    def _extract_body(self, payload: dict) -> str:
        """Extract body content from email payload, preferring HTML over plain text."""
        # Check for direct body
        body_data = payload.get('body', {}).get('data')
        if body_data:
            return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')

        # Check parts (multipart emails) - collect all then prefer HTML
        parts = payload.get('parts', [])
        html_content = None
        plain_content = None

        def extract_from_parts(parts_list):
            nonlocal html_content, plain_content
            for part in parts_list:
                mime_type = part.get('mimeType', '')

                if mime_type == 'text/html' and html_content is None:
                    data = part.get('body', {}).get('data')
                    if data:
                        html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

                elif mime_type == 'text/plain' and plain_content is None:
                    data = part.get('body', {}).get('data')
                    if data:
                        plain_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

                elif mime_type.startswith('multipart/'):
                    # Recursive check for nested parts
                    extract_from_parts(part.get('parts', []))

        extract_from_parts(parts)

        # Prefer HTML over plain text for better formatting preservation
        return html_content or plain_content or ""

    def _parse_date(self, date_str: str) -> int:
        """Parse email date string to Unix timestamp."""
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return int(dt.timestamp())
        except Exception:
            return int(datetime.now().timestamp())

    def incremental_sync(
        self,
        start_history_id: str,
        on_email: Callable[[dict], None] | None = None
    ) -> tuple[int, str | None]:
        """
        Perform incremental sync using Gmail history API.

        Args:
            start_history_id: Last known history_id
            on_email: Optional callback for each new email

        Returns:
            Tuple of (new_email_count, latest_history_id)
        """
        service = self.get_service()
        count = 0
        latest_history_id = start_history_id

        try:
            results = service.users().history().list(
                userId='me',
                startHistoryId=start_history_id,
                historyTypes=['messageAdded']
            ).execute()

            history = results.get('history', [])

            for record in history:
                latest_history_id = record.get('id', latest_history_id)
                messages_added = record.get('messagesAdded', [])

                for msg_data in messages_added:
                    msg_ref = msg_data.get('message', {})
                    try:
                        email_data = self._fetch_and_parse_email(service, msg_ref['id'])
                        if email_data:
                            # Determine folder from labels
                            labels = email_data.get('labels', [])
                            if 'SENT' in labels:
                                email_data['folder'] = 'SENT'
                            else:
                                email_data['folder'] = 'INBOX'

                            if on_email:
                                on_email(email_data)

                            count += 1
                    except Exception as e:
                        logger.error(f"Failed to process email: {e}")

            logger.info(f"Incremental sync: {count} new emails")

        except Exception as e:
            error_str = str(e)
            # Check for expired history ID (404 error)
            if '404' in error_str or 'notFound' in error_str:
                logger.warning(f"History ID {start_history_id} expired, full sync required")
                # Return None to signal caller should do full sync
                return count, None
            else:
                logger.error(f"Incremental sync failed: {e}")

        return count, latest_history_id

    def get_thread_context(self, thread_id: str) -> list[dict]:
        """
        Get all emails in a thread for full context.

        Args:
            thread_id: Gmail thread ID

        Returns:
            List of email dicts in the thread, ordered by date
        """
        service = self.get_service()

        thread = service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'
        ).execute()

        emails = []
        for msg in thread.get('messages', []):
            email_data = self._fetch_and_parse_email(service, msg['id'])
            if email_data:
                # Determine folder
                labels = email_data.get('labels', [])
                email_data['folder'] = 'SENT' if 'SENT' in labels else 'INBOX'
                emails.append(email_data)

        # Sort by date
        emails.sort(key=lambda x: x.get('date_received', 0))

        return emails
