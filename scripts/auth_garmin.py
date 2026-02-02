"""
Garmin Connect - Initial Authentication Script

This script performs the initial Garmin Connect authentication with 2FA support.
Run this once to authenticate and save session tokens that the app will reuse.

Usage:
    python scripts/auth_garmin.py

The script will:
1. Prompt for your Garmin username and password
2. Trigger the 2FA email from Garmin
3. Prompt you to enter the one-time passcode from your email
4. Save the session tokens for the app to reuse
"""

import getpass
import logging
from pathlib import Path

# Add project root to path
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import garth
except ImportError:
    print("Error: garth not installed. Run: pip install garth")
    sys.exit(1)

from integrations.vault_manager import VaultManager

# Vault keys for Garmin session
KEY_GARMIN_USERNAME = "garmin_username"
KEY_GARMIN_PASSWORD = "garmin_password"


def main():
    print("=" * 60)
    print("Garmin Connect - Initial Authentication")
    print("=" * 60)
    print()
    print("This will:")
    print("1. Prompt for your Garmin credentials")
    print("2. Trigger a 2FA email to be sent")
    print("3. Ask for the one-time passcode from that email")
    print("4. Save session tokens for MeGPT to use")
    print()
    print("Your credentials are stored securely in Windows Credential Manager.")
    print()

    # Get credentials from user
    username = input("Garmin username/email: ").strip()
    if not username:
        print("Error: Username is required")
        return

    password = getpass.getpass("Garmin password: ")
    if not password:
        print("Error: Password is required")
        return

    # Save credentials to vault
    vault = VaultManager()
    vault.store_token(KEY_GARMIN_USERNAME, username)
    vault.store_token(KEY_GARMIN_PASSWORD, password)
    print("✓ Credentials saved securely")

    # Authenticate with Garmin (this will trigger 2FA)
    print()
    print("Authenticating with Garmin Connect...")
    print("(If 2FA is enabled, check your email for a passcode)")

    try:
        # Use garth for interactive login
        # The login() function will prompt for MFA if needed
        client = garth.Client()
        client.login(username, password)

        # Save session
        session_dir = Path("~/.garth").expanduser()
        session_dir.mkdir(parents=True, exist_ok=True)
        client.save(session_dir)

        print()
        print("✓ Authentication successful!")
        print(f"✓ Session saved to {session_path}")
        print()
        print("You can now use Garmin health data in MeGPT.")
        print("The session tokens will be automatically reused for future connections.")

    except Exception as e:
        print()
        print(f"✗ Authentication failed: {e}")
        print()
        print("Troubleshooting:")
        print("- Make sure your username and password are correct")
        print("- If you have 2FA enabled, you'll receive a passcode by email")
        print("- Enter the passcode when prompted within a few minutes")
        print()
        # Clean up on failure
        vault.delete_token(KEY_GARMIN_USERNAME)
        vault.delete_token(KEY_GARMIN_PASSWORD)
        print("Credentials have been cleared due to failed authentication.")
        return

    print()
    print("=" * 60)
    print("Authentication complete! You can close this window.")
    print("=" * 60)


if __name__ == "__main__":
    main()
