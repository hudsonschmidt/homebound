"""Subscription management endpoints.

Handles subscription status, purchase verification, and feature limits.
"""

from datetime import datetime, UTC

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.services.subscription_check import get_limits_dict, get_user_tier

router = APIRouter(
    prefix="/api/v1/subscriptions",
    tags=["subscriptions"],
    dependencies=[Depends(auth.get_current_user_id)]
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

    In production, this should also validate the transaction with Apple's
    App Store Server API for security.
    """
    with db.engine.begin() as conn:
        # Parse dates
        purchase_date = datetime.fromisoformat(body.purchase_date.replace("Z", "+00:00"))
        expires_date = None
        if body.expires_date:
            expires_date = datetime.fromisoformat(body.expires_date.replace("Z", "+00:00"))

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
                    "is_family_shared": body.is_family_shared,
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
                    "is_family_shared": body.is_family_shared,
                    "is_trial": body.is_trial,
                    "environment": body.environment
                }
            )

        # Only set tier to 'plus' if subscription is not expired
        # For expired or null expires_date, keep as free
        is_subscription_active = (
            expires_date is not None and
            expires_date > datetime.now(UTC)
        )
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
                "expires_at": expires_date
            }
        )

        return VerifyPurchaseResponse(
            ok=True,
            tier=new_tier,
            expires_at=expires_date.isoformat() if expires_date else None,
            message="Subscription activated successfully" if is_subscription_active else "Subscription expired"
        )


@router.post("/restore")
def restore_purchases(user_id: int = Depends(auth.get_current_user_id)):
    """Trigger restore of purchases.

    This endpoint is called when the user requests to restore purchases.
    The iOS app should handle the actual restoration via StoreKit and then
    call verify-purchase for each restored transaction.
    """
    # Get the latest active, non-cancelled subscription for this user
    with db.engine.begin() as conn:
        subscription = conn.execute(
            sqlalchemy.text(
                """
                SELECT product_id, expires_date, status, auto_renew_status
                FROM subscriptions
                WHERE user_id = :user_id
                  AND status = 'active'
                  AND auto_renew_status = TRUE
                ORDER BY expires_date DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if subscription and subscription.expires_date:
            # Handle timezone-aware comparison properly
            expires_date = subscription.expires_date
            if expires_date.tzinfo is None:
                expires_date = expires_date.replace(tzinfo=UTC)
            if expires_date > datetime.now(UTC):
                # User has an active subscription, update their tier
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
                    "expires_at": subscription.expires_date.isoformat()
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
    """Pin an activity (premium feature)."""
    from src.services.subscription_check import check_pinned_activities_limit

    # Check if user can pin more activities
    check_pinned_activities_limit(user_id)

    # Validate position (0, 1, or 2)
    if body.position not in [0, 1, 2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Position must be 0, 1, or 2"
        )

    with db.engine.begin() as conn:
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

        # Check if position is taken and swap if needed
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
