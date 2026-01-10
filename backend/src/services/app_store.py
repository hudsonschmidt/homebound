"""Apple App Store Server API integration for receipt validation.

This module provides server-side validation of App Store purchases using
Apple's App Store Server API (AASA v2).

Setup required in App Store Connect:
1. Create an API key for App Store Server API
2. Download the .p8 private key file
3. Note the Key ID and Issuer ID
4. Configure these values in environment variables:
   - APP_STORE_KEY_ID
   - APP_STORE_ISSUER_ID
   - APP_STORE_PRIVATE_KEY (contents of .p8 file)
   - APP_BUNDLE_ID

Documentation:
https://developer.apple.com/documentation/appstoreserverapi
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from src import config


@dataclass
class TransactionInfo:
    """Parsed transaction information from Apple."""
    transaction_id: str
    original_transaction_id: str
    product_id: str
    purchase_date: str
    expires_date: str | None
    is_upgraded: bool
    revocation_date: str | None
    environment: str
    is_family_shared: bool


class AppStoreService:
    """Service for validating purchases with Apple's App Store Server API."""

    # API endpoints
    PRODUCTION_URL = "https://api.storekit.itunes.apple.com"
    SANDBOX_URL = "https://api.storekit-sandbox.itunes.apple.com"

    def __init__(self):
        settings = config.get_settings()
        self.bundle_id = getattr(settings, "APP_BUNDLE_ID", "com.hudsonschmidt.Homebound")
        self.key_id = getattr(settings, "APP_STORE_KEY_ID", None)
        self.issuer_id = getattr(settings, "APP_STORE_ISSUER_ID", None)
        self.private_key = getattr(settings, "APP_STORE_PRIVATE_KEY", None)

        # Check if configured
        self.is_configured = all([self.key_id, self.issuer_id, self.private_key])

    def _generate_token(self) -> str:
        """Generate JWT for App Store Server API authentication.

        The token is valid for 1 hour (Apple's maximum).
        Uses ES256 algorithm as required by Apple.
        """
        if not self.is_configured:
            raise ValueError("App Store Server API not configured")

        now = int(time.time())
        payload = {
            "iss": self.issuer_id,
            "iat": now,
            "exp": now + 3600,  # 1 hour expiration
            "aud": "appstoreconnect-v1",
            "bid": self.bundle_id,
        }

        headers = {
            "alg": "ES256",
            "kid": self.key_id,
            "typ": "JWT"
        }

        return jwt.encode(
            payload,
            self.private_key,
            algorithm="ES256",
            headers=headers
        )

    def _get_base_url(self, environment: str = "production") -> str:
        """Get the appropriate API URL based on environment."""
        return self.SANDBOX_URL if environment == "sandbox" else self.PRODUCTION_URL

    async def verify_transaction(
        self,
        transaction_id: str,
        environment: str = "production"
    ) -> TransactionInfo | None:
        """Verify a transaction with Apple's servers.

        Args:
            transaction_id: The transaction ID to verify
            environment: "production" or "sandbox"

        Returns:
            TransactionInfo if valid, None if invalid or not found
        """
        if not self.is_configured:
            # Return None to allow development without Apple credentials
            print("[AppStore] Warning: App Store API not configured, skipping verification")
            return None

        try:
            token = self._generate_token()
            base_url = self._get_base_url(environment)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/inApps/v1/transactions/{transaction_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_transaction(data)
                elif response.status_code == 404:
                    return None
                else:
                    print(f"[AppStore] Verification failed: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            print(f"[AppStore] Error verifying transaction: {e}")
            return None

    async def get_subscription_status(
        self,
        original_transaction_id: str,
        environment: str = "production"
    ) -> dict[str, Any] | None:
        """Get current subscription status from Apple.

        Args:
            original_transaction_id: The original transaction ID for the subscription
            environment: "production" or "sandbox"

        Returns:
            Subscription status dict if found, None otherwise
        """
        if not self.is_configured:
            print("[AppStore] Warning: App Store API not configured, skipping status check")
            return None

        try:
            token = self._generate_token()
            base_url = self._get_base_url(environment)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/inApps/v1/subscriptions/{original_transaction_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"[AppStore] Status check failed: {response.status_code}")
                    return None

        except Exception as e:
            print(f"[AppStore] Error checking subscription status: {e}")
            return None

    async def get_transaction_history(
        self,
        original_transaction_id: str,
        environment: str = "production"
    ) -> list[dict] | None:
        """Get full transaction history for a subscription.

        Useful for debugging and auditing subscription lifecycle.
        """
        if not self.is_configured:
            return None

        try:
            token = self._generate_token()
            base_url = self._get_base_url(environment)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/inApps/v1/history/{original_transaction_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("signedTransactions", [])
                else:
                    return None

        except Exception as e:
            print(f"[AppStore] Error fetching history: {e}")
            return None

    def _parse_transaction(self, data: dict) -> TransactionInfo:
        """Parse Apple's signed transaction response."""
        # Apple returns signed JWTs - in production you'd verify and decode these
        # For now, we'll extract the basic fields
        signed_tx = data.get("signedTransactionInfo", "")

        # Decode the JWT payload (Apple uses JWS)
        # In production, verify the signature using Apple's certificate chain
        try:
            # Split the JWT and decode the payload (middle part)
            parts = signed_tx.split(".")
            if len(parts) == 3:
                import base64
                import json
                # Add padding if needed
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))

                return TransactionInfo(
                    transaction_id=payload.get("transactionId", ""),
                    original_transaction_id=payload.get("originalTransactionId", ""),
                    product_id=payload.get("productId", ""),
                    purchase_date=payload.get("purchaseDate", ""),
                    expires_date=payload.get("expiresDate"),
                    is_upgraded=payload.get("isUpgraded", False),
                    revocation_date=payload.get("revocationDate"),
                    environment=payload.get("environment", "Production"),
                    is_family_shared=payload.get("inAppOwnershipType", "") == "FAMILY_SHARED"
                )
        except Exception as e:
            print(f"[AppStore] Error parsing transaction: {e}")

        # Fallback - return empty transaction info
        return TransactionInfo(
            transaction_id="",
            original_transaction_id="",
            product_id="",
            purchase_date="",
            expires_date=None,
            is_upgraded=False,
            revocation_date=None,
            environment="Production",
            is_family_shared=False
        )


# Singleton instance
app_store_service = AppStoreService()
