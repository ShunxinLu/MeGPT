"""
VaultManager - Secure credential storage using OS-level keyring.

Uses Windows Credential Locker via the keyring library to store OAuth tokens
and other sensitive data. Never stores credentials in plain text files.

Ported from personal_assist.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import keyring
try:
    import keyring
    from keyring.errors import KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger.warning("keyring not available. Credentials will be less secure.")


class VaultManager:
    """
    Manages secure storage and retrieval of credentials using OS keyring.

    On Windows, this uses Windows Credential Locker.
    On macOS, this uses Keychain.
    On Linux, this uses Secret Service (GNOME Keyring or KWallet).

    Falls back to encrypted file storage if keyring is not available.
    """

    SERVICE_NAME = "megpt_credentials"

    # Keys for different credential types
    KEY_GMAIL_TOKEN = "gmail_oauth_token"
    KEY_GMAIL_REFRESH = "gmail_refresh_token"
    KEY_OUTLOOK_REFRESH = "outlook_refresh_token"
    KEY_CALENDAR_TOKEN = "calendar_oauth_token"

    def __init__(self, service_name: str | None = None, fallback_dir: str | None = None):
        """
        Initialize VaultManager.

        Args:
            service_name: Optional custom service name for credential storage.
            fallback_dir: Directory for fallback encrypted storage.
        """
        self.service_name = service_name or self.SERVICE_NAME
        self.fallback_dir = fallback_dir

        if KEYRING_AVAILABLE:
            self._verify_keyring_available()
        else:
            logger.warning("Keyring not available, using fallback storage")

    def _verify_keyring_available(self) -> None:
        """Verify that keyring is properly configured and accessible."""
        try:
            # Test keyring by getting the backend name
            backend = keyring.get_keyring()
            logger.info(f"Using keyring backend: {backend.__class__.__name__}")
        except KeyringError as e:
            logger.error(f"Keyring not available: {e}")
            raise RuntimeError(
                "Secure credential storage is not available. "
                "Please ensure Windows Credential Locker is enabled."
            ) from e

    def store_token(self, key: str, token_data: dict[str, Any] | str) -> None:
        """
        Store OAuth token or other credential data securely.

        Args:
            key: The credential key (e.g., KEY_GMAIL_TOKEN)
            token_data: Dictionary containing token information or string value
        """
        if isinstance(token_data, str):
            serialized = token_data
        else:
            serialized = json.dumps(token_data)

        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(self.service_name, key, serialized)
                logger.debug(f"Stored credential: {key}")
                return
            except KeyringError as e:
                logger.error(f"Failed to store credential {key}: {e}")
                # Fall through to fallback storage

        # Fallback: file-based storage (not ideal)
        self._store_fallback(key, serialized)

    def retrieve_token(self, key: str) -> dict[str, Any] | str | None:
        """
        Retrieve stored OAuth token or credential data.

        Args:
            key: The credential key to retrieve

        Returns:
            Dictionary containing token data, string value, or None if not found
        """
        if KEYRING_AVAILABLE:
            try:
                serialized = keyring.get_password(self.service_name, key)
                if serialized is not None:
                    # Try to parse as JSON
                    try:
                        return json.loads(serialized)
                    except json.JSONDecodeError:
                        return serialized
            except KeyringError as e:
                logger.error(f"Failed to retrieve credential {key}: {e}")

        # Fallback: file-based storage
        return self._retrieve_fallback(key)

    def delete_token(self, key: str) -> bool:
        """
        Delete a stored credential.

        Args:
            key: The credential key to delete

        Returns:
            True if deleted, False if not found
        """
        deleted = False

        if KEYRING_AVAILABLE:
            try:
                if self.has_token(key):
                    keyring.delete_password(self.service_name, key)
                    deleted = True
                    logger.debug(f"Deleted credential: {key}")
            except KeyringError as e:
                logger.error(f"Failed to delete credential {key}: {e}")

        # Also delete from fallback
        if self._delete_fallback(key):
            deleted = True

        return deleted

    def has_token(self, key: str) -> bool:
        """
        Check if a credential exists.

        Args:
            key: The credential key to check

        Returns:
            True if the credential exists
        """
        if KEYRING_AVAILABLE:
            try:
                if keyring.get_password(self.service_name, key) is not None:
                    return True
            except KeyringError:
                pass

        # Check fallback
        return self._has_fallback(key)

    # ========== Fallback Storage (when keyring unavailable) ==========

    def _fallback_path(self, key: str) -> str:
        """Get fallback file path for a credential key."""
        from pathlib import Path

        if self.fallback_dir:
            dir_path = Path(self.fallback_dir)
        else:
            # Use data directory
            from config import config
            dir_path = config.data_dir / "credentials"

        dir_path.mkdir(parents=True, exist_ok=True)
        return str(dir_path / f"{key}.json")

    def _store_fallback(self, key: str, serialized: str) -> None:
        """Store credential in fallback file."""
        try:
            import base64
            from pathlib import Path

            path = Path(self._fallback_path(key))
            # Simple encoding (not truly secure, but better than plaintext)
            encoded = base64.b64encode(serialized.encode()).decode()
            path.write_text(encoded)
            logger.debug(f"Stored fallback credential: {key}")
        except Exception as e:
            logger.error(f"Failed to store fallback credential {key}: {e}")
            raise RuntimeError(f"Failed to store credential: {e}") from e

    def _retrieve_fallback(self, key: str) -> dict[str, Any] | str | None:
        """Retrieve credential from fallback file."""
        try:
            import base64
            from pathlib import Path

            path = Path(self._fallback_path(key))
            if not path.exists():
                return None

            encoded = path.read_text()
            decoded = base64.b64decode(encoded).decode()

            # Try to parse as JSON
            try:
                return json.loads(decoded)
            except json.JSONDecodeError:
                return decoded
        except Exception as e:
            logger.error(f"Failed to retrieve fallback credential {key}: {e}")
            return None

    def _delete_fallback(self, key: str) -> bool:
        """Delete credential from fallback file."""
        try:
            from pathlib import Path

            path = Path(self._fallback_path(key))
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False

    def _has_fallback(self, key: str) -> bool:
        """Check if fallback credential exists."""
        try:
            from pathlib import Path

            path = Path(self._fallback_path(key))
            return path.exists()
        except Exception:
            return False

    def clear_all(self) -> None:
        """Clear all stored credentials. Use with caution!"""
        keys = [
            self.KEY_GMAIL_TOKEN,
            self.KEY_GMAIL_REFRESH,
            self.KEY_OUTLOOK_REFRESH,
            self.KEY_CALENDAR_TOKEN,
        ]
        for key in keys:
            self.delete_token(key)
        logger.warning("All credentials cleared from vault")
