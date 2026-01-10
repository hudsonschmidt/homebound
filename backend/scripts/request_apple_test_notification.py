#!/usr/bin/env python3
"""Request a test notification from Apple App Store Server API.

Usage:
    python scripts/request_apple_test_notification.py \
        --key-file /path/to/AuthKey_XXXXXX.p8 \
        --key-id YOUR_KEY_ID \
        --issuer-id YOUR_ISSUER_ID \
        --bundle-id com.hudsonschmidt.Homebound \
        --sandbox  # Remove for production

You can find these values in App Store Connect:
- Key ID: Users and Access → Integrations → In-App Purchase → Your key
- Issuer ID: Users and Access → Integrations → In-App Purchase (shown at top)
- Bundle ID: Your app's bundle identifier
"""

import argparse
import json
import time

import jwt
import httpx


def create_apple_jwt(key_file: str, key_id: str, issuer_id: str, bundle_id: str) -> str:
    """Create a signed JWT for Apple App Store Server API."""
    with open(key_file, "r") as f:
        private_key = f.read()

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
    parser.add_argument("--key-file", required=True, help="Path to .p8 key file")
    parser.add_argument("--key-id", required=True, help="Key ID from App Store Connect")
    parser.add_argument("--issuer-id", required=True, help="Issuer ID from App Store Connect")
    parser.add_argument("--bundle-id", default="com.hudsonschmidt.Homebound", help="App bundle ID")
    parser.add_argument("--sandbox", action="store_true", help="Use sandbox environment")

    args = parser.parse_args()

    print(f"Creating JWT for bundle: {args.bundle_id}")
    print(f"Environment: {'Sandbox' if args.sandbox else 'Production'}")

    token = create_apple_jwt(
        args.key_file,
        args.key_id,
        args.issuer_id,
        args.bundle_id,
    )

    print(f"JWT created successfully")
    print(f"Requesting test notification...")

    result = request_test_notification(token, args.sandbox)

    if "testNotificationToken" in result:
        print(f"\n✅ Success! Test notification requested.")
        print(f"Token: {result['testNotificationToken']}")
        print(f"\nApple will send a TEST notification to your webhook shortly.")
        print(f"Watch your server logs for: POST /api/v1/subscriptions/apple-webhook")
    else:
        print(f"\n❌ Failed to request test notification")
        print(f"Result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
