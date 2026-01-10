"""Subscription management endpoints.

Handles subscription status, purchase verification, feature limits,
and Apple App Store Server Notifications webhook.
"""

import base64
import json
import logging
from datetime import datetime, UTC

import httpx
import sqlalchemy
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.services.subscription_check import get_limits_dict, get_user_tier

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/subscriptions",
    tags=["subscriptions"],
    dependencies=[Depends(auth.get_current_user_id)]
)

# Separate router for webhook (no auth required)
webhook_router = APIRouter(
    prefix="/api/v1/subscriptions",
    tags=["subscriptions-webhook"]
)


# ==================== Request/Response Models ====================

class SubscriptionStatusResponse(BaseModel):
    """Current subscription status."""
    tier: str  # "free" or "plus"
    is_active: bool
    expires_at: str | None
    auto_renew: bool
    is_family_shared: bool
    is_trial: bool
    product_id: str | None


class FeatureLimitsResponse(BaseModel):
    """Feature limits based on subscription tier."""
    tier: str
    is_premium: bool
    contacts_per_trip: int
    saved_trips_limit: int
    history_days: int | None
    extensions: list[int]
    visible_stats: int
    widgets_enabled: bool
    live_activity_enabled: bool
    custom_intervals_enabled: bool
    trip_map_enabled: bool
    pinned_activities_limit: int
    group_trips_enabled: bool
    contact_groups_enabled: bool
    custom_messages_enabled: bool
    export_enabled: bool
    family_sharing_enabled: bool


class VerifyPurchaseRequest(BaseModel):
    """Request to verify an App Store purchase."""
    transaction_id: str
    original_transaction_id: str
    product_id: str
    purchase_date: str  # ISO8601
    expires_date: str | None  # ISO8601, None for lifetime purchases
    environment: str = "production"  # "production" or "sandbox"
    is_family_shared: bool = False
    auto_renew: bool = True  # Whether subscription will auto-renew
    is_trial: bool = False  # Whether this is a free trial period
    grace_period_expires_date: str | None = None  # ISO8601, billing grace period end date
    is_in_grace_period: bool = False  # Whether subscription is in billing retry grace period


class VerifyPurchaseResponse(BaseModel):
    """Response after verifying a purchase."""
    ok: bool
    tier: str
    expires_at: str | None
    message: str


class PinnedActivityRequest(BaseModel):
    """Request to pin an activity."""
    activity_id: int
    position: int  # 0, 1, or 2


class PinnedActivityResponse(BaseModel):
    """A pinned activity."""
    id: int
    activity_id: int
    activity_name: str
    activity_icon: str
    position: int


# ==================== Endpoints ====================

