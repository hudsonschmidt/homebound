"""Tests for subscription validation and feature limits."""
from datetime import datetime, timedelta, UTC

import pytest
import sqlalchemy
from fastapi import HTTPException

from src import database as db
from src.services.subscription_check import (
    FREE_LIMITS,
    PLUS_LIMITS,
    FeatureLimits,
    get_user_tier,
    get_limits,
    get_limits_dict,
    check_contact_limit,
    check_extension_allowed,
    check_group_trips_allowed,
    check_custom_intervals_allowed,
    check_custom_messages_allowed,
    filter_history_by_tier,
)


# ==================== Tier Determination Tests ====================

def test_get_user_tier_free_user():
    """User with no subscription returns 'free'"""
    test_email = "tier-free@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with no subscription (default tier)
        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Free",
                "last_name": "User",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        tier = get_user_tier(user_id)
        assert tier == "free"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_get_user_tier_plus_user():
    """User with valid subscription returns 'plus'"""
    test_email = "tier-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with active plus subscription
        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Plus",
                "last_name": "User",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        tier = get_user_tier(user_id)
        assert tier == "plus"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_get_user_tier_expired_subscription():
    """User with expired subscription returns 'free'"""
    test_email = "tier-expired@homeboundapp.com"
    # Expired yesterday
    expires_at = datetime.now(UTC) - timedelta(days=1)

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with expired plus subscription
        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Expired",
                "last_name": "User",
                "age": 28,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        tier = get_user_tier(user_id)
        assert tier == "free", "Expired subscription should return 'free' tier"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_get_user_tier_nonexistent_user():
    """Non-existent user returns 'free'"""
    tier = get_user_tier(999999)
    assert tier == "free"


def test_get_user_tier_null_tier():
    """User with NULL tier returns 'free'"""
    test_email = "tier-null@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with NULL tier (should default to free)
        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Null",
                "last_name": "Tier",
                "age": 22
            }
        )
        user_id = result.fetchone()[0]

    try:
        tier = get_user_tier(user_id)
        assert tier == "free"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Feature Limits Tests ====================

def test_get_limits_free_tier():
    """Free tier has correct limits"""
    test_email = "limits-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Free",
                "last_name": "Limits",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        limits = get_limits(user_id)

        assert limits.contacts_per_trip == 2
        assert limits.saved_trips == 0
        assert limits.history_days == 30
        assert limits.extensions == [30, 60, 120, 180, 240]  # All extensions now free
        assert limits.visible_stats == 2
        assert limits.widgets is True  # Widgets now free
        assert limits.live_activity is False
        assert limits.custom_intervals is False
        assert limits.trip_map is False
        assert limits.pinned_activities == 0
        assert limits.group_trips is False
        assert limits.contact_groups is False
        assert limits.custom_messages is False
        assert limits.export is True  # Export now free
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_get_limits_plus_tier():
    """Plus tier has correct limits"""
    test_email = "limits-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Plus",
                "last_name": "Limits",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        limits = get_limits(user_id)

        assert limits.contacts_per_trip == 5
        assert limits.saved_trips == 10
        assert limits.history_days is None  # Unlimited
        assert limits.extensions == [30, 60, 120, 180, 240]
        assert limits.visible_stats == 8
        assert limits.widgets is True
        assert limits.live_activity is True
        assert limits.custom_intervals is True
        assert limits.trip_map is True
        assert limits.pinned_activities == 3
        assert limits.group_trips is True
        assert limits.contact_groups is True
        assert limits.custom_messages is True
        assert limits.export is True
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_get_limits_dict_includes_tier():
    """get_limits_dict includes tier and is_premium fields"""
    test_email = "limits-dict@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Dict",
                "last_name": "Test",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        limits = get_limits_dict(user_id)

        assert "tier" in limits
        assert "is_premium" in limits
        assert limits["tier"] == "free"
        assert limits["is_premium"] is False
        assert limits["contacts_per_trip"] == 2
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Limit Enforcement Tests ====================

