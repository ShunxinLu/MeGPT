"""
Integrations - External service clients for MeGPT.

Contains:
- PrivacyGuard: Email sanitization and PII masking
- VaultManager: Secure credential storage
- GmailClient: Gmail OAuth and sync
- OutlookClient: Outlook/Hotmail OAuth and sync
"""

from integrations.privacy_guard import PrivacyGuard
from integrations.vault_manager import VaultManager

# Try to import email clients (may fail if dependencies not installed)
try:
    from integrations.gmail_client import GmailClient
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    GmailClient = None

try:
    from integrations.outlook_client import OutlookClient
    OUTLOOK_AVAILABLE = True
except ImportError:
    OUTLOOK_AVAILABLE = False
    OutlookClient = None

__all__ = [
    "PrivacyGuard",
    "VaultManager",
    "GmailClient",
    "OutlookClient",
    "GMAIL_AVAILABLE",
    "OUTLOOK_AVAILABLE",
]
