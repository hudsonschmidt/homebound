"""Tests for Live Activity token API endpoints"""
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy
from fastapi import HTTPException

from src import database as db
from src.api.live_activity_tokens import (
    LiveActivityTokenRegister,
    LiveActivityTokenResponse,
    delete_live_activity_token,
    get_live_activity_token,
    register_live_activity_token,
)


def setup_test_user_and_trip():
    """Helper function to create a test user and trip"""
    test_email = "liveactivity_test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up any existing data
        connection.execute(
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "LiveActivity",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

        # Get Hiking activity ID
        activity_result = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()
        activity_id = activity_result[0]

        # Create trip
        now = datetime.now(UTC)
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, status, created_at,
                    checkin_token, checkout_token
                )
                VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, 'active', :created_at,
                    :checkin_token, :checkout_token
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": "Test Trip for Live Activity",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 30,
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194,
                "created_at": now.isoformat(),
                "checkin_token": "la_test_checkin",
                "checkout_token": "la_test_checkout"
            }
        )
        trip_id = result.fetchone()[0]

    return user_id, trip_id


def cleanup_test_data(user_id):
    """Helper function to clean up test data"""
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


# ============================================================================
# Registration Tests
# ============================================================================

def test_register_live_activity_token():
    """Test registering a new Live Activity token"""
    user_id, trip_id = setup_test_user_and_trip()

    token_data = LiveActivityTokenRegister(
        token="test_la_token_abc123",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )

    response = register_live_activity_token(token_data, user_id=user_id)

    assert isinstance(response, LiveActivityTokenResponse)
    assert response.trip_id == trip_id
    assert response.token == "test_la_token_abc123"
    assert response.bundle_id == "com.homeboundapp.Homebound"
    assert response.env == "development"

    cleanup_test_data(user_id)


def test_register_live_activity_token_upsert():
    """Test that registering the same trip_id updates the existing token"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register first token
    token_data1 = LiveActivityTokenRegister(
        token="first_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )
    response1 = register_live_activity_token(token_data1, user_id=user_id)

    # Register second token for same trip (should update, not create new)
    token_data2 = LiveActivityTokenRegister(
        token="second_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="production"
    )
    response2 = register_live_activity_token(token_data2, user_id=user_id)

    # Should be the same ID (upsert behavior)
    assert response1.id == response2.id
    # Token should be updated
    assert response2.token == "second_token"
    # Env should be updated
    assert response2.env == "production"

    cleanup_test_data(user_id)


def test_register_live_activity_token_invalid_env():
    """Test registering with invalid environment"""
    user_id, trip_id = setup_test_user_and_trip()

    token_data = LiveActivityTokenRegister(
        token="test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="invalid_env"
    )

    with pytest.raises(HTTPException) as exc_info:
        register_live_activity_token(token_data, user_id=user_id)

    assert exc_info.value.status_code == 400
    assert "env" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_register_live_activity_token_trip_not_found():
    """Test registering token for a trip that doesn't exist"""
    user_id, trip_id = setup_test_user_and_trip()

    token_data = LiveActivityTokenRegister(
        token="test_token",
        trip_id=999999,  # Non-existent trip
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )

    with pytest.raises(HTTPException) as exc_info:
        register_live_activity_token(token_data, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "trip" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_register_live_activity_token_wrong_user():
    """Test that user can't register token for another user's trip"""
    user_id, trip_id = setup_test_user_and_trip()

    # Create second user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": "other_user@homeboundapp.com",
                "first_name": "Other",
                "last_name": "User",
                "age": 25
            }
        )
        other_user_id = result.fetchone()[0]

    # Try to register token for first user's trip using second user's ID
    token_data = LiveActivityTokenRegister(
        token="test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )

    with pytest.raises(HTTPException) as exc_info:
        register_live_activity_token(token_data, user_id=other_user_id)

    assert exc_info.value.status_code == 404

    # Clean up other user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": other_user_id}
        )

    cleanup_test_data(user_id)


# ============================================================================
# Deletion Tests
# ============================================================================

def test_delete_live_activity_token():
    """Test deleting a Live Activity token"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register token first
    token_data = LiveActivityTokenRegister(
        token="delete_test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )
    register_live_activity_token(token_data, user_id=user_id)

    # Delete token
    response = delete_live_activity_token(trip_id, user_id=user_id)

    assert response["ok"] is True

    # Verify it's deleted
    with pytest.raises(HTTPException) as exc_info:
        get_live_activity_token(trip_id, user_id=user_id)

    assert exc_info.value.status_code == 404

    cleanup_test_data(user_id)


def test_delete_live_activity_token_not_found():
    """Test deleting a token that doesn't exist returns graceful response"""
    user_id, trip_id = setup_test_user_and_trip()

    # Delete without registering first (should not error)
    response = delete_live_activity_token(trip_id, user_id=user_id)

    # Should return OK (idempotent behavior)
    assert response["ok"] is True

    cleanup_test_data(user_id)


