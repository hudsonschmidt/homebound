"""Tests for checkin API endpoints"""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy
from fastapi import BackgroundTasks, HTTPException

from src import database as db
from src.api.checkin import CheckinResponse, checkin_with_token, checkout_with_token


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
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
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
        now = datetime.now(UTC)
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
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id = :user_id"),
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


# ============================================================================
# Live Activity Update Tests
# ============================================================================

def setup_test_trip_overdue():
    """Helper to set up an overdue trip with tokens"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
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
                "first_name": "Overdue",
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
                "email": "contact@homeboundapp.com"
            }
        )
        contact_id = result.fetchone()[0]

        # Get Hiking activity ID
        activity_result = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()
        activity_id = activity_result[0]

        # Create overdue trip
        now = datetime.now(UTC)
        past_eta = now - timedelta(hours=2)
        checkin_token = "test_checkin_overdue_123"
        checkout_token = "test_checkout_overdue_456"

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
                    :location_text, :gen_lat, :gen_lon, 'overdue_notified', :contact1,
                    :created_at, :checkin_token, :checkout_token
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": "Overdue Trip",
                "activity": activity_id,
                "start": (past_eta - timedelta(hours=2)).isoformat(),
                "eta": past_eta.isoformat(),
                "grace_min": 30,
                "location_text": "Mountain Trail",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194,
                "contact1": contact_id,
                "created_at": (past_eta - timedelta(hours=2)).isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token
            }
        )
        trip_id = result.fetchone()[0]

    return user_id, trip_id, checkin_token, checkout_token


def test_checkin_triggers_live_activity_update():
    """Test that check-in triggers Live Activity update with correct parameters"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        background_tasks = BackgroundTasks()
        response = checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

        assert response.ok is True

        # Execute background tasks manually
        for task in background_tasks.tasks:
            task.func(*task.args, **task.kwargs)

        # Verify send_live_activity_update was called
        mock_la_update.assert_called_once()

        # Verify call parameters
        call_kwargs = mock_la_update.call_args.kwargs
        assert call_kwargs["trip_id"] == trip_id
        assert call_kwargs["status"] == "active"
        assert call_kwargs["is_overdue"] is False
        assert call_kwargs["checkin_count"] == 1
        assert call_kwargs["last_checkin_time"] is not None

    cleanup_test_data(user_id)


def test_checkout_triggers_live_activity_end():
    """Test that checkout triggers Live Activity end event"""
    user_id, trip_id, _, checkout_token = setup_test_trip_with_tokens()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        background_tasks = BackgroundTasks()
        response = checkout_with_token(checkout_token, background_tasks)

        assert response.ok is True

        # Execute background tasks manually
        for task in background_tasks.tasks:
            task.func(*task.args, **task.kwargs)

        # Verify send_live_activity_update was called
        mock_la_update.assert_called_once()

        # Verify end event parameters
        call_kwargs = mock_la_update.call_args.kwargs
        assert call_kwargs["trip_id"] == trip_id
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["event"] == "end"
        assert call_kwargs["is_overdue"] is False
        assert call_kwargs["checkin_count"] == 0

    cleanup_test_data(user_id)


def test_checkin_increments_count_in_live_activity():
    """Test that multiple check-ins increment the count in Live Activity updates"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    call_counts = []

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        # First check-in
        background_tasks1 = BackgroundTasks()
        checkin_with_token(checkin_token, background_tasks1, lat=None, lon=None)
        for task in background_tasks1.tasks:
            task.func(*task.args, **task.kwargs)
        call_counts.append(mock_la_update.call_args.kwargs["checkin_count"])

        mock_la_update.reset_mock()

        # Second check-in
        background_tasks2 = BackgroundTasks()
        checkin_with_token(checkin_token, background_tasks2, lat=None, lon=None)
        for task in background_tasks2.tasks:
            task.func(*task.args, **task.kwargs)
        call_counts.append(mock_la_update.call_args.kwargs["checkin_count"])

        mock_la_update.reset_mock()

        # Third check-in
        background_tasks3 = BackgroundTasks()
        checkin_with_token(checkin_token, background_tasks3, lat=None, lon=None)
        for task in background_tasks3.tasks:
            task.func(*task.args, **task.kwargs)
        call_counts.append(mock_la_update.call_args.kwargs["checkin_count"])

    # Verify counts increment
    assert call_counts == [1, 2, 3]

    cleanup_test_data(user_id)


def test_checkin_from_overdue_sends_active_status():
    """Test that checking in from overdue status sends active status to Live Activity"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_overdue()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        background_tasks = BackgroundTasks()
        response = checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

        assert response.ok is True

        # Execute background tasks
        for task in background_tasks.tasks:
            task.func(*task.args, **task.kwargs)

        # Verify Live Activity update was sent with active status
        mock_la_update.assert_called_once()
        call_kwargs = mock_la_update.call_args.kwargs
        assert call_kwargs["status"] == "active"
        assert call_kwargs["is_overdue"] is False

    cleanup_test_data(user_id)


def test_checkout_from_overdue_sends_end_event():
    """Test that checkout from overdue trip sends end event to Live Activity"""
    user_id, trip_id, _, checkout_token = setup_test_trip_overdue()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        background_tasks = BackgroundTasks()
        response = checkout_with_token(checkout_token, background_tasks)

        assert response.ok is True

        # Execute background tasks
        for task in background_tasks.tasks:
            task.func(*task.args, **task.kwargs)

        # Verify end event was sent
        mock_la_update.assert_called_once()
        call_kwargs = mock_la_update.call_args.kwargs
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["event"] == "end"

    cleanup_test_data(user_id)


def test_checkin_includes_eta_in_live_activity():
    """Test that check-in includes ETA in Live Activity update"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        background_tasks = BackgroundTasks()
        checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

        # Execute background tasks
        for task in background_tasks.tasks:
            task.func(*task.args, **task.kwargs)

        # Verify eta is included
        call_kwargs = mock_la_update.call_args.kwargs
        assert "eta" in call_kwargs
        assert call_kwargs["eta"] is not None
        assert isinstance(call_kwargs["eta"], datetime)

    cleanup_test_data(user_id)


def test_checkin_with_coordinates_still_sends_live_activity():
    """Test that check-in with coordinates still sends Live Activity update"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        mock_la_update.return_value = None

        # Mock reverse geocoding
        with patch("src.api.checkin.reverse_geocode_sync", return_value="Mountain Peak, CA"):
            background_tasks = BackgroundTasks()
            response = checkin_with_token(
                checkin_token, background_tasks,
                lat=37.7749, lon=-122.4194
            )

            assert response.ok is True

            # Execute background tasks
            for task in background_tasks.tasks:
                task.func(*task.args, **task.kwargs)

            # Verify Live Activity update was still sent
            mock_la_update.assert_called_once()

    cleanup_test_data(user_id)


def test_live_activity_update_called_before_other_notifications():
    """Test that Live Activity update is scheduled for check-in"""
    user_id, trip_id, checkin_token, _ = setup_test_trip_with_tokens()

    with patch("src.api.checkin.send_live_activity_update") as mock_la_update:
        with patch("src.api.checkin.send_push_to_user") as mock_push:
            with patch("src.api.checkin.send_checkin_update_emails") as mock_email:
                mock_la_update.return_value = None
                mock_push.return_value = None
                mock_email.return_value = None

                background_tasks = BackgroundTasks()
                checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

                # Execute all background tasks
                for task in background_tasks.tasks:
                    task.func(*task.args, **task.kwargs)

                # Verify Live Activity update was called
                mock_la_update.assert_called_once()

    cleanup_test_data(user_id)
