"""Tests for checkin API endpoints"""
import pytest
from datetime import datetime, timezone, timedelta
from src import database as db
import sqlalchemy
from src.api.checkin import (
    CheckinResponse,
    checkin_with_token,
    checkout_with_token
)
from fastapi import HTTPException, BackgroundTasks


def setup_test_trip_with_tokens():
    """Helper function to set up test trip with tokens"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up - NULL out last_checkin, then delete events, then trips
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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Checkin",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

        # Create contact
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "name": "Emergency Contact",
                "email": "test@homeboundapp.com"
            }
        )
        contact_id = result.fetchone()[0]

        # Get Hiking activity ID
        activity_result = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()
        activity_id = activity_result[0]

        # Create trip with tokens
        now = datetime.now(timezone.utc)
        checkin_token = "test_checkin_token_123"
        checkout_token = "test_checkout_token_456"

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, status, contact1,
                    created_at, checkin_token, checkout_token
                )
                VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, 'active', :contact1,
                    :created_at, :checkin_token, :checkout_token
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": "Test Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 30,
                "location_text": "Mountain Trail",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194,
                "contact1": contact_id,
                "created_at": now.isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token
            }
        )
        trip_id = result.fetchone()[0]

    return user_id, trip_id, checkin_token, checkout_token


def cleanup_test_data(user_id):
    """Helper function to clean up test data"""
    with db.engine.begin() as connection:
        # NULL out last_checkin to break circular reference, then delete events, then trips
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


def test_checkin_with_valid_token():
    """Test checking in with a valid token"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    # Check in
    background_tasks = BackgroundTasks()
    response = checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

    assert isinstance(response, CheckinResponse)
    assert response.ok is True
    assert "checked in" in response.message.lower()

    # Verify event was created
    with db.engine.begin() as connection:
        events = connection.execute(
            sqlalchemy.text(
                """
                SELECT what FROM events
                WHERE trip_id = :trip_id AND what = 'checkin'
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        assert len(events) >= 1

        # Verify last_checkin was updated
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT last_checkin FROM trips WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        assert trip.last_checkin is not None

    cleanup_test_data(user_id)


def test_checkin_with_invalid_token():
    """Test checking in with an invalid token"""
    background_tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        checkin_with_token("invalid_token_12345", background_tasks, lat=None, lon=None)

    assert exc_info.value.status_code == 404
    assert "invalid" in exc_info.value.detail.lower()


def test_checkout_with_valid_token():
    """Test checking out with a valid token"""
    user_id, trip_id, _, checkout_token = setup_test_trip_with_tokens()

    # Check out
    background_tasks = BackgroundTasks()
    response = checkout_with_token(checkout_token, background_tasks)

    assert isinstance(response, CheckinResponse)
    assert response.ok is True
    assert "completed" in response.message.lower()

    # Verify trip is completed
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT status, completed_at FROM trips WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        assert trip.status == "completed"
        assert trip.completed_at is not None

        # Verify event was created
        events = connection.execute(
            sqlalchemy.text(
                """
                SELECT what FROM events
                WHERE trip_id = :trip_id AND what = 'complete'
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        assert len(events) >= 1

    cleanup_test_data(user_id)


def test_checkout_with_invalid_token():
    """Test checking out with an invalid token"""
    background_tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        checkout_with_token("invalid_checkout_token", background_tasks)

    assert exc_info.value.status_code == 404
    assert "invalid" in exc_info.value.detail.lower()


def test_checkin_after_checkout():
    """Test that checking in fails after trip is checked out"""
    user_id, _, checkin_token, checkout_token = setup_test_trip_with_tokens()

    # Check out first
    background_tasks = BackgroundTasks()
    checkout_with_token(checkout_token, background_tasks)

    # Try to check in after checkout
    with pytest.raises(HTTPException) as exc_info:
        checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

    assert exc_info.value.status_code == 404

    cleanup_test_data(user_id)


def test_multiple_checkins():
    """Test multiple check-ins on the same trip"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    background_tasks = BackgroundTasks()

    # First check-in
    response1 = checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)
    assert response1.ok is True

    # Second check-in
    response2 = checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)
    assert response2.ok is True

    # Verify multiple events were created
    with db.engine.begin() as connection:
        events = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count FROM events
                WHERE trip_id = :trip_id AND what = 'checkin'
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        assert events.count >= 2

    cleanup_test_data(user_id)


def test_checkout_already_completed_trip():
    """Test checking out a trip that's already completed"""
    user_id, _, _, checkout_token = setup_test_trip_with_tokens()

    # First checkout
    background_tasks = BackgroundTasks()
    checkout_with_token(checkout_token, background_tasks)

    # Try to checkout again
    with pytest.raises(HTTPException) as exc_info:
        checkout_with_token(checkout_token, background_tasks)

    assert exc_info.value.status_code == 404

    cleanup_test_data(user_id)