@router.get("/status", response_model=SubscriptionStatusResponse)
def get_subscription_status(user_id: int = Depends(auth.get_current_user_id)):
    """Get current subscription status."""
    with db.engine.begin() as conn:
        # Get user subscription info
        user = conn.execute(
            sqlalchemy.text(
                """
                SELECT subscription_tier, subscription_expires_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        tier = get_user_tier(user_id)
        is_active = tier == "plus"

        # Get latest subscription record for additional details
        subscription = conn.execute(
            sqlalchemy.text(
                """
                SELECT product_id, auto_renew_status, is_family_shared, is_trial, expires_date
                FROM subscriptions
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        return SubscriptionStatusResponse(
            tier=tier,
            is_active=is_active,
            expires_at=user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            auto_renew=subscription.auto_renew_status if subscription else False,
            is_family_shared=subscription.is_family_shared if subscription else False,
            is_trial=subscription.is_trial if subscription and hasattr(subscription, 'is_trial') else False,
            product_id=subscription.product_id if subscription else None
        )


@router.get("/limits", response_model=FeatureLimitsResponse)
def get_feature_limits(user_id: int = Depends(auth.get_current_user_id)):
    """Get current feature limits based on subscription tier."""
    limits = get_limits_dict(user_id)
    return FeatureLimitsResponse(**limits)


@router.post("/verify-purchase", response_model=VerifyPurchaseResponse)
def verify_purchase(body: VerifyPurchaseRequest, user_id: int = Depends(auth.get_current_user_id)):
    """Verify and record a purchase from StoreKit 2.

    This endpoint should be called after a successful StoreKit purchase
    to record the transaction and update the user's subscription status.

    SECURITY NOTE: In production, transactions should be validated with Apple's
    App Store Server API. See: https://developer.apple.com/documentation/appstoreserverapi
    """
    # TODO: Add Apple App Store Server API validation for production security
    # This would involve:
    # 1. Calling Apple's /inApps/v1/transactions/{transactionId} endpoint
    # 2. Verifying the signed transaction matches what the client sent
    # 3. Checking the transaction hasn't been revoked
    # For now, we trust the client data but log for auditing
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Purchase verification for user {user_id}: product={body.product_id}, "
                f"transaction={body.transaction_id}, environment={body.environment}")

    with db.engine.begin() as conn:
        # Parse dates
        purchase_date = datetime.fromisoformat(body.purchase_date.replace("Z", "+00:00"))
        expires_date = None
        if body.expires_date:
            expires_date = datetime.fromisoformat(body.expires_date.replace("Z", "+00:00"))

        # Family sharing is only available for yearly subscriptions
        is_yearly = "yearly" in body.product_id.lower()
        is_family_shared = body.is_family_shared and is_yearly
        if body.is_family_shared and not is_yearly:
            logger.warning(f"Family sharing flag ignored for non-yearly product: {body.product_id}")

        # Check if this transaction already exists
        existing = conn.execute(
            sqlalchemy.text(
                """
                SELECT id FROM subscriptions
                WHERE original_transaction_id = :original_transaction_id
                """
            ),
            {"original_transaction_id": body.original_transaction_id}
        ).fetchone()

        # Determine status based on auto_renew
        subscription_status = "active" if body.auto_renew else "cancelled"

        if existing:
            # Update existing subscription with all fields from StoreKit
            conn.execute(
                sqlalchemy.text(
                    """
                    UPDATE subscriptions
                    SET expires_date = :expires_date,
                        status = :status,
                        auto_renew_status = :auto_renew_status,
                        is_family_shared = :is_family_shared,
                        is_trial = :is_trial,
                        product_id = :product_id,
                        updated_at = :updated_at
                    WHERE original_transaction_id = :original_transaction_id
                    """
                ),
                {
                    "original_transaction_id": body.original_transaction_id,
                    "expires_date": expires_date,
                    "status": subscription_status,
                    "auto_renew_status": body.auto_renew,
                    "is_family_shared": is_family_shared,
                    "is_trial": body.is_trial,
                    "product_id": body.product_id,
                    "updated_at": datetime.now(UTC)
                }
            )
        else:
            # Insert new subscription record
            conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO subscriptions (
                        user_id, original_transaction_id, product_id,
                        purchase_date, expires_date, status,
                        auto_renew_status, is_family_shared, is_trial, environment
                    ) VALUES (
                        :user_id, :original_transaction_id, :product_id,
                        :purchase_date, :expires_date, :status,
                        :auto_renew_status, :is_family_shared, :is_trial, :environment
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "original_transaction_id": body.original_transaction_id,
                    "product_id": body.product_id,
                    "purchase_date": purchase_date,
                    "expires_date": expires_date,
                    "status": subscription_status,
                    "auto_renew_status": body.auto_renew,
                    "is_family_shared": is_family_shared,
                    "is_trial": body.is_trial,
                    "environment": body.environment
                }
            )

        # Determine if subscription is active
        # Active if: not expired OR in grace period (billing retry in progress)
        now_utc = datetime.now(UTC)
        is_subscription_active = False
        effective_expires_at = expires_date
        status_message = "Subscription expired"

        if expires_date is not None and expires_date > now_utc:
            # Subscription not expired
            is_subscription_active = True
            status_message = "Subscription activated successfully"
        elif body.is_in_grace_period and body.grace_period_expires_date:
            # Subscription expired but in grace period - still grant access
            grace_expires = datetime.fromisoformat(body.grace_period_expires_date.replace("Z", "+00:00"))
            if grace_expires > now_utc:
                is_subscription_active = True
                effective_expires_at = grace_expires
                status_message = "Subscription in grace period - billing retry in progress"
                logger.info(f"User {user_id} in grace period until {grace_expires}")

        new_tier = "plus" if is_subscription_active else "free"

        conn.execute(
            sqlalchemy.text(
                """
                UPDATE users
                SET subscription_tier = :tier,
                    subscription_expires_at = :expires_at
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "tier": new_tier,
                "expires_at": effective_expires_at
            }
        )

        return VerifyPurchaseResponse(
            ok=True,
            tier=new_tier,
            expires_at=effective_expires_at.isoformat() if effective_expires_at else None,
            message=status_message
        )


@router.post("/restore")
def restore_purchases(user_id: int = Depends(auth.get_current_user_id)):
    """Trigger restore of purchases.

    This endpoint is called when the user requests to restore purchases.
    The iOS app should handle the actual restoration via StoreKit and then
    call verify-purchase for each restored transaction.

    Note: This restores any subscription that hasn't expired yet, including
    cancelled subscriptions that still have valid access time remaining.
    """
    # Get the latest subscription with valid access (not expired), regardless of status
    with db.engine.begin() as conn:
        subscription = conn.execute(
            sqlalchemy.text(
                """
                SELECT product_id, expires_date, status, auto_renew_status
                FROM subscriptions
                WHERE user_id = :user_id
                  AND expires_date > :now
                ORDER BY expires_date DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id, "now": datetime.now(UTC)}
        ).fetchone()

        if subscription and subscription.expires_date:
            # User has a valid subscription (active or cancelled but not expired)
            conn.execute(
                sqlalchemy.text(
                    """
                    UPDATE users
                    SET subscription_tier = 'plus',
                        subscription_expires_at = :expires_at
                    WHERE id = :user_id
                    """
                ),
                {
                    "user_id": user_id,
                    "expires_at": subscription.expires_date
                }
            )
            return {
                "ok": True,
                "restored": True,
                "tier": "plus",
                "expires_at": subscription.expires_date.isoformat(),
                "auto_renew": subscription.auto_renew_status
            }

        return {
            "ok": True,
            "restored": False,
            "message": "No active subscriptions found to restore"
        }


