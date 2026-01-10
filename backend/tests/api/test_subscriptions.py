"""Tests for subscription API endpoints."""
import asyncio
from datetime import datetime, timedelta, UTC

import pytest
import sqlalchemy
from fastapi import HTTPException

from src import database as db
from src.api.subscriptions import (
    VerifyPurchaseRequest,
    verify_purchase,
    get_subscription_status,
    get_feature_limits,
    restore_purchases,
)


def run_async(coro):
    """Helper to run async functions in sync tests"""
    return asyncio.get_event_loop().run_until_complete(coro)


# ==================== Purchase Verification Tests ====================

def test_verify_purchase_new_subscription():
    """New purchase creates subscription record and updates user tier"""
    test_email = "verify-new@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create free user
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
                "first_name": "Verify",
                "last_name": "New",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        request = VerifyPurchaseRequest(
            transaction_id="txn_123456",
            original_transaction_id="orig_123456",
            product_id="com.homeboundapp.homebound.plus.monthly",
            purchase_date=datetime.now(UTC).isoformat(),
            expires_date=expires_at.isoformat(),
            environment="sandbox",
            is_family_shared=False,
            auto_renew=True,
            is_trial=False
        )

        response = verify_purchase(request, user_id=user_id)

        assert response.ok is True
        assert response.tier == "plus"
        assert response.expires_at is not None

        # Verify user tier was updated
        with db.engine.begin() as conn:
            user = conn.execute(
                sqlalchemy.text("SELECT subscription_tier FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert user.subscription_tier == "plus"

            # Verify subscription record was created
            sub = conn.execute(
                sqlalchemy.text("SELECT * FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert sub is not None
            assert sub.original_transaction_id == "orig_123456"
            assert sub.status == "active"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_verify_purchase_existing_subscription():
    """Existing subscription is updated, not duplicated"""
    test_email = "verify-existing@homeboundapp.com"
    original_expires = datetime.now(UTC) + timedelta(days=30)
    new_expires = datetime.now(UTC) + timedelta(days=60)

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with existing subscription
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
                "first_name": "Verify",
                "last_name": "Existing",
                "age": 30,
                "tier": "plus",
                "expires_at": original_expires
            }
        )
        user_id = result.fetchone()[0]

        # Create existing subscription
        conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO subscriptions (user_id, original_transaction_id, product_id, purchase_date, expires_date, status, auto_renew_status, is_trial, environment)
                VALUES (:user_id, :orig_txn, :product_id, :purchase_date, :expires_date, :status, :auto_renew, :is_trial, :environment)
                """
            ),
            {
                "user_id": user_id,
                "orig_txn": "orig_existing_123",
                "product_id": "com.homeboundapp.homebound.plus.monthly",
                "purchase_date": datetime.now(UTC),
                "expires_date": original_expires,
                "status": "active",
                "auto_renew": True,
                "is_trial": False,
                "environment": "sandbox"
            }
        )

    try:
        # Renew/update the subscription
        request = VerifyPurchaseRequest(
            transaction_id="txn_renewal_456",
            original_transaction_id="orig_existing_123",  # Same original transaction
            product_id="com.homeboundapp.homebound.plus.monthly",
            purchase_date=datetime.now(UTC).isoformat(),
            expires_date=new_expires.isoformat(),
            environment="sandbox",
            is_family_shared=False,
            auto_renew=True,
            is_trial=False
        )

        response = verify_purchase(request, user_id=user_id)

        assert response.ok is True
        assert response.tier == "plus"

        # Verify only one subscription record exists (updated, not duplicated)
        with db.engine.begin() as conn:
            subs = conn.execute(
                sqlalchemy.text("SELECT COUNT(*) as count FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert subs.count == 1

            # Verify expiration was updated
            sub = conn.execute(
                sqlalchemy.text("SELECT expires_date FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            # New expires should be later than original
            assert sub.expires_date > original_expires
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_verify_purchase_expired():
    """Expired purchase sets tier to 'free'"""
    test_email = "verify-expired@homeboundapp.com"
    # Already expired
    expires_at = datetime.now(UTC) - timedelta(days=1)

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Verify",
                "last_name": "Expired",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        request = VerifyPurchaseRequest(
            transaction_id="txn_expired_123",
            original_transaction_id="orig_expired_123",
            product_id="com.homeboundapp.homebound.plus.monthly",
            purchase_date=(datetime.now(UTC) - timedelta(days=31)).isoformat(),
            expires_date=expires_at.isoformat(),
            environment="sandbox",
            is_family_shared=False,
            auto_renew=False,
            is_trial=False
        )

        response = verify_purchase(request, user_id=user_id)

        assert response.ok is True
        assert response.tier == "free", "Expired subscription should set tier to 'free'"

        # Verify user tier is free
        with db.engine.begin() as conn:
            user = conn.execute(
                sqlalchemy.text("SELECT subscription_tier FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert user.subscription_tier == "free"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_verify_purchase_trial():
    """Trial purchase sets is_trial flag correctly"""
    test_email = "verify-trial@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=7)  # 7-day trial

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Verify",
                "last_name": "Trial",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        request = VerifyPurchaseRequest(
            transaction_id="txn_trial_123",
            original_transaction_id="orig_trial_123",
            product_id="com.homeboundapp.homebound.plus.monthly",
            purchase_date=datetime.now(UTC).isoformat(),
            expires_date=expires_at.isoformat(),
            environment="sandbox",
            is_family_shared=False,
            auto_renew=True,
            is_trial=True  # This is a trial
        )

        response = verify_purchase(request, user_id=user_id)

        assert response.ok is True
        assert response.tier == "plus"

        # Verify is_trial flag was set
        with db.engine.begin() as conn:
            sub = conn.execute(
                sqlalchemy.text("SELECT is_trial FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert sub.is_trial is True
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_verify_purchase_cancelled():
    """Cancelled subscription (auto_renew=false) sets status to 'cancelled'"""
    test_email = "verify-cancelled@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=15)  # Still has access time

    with db.engine.begin() as conn:
        # Clean up
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Verify",
                "last_name": "Cancelled",
                "age": 28,
                "tier": "plus"
            }
        )
        user_id = result.fetchone()[0]

    try:
        request = VerifyPurchaseRequest(
            transaction_id="txn_cancelled_123",
            original_transaction_id="orig_cancelled_123",
            product_id="com.homeboundapp.homebound.plus.monthly",
            purchase_date=datetime.now(UTC).isoformat(),
            expires_date=expires_at.isoformat(),
            environment="sandbox",
            is_family_shared=False,
            auto_renew=False,  # Cancelled
            is_trial=False
        )

        response = verify_purchase(request, user_id=user_id)

        assert response.ok is True
        # Still has access until expiration
        assert response.tier == "plus"

        # Verify status was set to cancelled
        with db.engine.begin() as conn:
            sub = conn.execute(
                sqlalchemy.text("SELECT status, auto_renew_status FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert sub.status == "cancelled"
            assert sub.auto_renew_status is False
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Status Endpoint Tests ====================

def test_status_endpoint_free_user():
    """Status returns correct data for free user"""
    test_email = "status-free@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Status",
                "last_name": "Free",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        status = get_subscription_status(user_id=user_id)

        assert status.tier == "free"
        assert status.is_active is False
        assert status.expires_at is None
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_status_endpoint_plus_user():
    """Status returns correct data including trial/auto_renew flags"""
    test_email = "status-plus@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Status",
                "last_name": "Plus",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

        # Create subscription record
        conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO subscriptions (user_id, original_transaction_id, product_id, purchase_date, expires_date, status, auto_renew_status, is_trial, environment)
                VALUES (:user_id, :orig_txn, :product_id, :purchase_date, :expires_date, :status, :auto_renew, :is_trial, :environment)
                """
            ),
            {
                "user_id": user_id,
                "orig_txn": "orig_status_plus_123",
                "product_id": "com.homeboundapp.homebound.plus.monthly",
                "purchase_date": datetime.now(UTC),
                "expires_date": expires_at,
                "status": "active",
                "auto_renew": True,
                "is_trial": True,
                "environment": "sandbox"
            }
        )

    try:
        status = get_subscription_status(user_id=user_id)

        assert status.tier == "plus"
        assert status.is_active is True
        assert status.expires_at is not None
        assert status.auto_renew is True
        assert status.is_trial is True
        assert status.product_id == "com.homeboundapp.homebound.plus.monthly"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Feature Limits Endpoint Tests ====================

