"""Tests for scheduler notification logic"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import sqlalchemy

from src import database as db


@pytest.fixture
def test_user_with_trip():
    """Create a test user with a contact for scheduler tests"""
    test_email = "scheduler_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up any existing test data
        conn.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, 'Scheduler', 'Test', 30)
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create a contact
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, 'Test Contact', 'contact@test.com')
                RETURNING id
            """),
            {"user_id": user_id}
        )
        contact_id = result.fetchone()[0]

        # Get an activity ID
        activity = conn.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

    yield {"user_id": user_id, "email": test_email, "activity_id": activity_id, "contact_id": contact_id}

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def create_trip(conn, user_id, activity_id, contact_id, status, eta_offset_minutes=0, grace_min=30):
    """Helper to create a trip with specified parameters"""
    now = datetime.utcnow()
    start = now - timedelta(hours=1)
    eta = now + timedelta(minutes=eta_offset_minutes)

    result = conn.execute(
        sqlalchemy.text("""
            INSERT INTO trips (
                user_id, activity, title, status, start, eta, grace_min, location_text,
                gen_lat, gen_lon, contact1, created_at,
                notified_starting_soon, notified_trip_started, notified_approaching_eta, notified_eta_reached
            )
            VALUES (
                :user_id, :activity, 'Test Trip', :status, :start, :eta, :grace_min, 'Test Location',
                37.7749, -122.4194, :contact1, NOW(),
                true, true, true, true
            )
            RETURNING id
        """),
        {
            "user_id": user_id,
            "activity": activity_id,
            "contact1": contact_id,
            "status": status,
            "start": start.isoformat(),
            "eta": eta.isoformat(),
            "grace_min": grace_min
        }
    )
    return result.fetchone()[0]


@pytest.mark.asyncio
async def test_grace_period_warning_skipped_when_active(test_user_with_trip):
    """Test that grace period warnings are not sent for active trips (only overdue)"""
    user_id = test_user_with_trip["user_id"]
    activity_id = test_user_with_trip["activity_id"]
    contact_id = test_user_with_trip["contact_id"]

    with db.engine.begin() as conn:
        # Create an active trip (not overdue)
        trip_id = create_trip(conn, user_id, activity_id, contact_id, "active", eta_offset_minutes=-10)

    mock_push = AsyncMock()

    with patch("src.services.scheduler.send_push_to_user", mock_push):
        from src.services.scheduler import check_push_notifications
        await check_push_notifications()

        # Should not send grace warning for active trips
        # Check if any calls were for "Urgent: Check In Now"
        grace_warning_calls = [
            call for call in mock_push.call_args_list
            if len(call[0]) >= 2 and call[0][1] == "Urgent: Check In Now"
        ]
        assert len(grace_warning_calls) == 0

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )


@pytest.mark.asyncio
async def test_grace_period_warning_skipped_when_completed(test_user_with_trip):
    """Test that grace period warnings are not sent for completed trips"""
    user_id = test_user_with_trip["user_id"]
    activity_id = test_user_with_trip["activity_id"]
    contact_id = test_user_with_trip["contact_id"]

    with db.engine.begin() as conn:
        # Create a completed trip with past ETA
        trip_id = create_trip(conn, user_id, activity_id, contact_id, "completed", eta_offset_minutes=-30)

    mock_push = AsyncMock()

    with patch("src.services.scheduler.send_push_to_user", mock_push):
        from src.services.scheduler import check_push_notifications
        await check_push_notifications()

        # Should not send grace warning for completed trips
        grace_warning_calls = [
            call for call in mock_push.call_args_list
            if len(call[0]) >= 2 and call[0][1] == "Urgent: Check In Now"
        ]
        assert len(grace_warning_calls) == 0

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )


@pytest.mark.asyncio
async def test_grace_period_warning_sent_when_overdue(test_user_with_trip):
    """Test that grace period warnings ARE sent for overdue trips"""
    user_id = test_user_with_trip["user_id"]
    activity_id = test_user_with_trip["activity_id"]
    contact_id = test_user_with_trip["contact_id"]

    with db.engine.begin() as conn:
        # Create an overdue trip with remaining grace period
        trip_id = create_trip(conn, user_id, activity_id, contact_id, "overdue", eta_offset_minutes=-10, grace_min=60)

    mock_push = AsyncMock()

    with patch("src.services.scheduler.send_push_to_user", mock_push):
        from src.services.scheduler import check_push_notifications
        await check_push_notifications()

        # Should send grace warning for overdue trips
        grace_warning_calls = [
            call for call in mock_push.call_args_list
            if len(call[0]) >= 2 and call[0][1] == "Urgent: Check In Now"
        ]
        assert len(grace_warning_calls) >= 1

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )


@pytest.mark.asyncio
async def test_grace_period_warning_skipped_when_overdue_notified(test_user_with_trip):
    """Test that grace period warnings are NOT sent for overdue_notified trips"""
    user_id = test_user_with_trip["user_id"]
    activity_id = test_user_with_trip["activity_id"]
    contact_id = test_user_with_trip["contact_id"]

    with db.engine.begin() as conn:
        # Create an overdue_notified trip (contacts already notified)
        trip_id = create_trip(conn, user_id, activity_id, contact_id, "overdue_notified", eta_offset_minutes=-60)

    mock_push = AsyncMock()

    with patch("src.services.scheduler.send_push_to_user", mock_push):
        from src.services.scheduler import check_push_notifications
        await check_push_notifications()

        # Should NOT send grace warning for overdue_notified trips
        grace_warning_calls = [
            call for call in mock_push.call_args_list
            if len(call[0]) >= 2 and call[0][1] == "Urgent: Check In Now"
        ]
        assert len(grace_warning_calls) == 0

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )


@pytest.mark.asyncio
async def test_starting_soon_notification_sets_flag(test_user_with_trip):
    """Test that starting soon notification sets the flag"""
    user_id = test_user_with_trip["user_id"]
    activity_id = test_user_with_trip["activity_id"]
    contact_id = test_user_with_trip["contact_id"]

    with db.engine.begin() as conn:
        now = datetime.utcnow()
        # Create a planned trip starting in 10 minutes
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO trips (
                    user_id, activity, title, status, start, eta, grace_min, location_text,
                    gen_lat, gen_lon, contact1, created_at,
                    notified_starting_soon, notified_trip_started, notified_approaching_eta, notified_eta_reached
                )
                VALUES (
                    :user_id, :activity, 'Starting Soon Trip', 'planned', :start, :eta, 30, 'Test Location',
                    37.7749, -122.4194, :contact1, NOW(),
                    false, false, false, false
                )
                RETURNING id
            """),
            {
                "user_id": user_id,
                "activity": activity_id,
                "contact1": contact_id,
                "start": (now + timedelta(minutes=10)).isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat()
            }
        )
        trip_id = result.fetchone()[0]

    mock_push = AsyncMock()

    with patch("src.services.scheduler.send_push_to_user", mock_push):
        from src.services.scheduler import check_push_notifications
        await check_push_notifications()

        # Verify flag was set
        with db.engine.begin() as conn:
            result = conn.execute(
                sqlalchemy.text("SELECT notified_starting_soon FROM trips WHERE id = :trip_id"),
                {"trip_id": trip_id}
            ).fetchone()
            assert result[0] is True

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )
