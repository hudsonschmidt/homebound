#!/usr/bin/env python3
"""Request a test notification from Apple App Store Server API.

Usage:
    python scripts/request_apple_test_notification.py [--sandbox]

Reads credentials from backend/.env:
    - APP_STORE_KEY_ID
    - APP_STORE_ISSUER_ID
    - APP_STORE_PRIVATE_KEY
    - APP_BUNDLE_ID (optional, defaults to com.hudsonschmidt.Homebound)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import jwt
import httpx
from dotenv import load_dotenv


def create_apple_jwt(private_key: str, key_id: str, issuer_id: str, bundle_id: str) -> str:
    """Create a signed JWT for Apple App Store Server API."""
    now = int(time.time())
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + 3600,  # 1 hour
        "aud": "appstoreconnect-v1",
        "bid": bundle_id,
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )

    return token


def request_test_notification(token: str, sandbox: bool = True) -> dict:
    """Request Apple to send a test notification to your webhook."""
    if sandbox:
        url = "https://api.storekit-sandbox.itunes.apple.com/inApps/v1/notifications/test"
    else:
        url = "https://api.storekit.itunes.apple.com/inApps/v1/notifications/test"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    with httpx.Client() as client:
        response = client.post(url, headers=headers, timeout=30.0)

        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.text, "status": response.status_code}


def main():
    parser = argparse.ArgumentParser(description="Request Apple test notification")
    parser.add_argument("--sandbox", action="store_true", default=True, help="Use sandbox environment (default)")
    parser.add_argument("--production", action="store_true", help="Use production environment")

    args = parser.parse_args()
    use_sandbox = not args.production

    # Load .env from backend directory
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / ".env"

    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        sys.exit(1)

    load_dotenv(env_path)

    # Get credentials from environment
    key_id = os.getenv("APP_STORE_KEY_ID")
    issuer_id = os.getenv("APP_STORE_ISSUER_ID")
    private_key = os.getenv("APP_STORE_PRIVATE_KEY")
    private_key_path = os.getenv("APP_STORE_PRIVATE_KEY_PATH")
    bundle_id = os.getenv("APP_BUNDLE_ID", "com.hudsonschmidt.Homebound")

    # Load private key from file if path is provided
    if not private_key and private_key_path:
        key_file = backend_dir / private_key_path
        if key_file.exists():
            private_key = key_file.read_text()
            print(f"Loaded private key from {key_file}")
        else:
            print(f"Error: Private key file not found at {key_file}")
            sys.exit(1)

    # Validate required credentials
    missing = []
    if not key_id:
        missing.append("APP_STORE_KEY_ID")
    if not issuer_id:
        missing.append("APP_STORE_ISSUER_ID")
    if not private_key:
        missing.append("APP_STORE_PRIVATE_KEY or APP_STORE_PRIVATE_KEY_PATH")

    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print(f"Please add them to {env_path}")
        sys.exit(1)

    # Handle escaped newlines in private key
    private_key = private_key.replace("\\n", "\n")

    print(f"Bundle ID: {bundle_id}")
    print(f"Key ID: {key_id}")
    print(f"Issuer ID: {issuer_id[:8]}...")
    print(f"Environment: {'Sandbox' if use_sandbox else 'Production'}")

    token = create_apple_jwt(private_key, key_id, issuer_id, bundle_id)

    print(f"JWT created successfully")
    print(f"Requesting test notification...")

    result = request_test_notification(token, use_sandbox)

    if "testNotificationToken" in result:
        print(f"\nSuccess! Test notification requested.")
        print(f"Token: {result['testNotificationToken']}")
        print(f"\nApple will send a TEST notification to your webhook shortly.")
        print(f"Watch your server logs for: POST /api/v1/subscriptions/apple-webhook")
    else:
        print(f"\nFailed to request test notification")
        print(f"Result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