def test_limits_endpoint_returns_correct_tier():
    """GET /api/v1/subscriptions/limits returns correct data"""
    test_email = "limits-endpoint@homeboundapp.com"

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
                "first_name": "Limits",
                "last_name": "Endpoint",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        limits = get_feature_limits(user_id=user_id)

        assert limits.tier == "free"
        assert limits.is_premium is False
        assert limits.contacts_per_trip == 2
        assert limits.saved_trips_limit == 0
        assert limits.history_days == 30
        assert limits.widgets_enabled is False
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_limits_endpoint_plus_user():
    """Limits endpoint returns premium limits for plus user"""
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
                "first_name": "Limits",
                "last_name": "Plus",
                "age": 30,
                "tier": "plus",
                "expires_at": expires_at
            }
        )
        user_id = result.fetchone()[0]

    try:
        limits = get_feature_limits(user_id=user_id)

        assert limits.tier == "plus"
        assert limits.is_premium is True
        assert limits.contacts_per_trip == 5
        assert limits.saved_trips_limit == 10
        assert limits.history_days is None  # Unlimited
        assert limits.widgets_enabled is True
        assert limits.live_activity_enabled is True
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Restore Tests ====================

def test_restore_with_valid_subscription():
    """Restore finds and activates valid subscription"""
    test_email = "restore-valid@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=15)

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user marked as free (but has valid subscription)
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
                "first_name": "Restore",
                "last_name": "Valid",
                "age": 28,
                "tier": "free"  # Marked as free
            }
        )
        user_id = result.fetchone()[0]

        # But has a valid subscription in the table
        conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO subscriptions (user_id, original_transaction_id, product_id, purchase_date, expires_date, status, auto_renew_status, is_trial, environment)
                VALUES (:user_id, :orig_txn, :product_id, :purchase_date, :expires_date, :status, :auto_renew, :is_trial, :environment)
                """
            ),
            {
                "user_id": user_id,
                "orig_txn": "orig_restore_valid_123",
                "product_id": "com.homeboundapp.homebound.plus.monthly",
                "purchase_date": datetime.now(UTC) - timedelta(days=15),
                "expires_date": expires_at,
                "status": "active",
                "auto_renew": True,
                "is_trial": False,
                "environment": "sandbox"
            }
        )

    try:
        response = restore_purchases(user_id=user_id)

        assert response["restored"] is True

        # Verify tier was updated
        with db.engine.begin() as conn:
            user = conn.execute(
                sqlalchemy.text("SELECT subscription_tier FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert user.subscription_tier == "plus"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_restore_with_expired_subscription():
    """Restore with expired subscription returns no restoration"""
    test_email = "restore-expired@homeboundapp.com"
    expires_at = datetime.now(UTC) - timedelta(days=5)  # Expired

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Restore",
                "last_name": "Expired",
                "age": 30,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

        # Expired subscription
        conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO subscriptions (user_id, original_transaction_id, product_id, purchase_date, expires_date, status, auto_renew_status, is_trial, environment)
                VALUES (:user_id, :orig_txn, :product_id, :purchase_date, :expires_date, :status, :auto_renew, :is_trial, :environment)
                """
            ),
            {
                "user_id": user_id,
                "orig_txn": "orig_restore_expired_123",
                "product_id": "com.homeboundapp.homebound.plus.monthly",
                "purchase_date": datetime.now(UTC) - timedelta(days=35),
                "expires_date": expires_at,
                "status": "cancelled",
                "auto_renew": False,
                "is_trial": False,
                "environment": "sandbox"
            }
        )

    try:
        response = restore_purchases(user_id=user_id)

        assert response["restored"] is False

        # Tier should still be free
        with db.engine.begin() as conn:
            user = conn.execute(
                sqlalchemy.text("SELECT subscription_tier FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert user.subscription_tier == "free"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_restore_with_cancelled_but_valid():
    """Cancelled but not expired subscription can be restored"""
    test_email = "restore-cancelled@homeboundapp.com"
    expires_at = datetime.now(UTC) + timedelta(days=10)  # Still valid

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Restore",
                "last_name": "Cancelled",
                "age": 27,
                "tier": "free"  # Marked as free
            }
        )
        user_id = result.fetchone()[0]

        # Cancelled but not expired subscription
        conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO subscriptions (user_id, original_transaction_id, product_id, purchase_date, expires_date, status, auto_renew_status, is_trial, environment)
                VALUES (:user_id, :orig_txn, :product_id, :purchase_date, :expires_date, :status, :auto_renew, :is_trial, :environment)
                """
            ),
            {
                "user_id": user_id,
                "orig_txn": "orig_restore_cancelled_123",
                "product_id": "com.homeboundapp.homebound.plus.monthly",
                "purchase_date": datetime.now(UTC) - timedelta(days=20),
                "expires_date": expires_at,
                "status": "cancelled",  # Cancelled
                "auto_renew": False,
                "is_trial": False,
                "environment": "sandbox"
            }
        )

    try:
        response = restore_purchases(user_id=user_id)

        # Should still be restored because it hasn't expired yet
        assert response["restored"] is True

        # Tier should be plus
        with db.engine.begin() as conn:
            user = conn.execute(
                sqlalchemy.text("SELECT subscription_tier FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            assert user.subscription_tier == "plus"
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_restore_no_subscription():
    """Restore with no subscription history returns no restoration"""
    test_email = "restore-none@homeboundapp.com"

    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Restore",
                "last_name": "None",
                "age": 25,
                "tier": "free"
            }
        )
        user_id = result.fetchone()[0]

    try:
        response = restore_purchases(user_id=user_id)

        assert response["restored"] is False
    finally:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )
