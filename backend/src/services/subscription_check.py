"""Subscription validation utilities and feature limits.

This module defines the feature limits for each subscription tier and provides
utilities for checking subscription status and enforcing limits.
"""

from datetime import datetime, UTC
from dataclasses import dataclass
from typing import Any

import sqlalchemy
from fastapi import Depends, HTTPException, status

from src import database as db
from src.api import auth


@dataclass
class FeatureLimits:
    """Feature limits for a subscription tier."""
    contacts_per_trip: int
    saved_trips: int
    history_days: int | None  # None = unlimited
    extensions: list[int]  # Available extension durations in minutes
    visible_stats: int
    widgets: bool
    live_activity: bool
    custom_intervals: bool
    trip_map: bool  # Access to the Trip Map tab
    pinned_activities: int
    group_trips: bool
    contact_groups: bool
    custom_messages: bool
    export: bool
    family_sharing: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "contacts_per_trip": self.contacts_per_trip,
            "saved_trips_limit": self.saved_trips,
            "history_days": self.history_days,
            "extensions": self.extensions,
            "visible_stats": self.visible_stats,
            "widgets_enabled": self.widgets,
            "live_activity_enabled": self.live_activity,
            "custom_intervals_enabled": self.custom_intervals,
            "trip_map_enabled": self.trip_map,
            "pinned_activities_limit": self.pinned_activities,
            "group_trips_enabled": self.group_trips,
            "contact_groups_enabled": self.contact_groups,
            "custom_messages_enabled": self.custom_messages,
            "export_enabled": self.export,
            "family_sharing_enabled": self.family_sharing,
        }


# Free tier limits
FREE_LIMITS = FeatureLimits(
    contacts_per_trip=2,
    saved_trips=0,
    history_days=30,
    extensions=[30, 60, 120, 180, 240],  # All extension options
    visible_stats=2,
    widgets=True,
    live_activity=False,
    custom_intervals=False,
    trip_map=False,
    pinned_activities=0,
    group_trips=False,
    contact_groups=False,
    custom_messages=False,
    export=True,
    family_sharing=False,
)

# Homebound+ limits
PLUS_LIMITS = FeatureLimits(
    contacts_per_trip=5,
    saved_trips=10,
    history_days=None,  # Unlimited
    extensions=[30, 60, 120, 180, 240],  # 30min, 1hr, 2hr, 3hr, 4hr
    visible_stats=8,
    widgets=True,
    live_activity=True,
    custom_intervals=True,
    trip_map=True,
    pinned_activities=3,
    group_trips=True,
    contact_groups=True,
    custom_messages=True,
    export=True,
    family_sharing=True,
)


def get_user_tier(user_id: int) -> str:
    """Get user's subscription tier.

    Returns 'free' if:
    - User has no subscription
    - Subscription has expired
    - User not found

    Returns 'plus' if user has active Homebound+ subscription.
    """
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text(
                """
                SELECT subscription_tier, subscription_expires_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not result:
            return "free"

        tier = result.subscription_tier
        expires_at = result.subscription_expires_at

        # Check if subscription is still valid
        if tier == "plus" and expires_at:
            # Handle timezone-aware comparison properly
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
            if exp < datetime.now(UTC):
                return "free"

        return tier or "free"


def get_limits(user_id: int) -> FeatureLimits:
    """Get feature limits for a user based on their subscription tier."""
    tier = get_user_tier(user_id)
    return PLUS_LIMITS if tier == "plus" else FREE_LIMITS


def get_limits_dict(user_id: int) -> dict[str, Any]:
    """Get feature limits as a dictionary for API response.

    Note: family_sharing_enabled is only true for yearly subscriptions.
    """
    limits = get_limits(user_id)
    tier = get_user_tier(user_id)
    result = limits.to_dict()
    result["tier"] = tier
    result["is_premium"] = tier == "plus"

    # Family sharing is only available for yearly subscriptions
    if tier == "plus":
        result["family_sharing_enabled"] = _has_yearly_subscription(user_id)
    else:
        result["family_sharing_enabled"] = False

    return result


def _has_yearly_subscription(user_id: int) -> bool:
    """Check if user has a yearly subscription (required for family sharing)."""
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text(
                """
                SELECT product_id FROM subscriptions
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not result or not result.product_id:
            return False

        # Yearly product ID contains "yearly"
        return "yearly" in result.product_id.lower()


async def require_premium(user_id: int = Depends(auth.get_current_user_id)) -> bool:
    """FastAPI dependency that raises 403 if user is not premium.

    Use as a dependency on endpoints that require Homebound+:

        @router.post("/premium-feature")
        def premium_feature(
            user_id: int = Depends(auth.get_current_user_id),
            _: bool = Depends(require_premium)
        ):
            ...
    """
    if get_user_tier(user_id) != "plus":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires Homebound+"
        )
    return True


def check_contact_limit(user_id: int, contact_count: int) -> None:
    """Check if adding contacts would exceed the user's limit.

    Raises HTTPException if limit would be exceeded.
    """
    limits = get_limits(user_id)
    if contact_count > limits.contacts_per_trip:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Contact limit exceeded. Your plan allows {limits.contacts_per_trip} contacts per trip."
        )


def check_saved_trips_limit(user_id: int) -> None:
    """Check if user can save another trip template.

    Raises HTTPException if limit would be exceeded.
    """
    limits = get_limits(user_id)

    if limits.saved_trips == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Saved trips require Homebound+"
        )

    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count
                FROM saved_trips
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        current_count = result.count if result else 0

        if current_count >= limits.saved_trips:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Saved trips limit reached. Your plan allows {limits.saved_trips} saved trips."
            )


def check_extension_allowed(user_id: int, extension_minutes: int) -> None:
    """Check if the requested extension duration is allowed for the user.

    Raises HTTPException if extension is not allowed.
    """
    limits = get_limits(user_id)

    if extension_minutes not in limits.extensions:
        allowed = ", ".join(f"{m} min" for m in limits.extensions)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This extension duration requires Homebound+. Your plan allows: {allowed}"
        )


def check_pinned_activities_limit(user_id: int) -> None:
    """Check if user can pin another activity.

    Raises HTTPException if limit would be exceeded.
    """
    limits = get_limits(user_id)

    if limits.pinned_activities == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pinned activities require Homebound+"
        )

    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count
                FROM pinned_activities
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        current_count = result.count if result else 0

        if current_count >= limits.pinned_activities:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Pinned activities limit reached. Your plan allows {limits.pinned_activities} pinned activities."
            )


def check_group_trips_allowed(user_id: int) -> None:
    """Check if user can create group trips.

    Raises HTTPException if not allowed.
    """
    limits = get_limits(user_id)

    if not limits.group_trips:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Group trips require Homebound+"
        )


def check_custom_intervals_allowed(user_id: int, interval_minutes: int) -> None:
    """Check if user can set a custom check-in interval.

    Free users can only use the default 30-minute interval.
    Premium users can set any interval.

    Raises HTTPException if not allowed.
    """
    DEFAULT_INTERVAL = 30

    # Default interval is always allowed
    if interval_minutes == DEFAULT_INTERVAL:
        return

    limits = get_limits(user_id)

    if not limits.custom_intervals:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Custom check-in intervals require Homebound+. Free plan uses {DEFAULT_INTERVAL}-minute intervals."
        )


def check_custom_messages_allowed(user_id: int) -> None:
    """Check if user can set custom notification messages.

    Custom start and overdue messages are a premium feature.

    Raises HTTPException if not allowed.
    """
    limits = get_limits(user_id)

    if not limits.custom_messages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Custom notification messages require Homebound+"
        )


def filter_history_by_tier(user_id: int, trips: list[dict]) -> list[dict]:
    """Filter trip history based on user's subscription tier.

    Free users only see trips from the last 30 days.
    Premium users see all trips.
    """
    limits = get_limits(user_id)

    if limits.history_days is None:
        return trips

    cutoff_date = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    cutoff_date = cutoff_date - timedelta(days=limits.history_days)

    filtered = []
    for trip in trips:
        # Check completed_at or start_at
        trip_date = trip.get("completed_at") or trip.get("start_at")
        if trip_date:
            if isinstance(trip_date, str):
                trip_date = datetime.fromisoformat(trip_date.replace("Z", "+00:00"))
            # Handle timezone-aware comparison properly
            td = trip_date if trip_date.tzinfo else trip_date.replace(tzinfo=UTC)
            if td >= cutoff_date:
                filtered.append(trip)

    return filtered