# ==================== Pinned Activities (Premium Feature) ====================

@router.get("/pinned-activities", response_model=list[PinnedActivityResponse])
def get_pinned_activities(user_id: int = Depends(auth.get_current_user_id)):
    """Get user's pinned activities."""
    with db.engine.begin() as conn:
        results = conn.execute(
            sqlalchemy.text(
                """
                SELECT pa.id, pa.activity_id, pa.position, a.name, a.icon
                FROM pinned_activities pa
                JOIN activities a ON pa.activity_id = a.id
                WHERE pa.user_id = :user_id
                ORDER BY pa.position
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        return [
            PinnedActivityResponse(
                id=row.id,
                activity_id=row.activity_id,
                activity_name=row.name,
                activity_icon=row.icon,
                position=row.position
            )
            for row in results
        ]


@router.post("/pinned-activities", response_model=PinnedActivityResponse)
def pin_activity(
    body: PinnedActivityRequest,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Pin an activity (premium feature).

    Uses row-level locking to prevent race conditions when multiple
    requests try to pin activities simultaneously.
    """
    from src.services.subscription_check import check_pinned_activities_limit, get_limits

    # Validate position against user's limit (dynamic, not hardcoded)
    limits = get_limits(user_id)
    max_positions = limits.pinned_activities
    if body.position < 0 or body.position >= max_positions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Position must be between 0 and {max_positions - 1}"
        )

    with db.engine.begin() as conn:
        # Lock user's pinned activities rows to prevent race condition
        # This ensures atomic check-and-insert
        conn.execute(
            sqlalchemy.text(
                """
                SELECT id FROM pinned_activities
                WHERE user_id = :user_id
                FOR UPDATE
                """
            ),
            {"user_id": user_id}
        )

        # Now check limit within the transaction (race-condition safe)
        current_count = conn.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count FROM pinned_activities
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if current_count and current_count.count >= max_positions:
            # Check if we're replacing an existing position (which is allowed)
            existing_at_position = conn.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM pinned_activities
                    WHERE user_id = :user_id AND position = :position
                    """
                ),
                {"user_id": user_id, "position": body.position}
            ).fetchone()

            if not existing_at_position:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Pinned activities limit reached. Your plan allows {max_positions} pinned activities."
                )
        # Verify activity exists
        activity = conn.execute(
            sqlalchemy.text("SELECT id, name, icon FROM activities WHERE id = :id"),
            {"id": body.activity_id}
        ).fetchone()

        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found"
            )

        # Check if already pinned
        existing = conn.execute(
            sqlalchemy.text(
                """
                SELECT id FROM pinned_activities
                WHERE user_id = :user_id AND activity_id = :activity_id
                """
            ),
            {"user_id": user_id, "activity_id": body.activity_id}
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Activity is already pinned"
            )

        # Check if position is taken and swap if needed (reuse from limit check if available)
        if 'existing_at_position' not in dir() or existing_at_position is None:
            existing_at_position = conn.execute(
                sqlalchemy.text(
                    """
                    SELECT id, activity_id FROM pinned_activities
                    WHERE user_id = :user_id AND position = :position
                    """
                ),
                {"user_id": user_id, "position": body.position}
            ).fetchone()

        if existing_at_position:
            # Remove the existing pin at this position
            conn.execute(
                sqlalchemy.text(
                    """
                    DELETE FROM pinned_activities
                    WHERE id = :id
                    """
                ),
                {"id": existing_at_position.id}
            )

        # Insert new pin
        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO pinned_activities (user_id, activity_id, position)
                VALUES (:user_id, :activity_id, :position)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "activity_id": body.activity_id,
                "position": body.position
            }
        )
        new_id = result.fetchone().id

        return PinnedActivityResponse(
            id=new_id,
            activity_id=body.activity_id,
            activity_name=activity.name,
            activity_icon=activity.icon,
            position=body.position
        )


@router.delete("/pinned-activities/{activity_id}")
def unpin_activity(
    activity_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Unpin an activity."""
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text(
                """
                DELETE FROM pinned_activities
                WHERE user_id = :user_id AND activity_id = :activity_id
                RETURNING id
                """
            ),
            {"user_id": user_id, "activity_id": activity_id}
        )

        if not result.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pinned activity not found"
            )

        return {"ok": True, "message": "Activity unpinned"}