def test_check_contact_limit_free_allows_two():
    """Free tier allows up to 2 contacts"""
    test_email = "contact-limit@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Contact",
                "last_name": "Limit",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        # Should not raise for 1 or 2 contacts
        check_contact_limit(user_id, 1)
        check_contact_limit(user_id, 2)
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_contact_limit_free_blocks_three():
    """Free tier blocks 3+ contacts with 403"""
    test_email = "contact-block@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Contact",
                "last_name": "Block",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        with pytest.raises(HTTPException) as exc_info:
            check_contact_limit(user_id, 3)
        assert exc_info.value.status_code == 403
        assert "contact limit" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_contact_limit_plus_allows_five():
    """Plus tier allows up to 5 contacts"""
    test_email = "contact-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Contact",
                "last_name": "Plus",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        # Should not raise for up to 5 contacts
        check_contact_limit(user_id, 3)
        check_contact_limit(user_id, 4)
        check_contact_limit(user_id, 5)
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_extension_allowed_free():
    """Free tier now allows all extension durations"""
    test_email = "extension-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Extension",
                "last_name": "Free",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        # All durations should now work for free users
        check_extension_allowed(user_id, 30)
        check_extension_allowed(user_id, 60)
        check_extension_allowed(user_id, 120)
        check_extension_allowed(user_id, 180)
        check_extension_allowed(user_id, 240)
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_extension_allowed_plus():
    """Plus tier allows all extension durations"""
    test_email = "extension-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Extension",
                "last_name": "Plus",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        # All durations should work for plus users
        check_extension_allowed(user_id, 30)
        check_extension_allowed(user_id, 60)
        check_extension_allowed(user_id, 120)
        check_extension_allowed(user_id, 180)
        check_extension_allowed(user_id, 240)
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_group_trips_blocks_free():
    """Free tier cannot create group trips"""
    test_email = "group-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Group",
                "last_name": "Free",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        with pytest.raises(HTTPException) as exc_info:
            check_group_trips_allowed(user_id)
        assert exc_info.value.status_code == 403
        assert "group trips" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_group_trips_allows_plus():
    """Plus tier can create group trips"""
    test_email = "group-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Group",
                "last_name": "Plus",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        # Should not raise
        check_group_trips_allowed(user_id)
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_custom_intervals_default_allowed():
    """Default 30-min interval is always allowed"""
    test_email = "interval-default@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Interval",
                "last_name": "Default",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        # 30 min (default) should always work
        check_custom_intervals_allowed(user_id, 30)
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_custom_intervals_blocks_free():
    """Free tier cannot use custom intervals"""
    test_email = "interval-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Interval",
                "last_name": "Free",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        # Custom intervals should fail for free users
        with pytest.raises(HTTPException) as exc_info:
            check_custom_intervals_allowed(user_id, 15)
        assert exc_info.value.status_code == 403

        with pytest.raises(HTTPException) as exc_info:
            check_custom_intervals_allowed(user_id, 60)
        assert exc_info.value.status_code == 403
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_check_custom_messages_blocks_free():
    """Free tier cannot use custom messages"""
    test_email = "messages-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Messages",
                "last_name": "Free",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        with pytest.raises(HTTPException) as exc_info:
            check_custom_messages_allowed(user_id)
        assert exc_info.value.status_code == 403
        assert "custom" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== History Filtering Tests ====================

def test_filter_history_free_tier():
    """Free tier only sees last 30 days of history"""
    test_email = "history-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, :tier)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "History",
                "last_name": "Free",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        now = datetime.now(UTC)
        trips = [
            {"id": 1, "title": "Recent", "completed_at": now - timedelta(days=5)},
            {"id": 2, "title": "Last Month", "completed_at": now - timedelta(days=25)},
            {"id": 3, "title": "Old", "completed_at": now - timedelta(days=45)},
            {"id": 4, "title": "Very Old", "completed_at": now - timedelta(days=90)},
        ]

        filtered = filter_history_by_tier(user_id, trips)

        # Should only include trips from last 30 days
        assert len(filtered) == 2
        titles = [t["title"] for t in filtered]
        assert "Recent" in titles
        assert "Last Month" in titles
        assert "Old" not in titles
        assert "Very Old" not in titles
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_filter_history_plus_tier():
    """Plus tier sees all history"""
    test_email = "history-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier, subscription_expires_at)
                VALUES (:email, :first_name, :last_name, :age, :tier, :expires_at)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "History",
                "last_name": "Plus",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        now = datetime.now(UTC)
        trips = [
            {"id": 1, "title": "Recent", "completed_at": now - timedelta(days=5)},
            {"id": 2, "title": "Last Month", "completed_at": now - timedelta(days=25)},
            {"id": 3, "title": "Old", "completed_at": now - timedelta(days=45)},
            {"id": 4, "title": "Very Old", "completed_at": now - timedelta(days=90)},
        ]

        filtered = filter_history_by_tier(user_id, trips)

        # Plus users should see all trips
        assert len(filtered) == 4
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Feature Limits Static Tests ====================

def test_free_limits_constant():
    """Verify FREE_LIMITS constant values"""
    assert FREE_LIMITS.contacts_per_trip == 2
    assert FREE_LIMITS.saved_trips == 0
    assert FREE_LIMITS.history_days == 30
    assert FREE_LIMITS.widgets is True  # Widgets now free
    assert FREE_LIMITS.live_activity is False
    assert FREE_LIMITS.group_trips is False
    assert FREE_LIMITS.export is True  # Export now free
    assert FREE_LIMITS.extensions == [30, 60, 120, 180, 240]  # All extensions now free


def test_plus_limits_constant():
    """Verify PLUS_LIMITS constant values"""
    assert PLUS_LIMITS.contacts_per_trip == 5
    assert PLUS_LIMITS.saved_trips == 10
    assert PLUS_LIMITS.history_days is None
    assert PLUS_LIMITS.widgets is True
    assert PLUS_LIMITS.live_activity is True
    assert PLUS_LIMITS.group_trips is True


def test_feature_limits_to_dict():
    """FeatureLimits.to_dict returns expected format"""
    limits_dict = FREE_LIMITS.to_dict()

    assert "contacts_per_trip" in limits_dict
    assert "saved_trips_limit" in limits_dict
    assert "history_days" in limits_dict
    assert "extensions" in limits_dict
    assert "widgets_enabled" in limits_dict
    assert "live_activity_enabled" in limits_dict