def test_delete_live_activity_token_wrong_user():
    """Test that user can't delete another user's token"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register token
    token_data = LiveActivityTokenRegister(
        token="test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )
    register_live_activity_token(token_data, user_id=user_id)

    # Create second user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": "other_user2@homeboundapp.com",
                "first_name": "Other",
                "last_name": "User",
                "age": 25
            }
        )
        other_user_id = result.fetchone()[0]

    # Try to delete with wrong user - should return "not found" (graceful)
    response = delete_live_activity_token(trip_id, user_id=other_user_id)
    # Still returns OK but with "not found" message
    assert response["ok"] is True

    # Verify original token still exists
    token = get_live_activity_token(trip_id, user_id=user_id)
    assert token.token == "test_token"

    # Clean up other user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": other_user_id}
        )

    cleanup_test_data(user_id)


# ============================================================================
# Get Token Tests
# ============================================================================

def test_get_live_activity_token():
    """Test retrieving a Live Activity token"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register token first
    token_data = LiveActivityTokenRegister(
        token="get_test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="production"
    )
    register_live_activity_token(token_data, user_id=user_id)

    # Get token
    response = get_live_activity_token(trip_id, user_id=user_id)

    assert isinstance(response, LiveActivityTokenResponse)
    assert response.trip_id == trip_id
    assert response.token == "get_test_token"
    assert response.env == "production"

    cleanup_test_data(user_id)


def test_get_live_activity_token_not_found():
    """Test getting a token that doesn't exist"""
    user_id, trip_id = setup_test_user_and_trip()

    with pytest.raises(HTTPException) as exc_info:
        get_live_activity_token(trip_id, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_get_live_activity_token_wrong_user():
    """Test that user can't get another user's token"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register token
    token_data = LiveActivityTokenRegister(
        token="test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )
    register_live_activity_token(token_data, user_id=user_id)

    # Create second user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": "other_user3@homeboundapp.com",
                "first_name": "Other",
                "last_name": "User",
                "age": 25
            }
        )
        other_user_id = result.fetchone()[0]

    # Try to get with wrong user
    with pytest.raises(HTTPException) as exc_info:
        get_live_activity_token(trip_id, user_id=other_user_id)

    assert exc_info.value.status_code == 404

    # Clean up other user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": other_user_id}
        )

    cleanup_test_data(user_id)


# ============================================================================
# Cascade Delete Tests
# ============================================================================

def test_token_deleted_when_trip_deleted():
    """Test that Live Activity token is deleted when trip is deleted (CASCADE)"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register token
    token_data = LiveActivityTokenRegister(
        token="cascade_test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )
    register_live_activity_token(token_data, user_id=user_id)

    # Verify token exists
    token = get_live_activity_token(trip_id, user_id=user_id)
    assert token is not None

    # Delete trip (should cascade delete token)
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE trip_id = :trip_id"),
            {"trip_id": trip_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )

    # Verify token is gone
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text("SELECT id FROM live_activity_tokens WHERE trip_id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()
        assert result is None

    cleanup_test_data(user_id)


def test_token_deleted_when_user_deleted():
    """Test that Live Activity token is deleted when user is deleted (CASCADE)"""
    user_id, trip_id = setup_test_user_and_trip()

    # Register token
    token_data = LiveActivityTokenRegister(
        token="user_cascade_test_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )
    register_live_activity_token(token_data, user_id=user_id)

    # Capture the token ID
    token = get_live_activity_token(trip_id, user_id=user_id)
    token_id = token.id

    # Delete user (should cascade delete token via trip or directly)
    cleanup_test_data(user_id)

    # Verify token is gone
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text("SELECT id FROM live_activity_tokens WHERE id = :token_id"),
            {"token_id": token_id}
        ).fetchone()
        assert result is None


# ============================================================================
# Edge Cases
# ============================================================================

def test_register_token_with_production_env():
    """Test registering token with production environment"""
    user_id, trip_id = setup_test_user_and_trip()

    token_data = LiveActivityTokenRegister(
        token="prod_token",
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="production"
    )

    response = register_live_activity_token(token_data, user_id=user_id)

    assert response.env == "production"

    cleanup_test_data(user_id)


def test_register_token_with_long_token():
    """Test registering token with maximum length token (256 chars)"""
    user_id, trip_id = setup_test_user_and_trip()

    long_token = "a" * 256

    token_data = LiveActivityTokenRegister(
        token=long_token,
        trip_id=trip_id,
        bundle_id="com.homeboundapp.Homebound",
        env="development"
    )

    response = register_live_activity_token(token_data, user_id=user_id)

    assert response.token == long_token

    cleanup_test_data(user_id)


def test_multiple_trips_multiple_tokens():
    """Test that each trip can have its own token"""
    user_id, trip_id1 = setup_test_user_and_trip()

    # Create second trip
    with db.engine.begin() as connection:
        activity_result = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Driving'")
        ).fetchone()
        activity_id = activity_result[0]

        now = datetime.now(UTC)
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, status, created_at,
                    checkin_token, checkout_token
                )
                VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, 'active', :created_at,
                    :checkin_token, :checkout_token
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": "Second Test Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=1)).isoformat(),
                "grace_min": 15,
                "location_text": "Another Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194,
                "created_at": now.isoformat(),
                "checkin_token": "second_checkin",
                "checkout_token": "second_checkout"
            }
        )
        trip_id2 = result.fetchone()[0]

    # Register tokens for both trips
    register_live_activity_token(
        LiveActivityTokenRegister(
            token="trip1_token",
            trip_id=trip_id1,
            bundle_id="com.homeboundapp.Homebound",
            env="development"
        ),
        user_id=user_id
    )

    register_live_activity_token(
        LiveActivityTokenRegister(
            token="trip2_token",
            trip_id=trip_id2,
            bundle_id="com.homeboundapp.Homebound",
            env="development"
        ),
        user_id=user_id
    )

    # Verify both tokens exist and are different
    token1 = get_live_activity_token(trip_id1, user_id=user_id)
    token2 = get_live_activity_token(trip_id2, user_id=user_id)

    assert token1.token == "trip1_token"
    assert token2.token == "trip2_token"
    assert token1.trip_id != token2.trip_id

    cleanup_test_data(user_id)