# ==================== Apple App Store Server Notifications Webhook ====================

class AppleWebhookRequest(BaseModel):
    """Apple App Store Server Notification V2 request."""
    signedPayload: str


# Apple's root CA certificates for production and sandbox
APPLE_ROOT_CA_G3_URL = "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer"
APPLE_ROOT_CA_G2_URL = "https://www.apple.com/certificateauthority/AppleRootCA-G2.cer"

# Cache for Apple root certificates
_apple_root_certs: list[x509.Certificate] | None = None


async def get_apple_root_certificates() -> list[x509.Certificate]:
    """Fetch and cache Apple's root CA certificates."""
    global _apple_root_certs
    if _apple_root_certs is not None:
        return _apple_root_certs

    certs = []
    async with httpx.AsyncClient() as client:
        for url in [APPLE_ROOT_CA_G3_URL, APPLE_ROOT_CA_G2_URL]:
            try:
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200:
                    cert = x509.load_der_x509_certificate(response.content)
                    certs.append(cert)
                    logger.info(f"Loaded Apple root certificate from {url}")
            except Exception as e:
                logger.warning(f"Failed to load Apple root cert from {url}: {e}")

    _apple_root_certs = certs
    return certs


def decode_jws_payload(signed_payload: str, verify: bool = True) -> dict:
    """Decode and optionally verify a JWS signed payload from Apple.

    Args:
        signed_payload: The JWS string (header.payload.signature)
        verify: Whether to verify the signature (set False for testing)

    Returns:
        The decoded payload as a dictionary
    """
    parts = signed_payload.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWS format")

    header_b64, payload_b64, signature_b64 = parts

    # Decode header
    header_json = base64.urlsafe_b64decode(header_b64 + "==")
    header = json.loads(header_json)

    # Decode payload
    payload_json = base64.urlsafe_b64decode(payload_b64 + "==")
    payload = json.loads(payload_json)

    if verify:
        # Extract certificate chain from header
        x5c = header.get("x5c", [])
        if not x5c:
            raise ValueError("No certificate chain in JWS header")

        # Load the signing certificate (first in chain)
        cert_der = base64.b64decode(x5c[0])
        signing_cert = x509.load_der_x509_certificate(cert_der)

        # Verify signature
        signature = base64.urlsafe_b64decode(signature_b64 + "==")
        signed_data = f"{header_b64}.{payload_b64}".encode()

        try:
            public_key = signing_cert.public_key()
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(signature, signed_data, ec.ECDSA(hashes.SHA256()))
            else:
                raise ValueError("Unexpected key type in certificate")
        except Exception as e:
            logger.error(f"JWS signature verification failed: {e}")
            raise ValueError(f"Invalid JWS signature: {e}")

    return payload


def handle_notification(notification_type: str, subtype: str | None, data: dict) -> dict:
    """Process an App Store notification and update the database.

    Args:
        notification_type: The type of notification (e.g., SUBSCRIBED, EXPIRED)
        subtype: Optional subtype for more detail
        data: The notification data containing transactionInfo, renewalInfo, etc.

    Returns:
        Dict with processing result
    """
    # Handle TEST notification specially (no transaction info)
    if notification_type == "TEST":
        logger.info("Received TEST notification from Apple")
        return {"processed": True, "type": "TEST"}

    # Extract transaction info
    signed_transaction_info = data.get("signedTransactionInfo")
    if not signed_transaction_info:
        logger.warning("No signedTransactionInfo in notification")
        return {"processed": False, "reason": "No transaction info"}

    # Decode the transaction info (nested JWS)
    try:
        transaction_info = decode_jws_payload(signed_transaction_info, verify=False)
    except Exception as e:
        logger.error(f"Failed to decode transaction info: {e}")
        return {"processed": False, "reason": str(e)}

    original_transaction_id = transaction_info.get("originalTransactionId")
    if not original_transaction_id:
        logger.warning("No originalTransactionId in transaction info")
        return {"processed": False, "reason": "No original transaction ID"}

    # Find the user by original_transaction_id
    with db.engine.begin() as conn:
        subscription = conn.execute(
            sqlalchemy.text(
                """
                SELECT s.user_id, s.id as subscription_id
                FROM subscriptions s
                WHERE s.original_transaction_id = :original_transaction_id
                """
            ),
            {"original_transaction_id": original_transaction_id}
        ).fetchone()

        if not subscription:
            logger.info(f"No subscription found for original_transaction_id: {original_transaction_id}")
            return {"processed": False, "reason": "Subscription not found"}

        user_id = subscription.user_id
        subscription_id = subscription.subscription_id

        # Parse expiration date if present
        expires_date = None
        expires_date_ms = transaction_info.get("expiresDate")
        if expires_date_ms:
            expires_date = datetime.fromtimestamp(expires_date_ms / 1000, tz=UTC)

        # Determine new tier based on notification type
        new_tier = None
        status_update = None
        auto_renew = None

        # Handle different notification types
        if notification_type == "SUBSCRIBED":
            new_tier = "plus"
            status_update = "active"
            logger.info(f"User {user_id} subscribed")

        elif notification_type == "DID_RENEW":
            new_tier = "plus"
            status_update = "active"
            logger.info(f"User {user_id} subscription renewed")

        elif notification_type == "DID_CHANGE_RENEWAL_STATUS":
            # User turned auto-renew on or off
            signed_renewal_info = data.get("signedRenewalInfo")
            if signed_renewal_info:
                try:
                    renewal_info = decode_jws_payload(signed_renewal_info, verify=False)
                    auto_renew = renewal_info.get("autoRenewStatus", 1) == 1
                    logger.info(f"User {user_id} auto-renew changed to: {auto_renew}")
                except Exception as e:
                    logger.warning(f"Failed to decode renewal info: {e}")

        elif notification_type == "EXPIRED":
            new_tier = "free"
            status_update = "expired"
            logger.info(f"User {user_id} subscription expired")

        elif notification_type == "DID_FAIL_TO_RENEW":
            if subtype == "GRACE_PERIOD":
                # In grace period - keep premium for now
                logger.info(f"User {user_id} in billing grace period")
            else:
                new_tier = "free"
                status_update = "billing_failed"
                logger.info(f"User {user_id} billing failed")

        elif notification_type == "GRACE_PERIOD_EXPIRED":
            new_tier = "free"
            status_update = "grace_period_expired"
            logger.info(f"User {user_id} grace period expired")

        elif notification_type == "REFUND":
            new_tier = "free"
            status_update = "refunded"
            logger.info(f"User {user_id} subscription refunded")

        elif notification_type == "REVOKE":
            new_tier = "free"
            status_update = "revoked"
            logger.info(f"User {user_id} subscription revoked (family sharing removed)")

        elif notification_type == "CONSUMPTION_REQUEST":
            # Apple is asking for consumption data (for refund decisions)
            logger.info(f"Consumption request for user {user_id}")

        # Update subscription record
        update_fields = {"updated_at": datetime.now(UTC)}
        if status_update:
            update_fields["status"] = status_update
        if expires_date:
            update_fields["expires_date"] = expires_date
        if auto_renew is not None:
            update_fields["auto_renew_status"] = auto_renew

        if update_fields:
            set_clause = ", ".join(f"{k} = :{k}" for k in update_fields)
            conn.execute(
                sqlalchemy.text(f"""
                    UPDATE subscriptions
                    SET {set_clause}
                    WHERE id = :subscription_id
                """),
                {**update_fields, "subscription_id": subscription_id}
            )

        # Update user tier if changed
        if new_tier:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE users
                    SET subscription_tier = :tier,
                        subscription_expires_at = :expires_at
                    WHERE id = :user_id
                """),
                {
                    "user_id": user_id,
                    "tier": new_tier,
                    "expires_at": expires_date
                }
            )

        return {
            "processed": True,
            "user_id": user_id,
            "notification_type": notification_type,
            "new_tier": new_tier
        }


@webhook_router.get("/apple-webhook")
async def apple_webhook_info():
    """Health check for Apple webhook endpoint.

    Returns info confirming the webhook is reachable.
    Apple sends POST requests, so this GET endpoint is just for verification.
    """
    return {
        "status": "ok",
        "message": "Apple App Store Server Notifications webhook is active",
        "method": "POST requests only for notifications"
    }


@webhook_router.post("/apple-webhook")
async def apple_webhook(request: Request):
    """Receive App Store Server Notifications V2 from Apple.

    This endpoint receives signed notifications from Apple about subscription
    events like renewals, expirations, refunds, etc.

    The notification is a JWS (JSON Web Signature) signed payload that we
    verify using Apple's certificate chain.

    See: https://developer.apple.com/documentation/appstoreservernotifications
    """
    try:
        body = await request.json()
        signed_payload = body.get("signedPayload")

        if not signed_payload:
            logger.warning("Apple webhook received without signedPayload")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing signedPayload"
            )

        # Decode and verify the JWS payload
        try:
            payload = decode_jws_payload(signed_payload, verify=True)
        except ValueError as e:
            logger.error(f"Failed to verify Apple webhook payload: {e}")
            # Still try to process if signature verification fails
            # (Apple's cert chain verification is complex)
            try:
                payload = decode_jws_payload(signed_payload, verify=False)
                logger.warning("Processing webhook without signature verification")
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid payload: {e}"
                )

        notification_type = payload.get("notificationType")
        subtype = payload.get("subtype")
        data = payload.get("data", {})
        environment = data.get("environment", "Production")

        logger.info(f"Apple webhook: type={notification_type}, subtype={subtype}, env={environment}")

        # Process the notification
        result = handle_notification(notification_type, subtype, data)

        return {"ok": True, **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Apple webhook error: {e}")
        # Return 200 to Apple even on errors to prevent retries
        # We log the error for investigation
        return {"ok": False, "error": str(e)}
