"""Tests for trips API endpoints"""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from fastapi import BackgroundTasks, HTTPException

from src import database as db
from src.api.trips import (
    TimelineEvent,
    TripCreate,
    TripResponse,
    TripUpdate,
    complete_trip,
    create_trip,
    delete_trip,
    get_active_trip,
    get_trip,
    get_trip_timeline,
    get_trips,
    update_trip,
)


def setup_test_user_and_contact():
    """Helper function to set up test user and contact"""
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
                "first_name": "Trip",
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

    return user_id, contact_id


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
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_create_trip():
    """Test creating a new trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Hiking Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        notes="Bring water",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert isinstance(trip, TripResponse)
    assert trip.title == "Hiking Trip"
    assert trip.activity.name == "Hiking"
    assert trip.grace_min == 30
    assert trip.location_text == "Mountain Trail"
    assert trip.gen_lat == 37.7749
    assert trip.gen_lon == -122.4194
    assert trip.notes == "Bring water"
    assert trip.status == "active"
    assert trip.contact1 == contact_id
    assert trip.checkin_token is not None
    assert trip.checkout_token is not None

    cleanup_test_data(user_id)


def test_create_trip_invalid_activity():
    """Test creating trip with non-existent activity"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Invalid Trip",
        activity="NonExistentActivity",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    with pytest.raises(HTTPException) as exc_info:
        create_trip(trip_data, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "activity" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_create_trip_invalid_contact():
    """Test creating trip with non-existent contact"""
    user_id, _ = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Invalid Contact Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=999999  # Non-existent contact
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    with pytest.raises(HTTPException) as exc_info:
        create_trip(trip_data, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "contact" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_get_trips():
    """Test retrieving all trips for a user"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create multiple trips
    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)

    create_trip(
        TripCreate(
            title="Trip 1",
            activity="Hiking",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            location_text="Trail 1",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    create_trip(
        TripCreate(
            title="Trip 2",
            activity="Biking",
            start=now,
            eta=now + timedelta(hours=1),
            grace_min=20,
            location_text="Bike Path",
            gen_lat=37.7850,
            gen_lon=-122.4300,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    # Get all trips
    trips = get_trips(user_id=user_id)

    assert len(trips) == 2
    assert all(isinstance(t, TripResponse) for t in trips)
    titles = [t.title for t in trips]
    assert "Trip 1" in titles
    assert "Trip 2" in titles

    cleanup_test_data(user_id)


def test_get_active_trip():
    """Test retrieving the active trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create active trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active Trip",
        activity="Running",
        start=now,
        eta=now + timedelta(hours=1),
        grace_min=15,
        location_text="Running Track",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    create_trip(trip_data, background_tasks, user_id=user_id)

    # Get active trip
    active = get_active_trip(user_id=user_id)

    assert active is not None
    assert isinstance(active, TripResponse)
    assert active.title == "Active Trip"
    assert active.status == "active"

    cleanup_test_data(user_id)


def test_get_active_trip_none():
    """Test retrieving active trip when none exists"""
    user_id, _ = setup_test_user_and_contact()

    active = get_active_trip(user_id=user_id)
    assert active is None

    cleanup_test_data(user_id)


def test_get_trip():
    """Test retrieving a specific trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip
    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)
    created = create_trip(
        TripCreate(
            title="Specific Trip",
            activity="Camping",
            start=now,
            eta=now + timedelta(hours=4),
            grace_min=60,
            location_text="Campground",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    # Get the trip
    trip = get_trip(created.id, user_id=user_id)

    assert trip.id == created.id
    assert trip.title == "Specific Trip"
    assert trip.activity.name == "Camping"

    cleanup_test_data(user_id)


def test_get_nonexistent_trip():
    """Test retrieving a trip that doesn't exist"""
    with pytest.raises(HTTPException) as exc_info:
        get_trip(999999, user_id=1)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_complete_trip():
    """Test completing a trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip
    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(
        TripCreate(
            title="Complete Me",
            activity="Driving",
            start=now,
            eta=now + timedelta(hours=1),
            grace_min=15,
            location_text="Highway",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    # Complete the trip
    result = complete_trip(trip.id, user_id=user_id)
    assert result["ok"] is True

    # Verify trip is completed
    completed = get_trip(trip.id, user_id=user_id)
    assert completed.status == "completed"
    assert completed.completed_at is not None

    cleanup_test_data(user_id)


def test_complete_already_completed_trip():
    """Test completing a trip that's already completed"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create and complete trip
    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(
        TripCreate(
            title="Already Complete",
            activity="Flying",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=120,
            location_text="Airport",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    complete_trip(trip.id, user_id=user_id)

    # Try to complete again
    with pytest.raises(HTTPException) as exc_info:
        complete_trip(trip.id, user_id=user_id)

    assert exc_info.value.status_code == 400
    assert "not active" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_delete_trip():
    """Test deleting a trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip
    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(
        TripCreate(
            title="Delete Me",
            activity="Climbing",
            start=now,
            eta=now + timedelta(hours=3),
            grace_min=45,
            location_text="Climbing Gym",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    # Delete the trip
    result = delete_trip(trip.id, user_id=user_id)
    assert result["ok"] is True

    # Verify trip is deleted
    with pytest.raises(HTTPException) as exc_info:
        get_trip(trip.id, user_id=user_id)

    assert exc_info.value.status_code == 404

    cleanup_test_data(user_id)


def test_delete_nonexistent_trip():
    """Test deleting a trip that doesn't exist"""
    with pytest.raises(HTTPException) as exc_info:
        delete_trip(999999, user_id=1)

    assert exc_info.value.status_code == 404


def test_get_trip_timeline():
    """Test retrieving trip timeline"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip
    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(
        TripCreate(
            title="Timeline Trip",
            activity="Sailing",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            location_text="Marina",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    # Add some events
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp)
                VALUES (:user_id, :trip_id, :what, :timestamp)
                """
            ),
            {
                "user_id": user_id,
                "trip_id": trip.id,
                "what": "started",
                "timestamp": now.isoformat()
            }
        )

    # Get timeline
    timeline = get_trip_timeline(trip.id, user_id=user_id)

    assert len(timeline) >= 1
    assert all(isinstance(e, TimelineEvent) for e in timeline)
    event_types = [e.kind for e in timeline]
    assert "started" in event_types

    cleanup_test_data(user_id)


def test_get_timeline_nonexistent_trip():
    """Test getting timeline for non-existent trip"""
    with pytest.raises(HTTPException) as exc_info:
        get_trip_timeline(999999, user_id=1)

    assert exc_info.value.status_code == 404


# ============================================================================
# UPDATE TRIP TESTS
# ============================================================================

def create_planned_trip(user_id: int, contact_id: int, title: str = "Planned Trip"):
    """Helper to create a trip with 'planned' status (future start time)"""
    future_start = datetime.now(UTC) + timedelta(hours=24)  # Start tomorrow
    future_eta = future_start + timedelta(hours=2)

    trip_data = TripCreate(
        title=title,
        activity="Hiking",
        start=future_start,
        eta=future_eta,
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        notes="Original notes",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "planned"  # Verify it's planned
    return trip


def test_update_trip_title():
    """Test updating a planned trip's title"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    # Update just the title
    update_data = TripUpdate(title="Updated Title")
    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.title == "Updated Title"
    assert updated.activity.name == "Hiking"  # Unchanged
    assert updated.notes == "Original notes"  # Unchanged

    cleanup_test_data(user_id)


def test_update_trip_all_fields():
    """Test updating all fields of a planned trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create a second contact for testing contact updates
    with db.engine.begin() as connection:
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
                "name": "Second Contact",
                "email": "second@example.com"
            }
        )
        contact2_id = result.fetchone()[0]

    trip = create_planned_trip(user_id, contact_id)

    # Update all fields
    new_start = datetime.now(UTC) + timedelta(hours=48)
    new_eta = new_start + timedelta(hours=3)

    update_data = TripUpdate(
        title="Completely Updated",
        activity="Biking",
        start=new_start,
        eta=new_eta,
        grace_min=60,
        location_text="New Location",
        gen_lat=40.7128,
        gen_lon=-74.0060,
        notes="Updated notes",
        contact1=contact2_id,
        timezone="America/New_York"
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.title == "Completely Updated"
    assert updated.activity.name == "Biking"
    assert updated.grace_min == 60
    assert updated.location_text == "New Location"
    assert updated.gen_lat == 40.7128
    assert updated.gen_lon == -74.0060
    assert updated.notes == "Updated notes"
    assert updated.contact1 == contact2_id

    cleanup_test_data(user_id)


def test_update_trip_partial_fields():
    """Test updating only some fields leaves others unchanged"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)
    original_lat = trip.gen_lat
    original_lon = trip.gen_lon

    # Update only grace_min and notes
    update_data = TripUpdate(
        grace_min=90,
        notes="Only notes updated"
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.grace_min == 90
    assert updated.notes == "Only notes updated"
    # These should be unchanged
    assert updated.title == "Planned Trip"
    assert updated.gen_lat == original_lat
    assert updated.gen_lon == original_lon
    assert updated.activity.name == "Hiking"

    cleanup_test_data(user_id)


def test_update_active_trip_fails():
    """Test that updating an active trip fails"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create an active trip (start time in the past)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active Trip",
        activity="Hiking",
        start=now,  # Starts now, so status will be 'active'
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "active"

    # Try to update
    update_data = TripUpdate(title="Should Fail")

    with pytest.raises(HTTPException) as exc_info:
        update_trip(trip.id, update_data, user_id=user_id)

    assert exc_info.value.status_code == 400
    assert "planned" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_update_completed_trip_fails():
    """Test that updating a completed trip fails"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create and complete a trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Completed Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    complete_trip(trip.id, user_id=user_id)

    # Try to update
    update_data = TripUpdate(title="Should Fail")

    with pytest.raises(HTTPException) as exc_info:
        update_trip(trip.id, update_data, user_id=user_id)

    assert exc_info.value.status_code == 400
    assert "planned" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_update_nonexistent_trip():
    """Test updating a trip that doesn't exist"""
    user_id, _ = setup_test_user_and_contact()

    update_data = TripUpdate(title="Should Fail")

    with pytest.raises(HTTPException) as exc_info:
        update_trip(999999, update_data, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_update_trip_invalid_activity():
    """Test updating trip with non-existent activity"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    update_data = TripUpdate(activity="NonExistentActivity")

    with pytest.raises(HTTPException) as exc_info:
        update_trip(trip.id, update_data, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "activity" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_update_trip_invalid_contact():
    """Test updating trip with non-existent contact"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    update_data = TripUpdate(contact1=999999)  # Non-existent contact

    with pytest.raises(HTTPException) as exc_info:
        update_trip(trip.id, update_data, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "contact" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_update_trip_other_users_trip():
    """Test that a user cannot update another user's trip"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    # Create another user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
                RETURNING id
                """
            ),
            {
                "email": "other@example.com",
                "first_name": "Other",
                "last_name": "User",
                "age": 25
            }
        )
        other_user_id = result.fetchone()[0]

    # Try to update as other user
    update_data = TripUpdate(title="Hacked!")

    with pytest.raises(HTTPException) as exc_info:
        update_trip(trip.id, update_data, user_id=other_user_id)

    assert exc_info.value.status_code == 404  # Trip not found for this user

    # Clean up other user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": other_user_id}
        )

    cleanup_test_data(user_id)


def test_update_trip_empty_update():
    """Test updating trip with no fields (should return unchanged trip)"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    # Update with empty data
    update_data = TripUpdate()

    updated = update_trip(trip.id, update_data, user_id=user_id)

    # Trip should be unchanged
    assert updated.title == trip.title
    assert updated.activity.name == trip.activity.name
    assert updated.grace_min == trip.grace_min
    assert updated.notes == trip.notes

    cleanup_test_data(user_id)


# ============================================================================
# NOTIFICATION SETTINGS TESTS
# ============================================================================

def test_create_trip_with_notification_settings():
    """Test creating a trip with custom notification settings"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Multi-day Trip",
        activity="Camping",
        start=now,
        eta=now + timedelta(hours=48),
        grace_min=30,
        location_text="Campground",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id,
        checkin_interval_min=60,  # Check in every hour
        notify_start_hour=8,      # Start notifications at 8 AM
        notify_end_hour=22        # End notifications at 10 PM
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.checkin_interval_min == 60
    assert trip.notify_start_hour == 8
    assert trip.notify_end_hour == 22

    cleanup_test_data(user_id)


def test_create_trip_default_notification_settings():
    """Test that default notification settings are applied when not specified"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Default Settings Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=contact_id
        # No notification settings specified
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Default interval is 30, quiet hours are null (no restriction)
    assert trip.checkin_interval_min == 30
    assert trip.notify_start_hour is None
    assert trip.notify_end_hour is None

    cleanup_test_data(user_id)


def test_create_trip_custom_checkin_interval():
    """Test creating a trip with a custom check-in interval"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Frequent Checkins",
        activity="Running",
        start=now,
        eta=now + timedelta(hours=3),
        grace_min=15,
        contact1=contact_id,
        checkin_interval_min=15  # Check in every 15 minutes
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.checkin_interval_min == 15
    assert trip.notify_start_hour is None
    assert trip.notify_end_hour is None

    cleanup_test_data(user_id)


def test_create_trip_quiet_hours_only():
    """Test creating a trip with quiet hours but default interval"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Overnight Trip",
        activity="Camping",
        start=now,
        eta=now + timedelta(hours=24),
        grace_min=60,
        contact1=contact_id,
        notify_start_hour=7,   # 7 AM
        notify_end_hour=21     # 9 PM
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.checkin_interval_min == 30  # Default
    assert trip.notify_start_hour == 7
    assert trip.notify_end_hour == 21

    cleanup_test_data(user_id)


def test_update_trip_notification_settings():
    """Test updating a planned trip's notification settings"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    # Original trip should have default settings
    assert trip.checkin_interval_min == 30  # Default
    assert trip.notify_start_hour is None
    assert trip.notify_end_hour is None

    # Update notification settings
    update_data = TripUpdate(
        checkin_interval_min=120,  # 2 hours
        notify_start_hour=6,
        notify_end_hour=23
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.checkin_interval_min == 120
    assert updated.notify_start_hour == 6
    assert updated.notify_end_hour == 23

    # Other fields should be unchanged
    assert updated.title == trip.title
    assert updated.grace_min == trip.grace_min

    cleanup_test_data(user_id)


def test_update_trip_checkin_interval_only():
    """Test updating only the check-in interval"""
    user_id, contact_id = setup_test_user_and_contact()

    trip = create_planned_trip(user_id, contact_id)

    update_data = TripUpdate(checkin_interval_min=45)
    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.checkin_interval_min == 45
    assert updated.notify_start_hour is None  # Unchanged
    assert updated.notify_end_hour is None    # Unchanged

    cleanup_test_data(user_id)


def test_get_trip_includes_notification_settings():
    """Test that get_trip returns notification settings"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Get Trip Test",
        activity="Biking",
        start=now + timedelta(hours=24),  # Future start for planned status
        eta=now + timedelta(hours=26),
        grace_min=30,
        contact1=contact_id,
        checkin_interval_min=90,
        notify_start_hour=9,
        notify_end_hour=20
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    created = create_trip(trip_data, background_tasks, user_id=user_id)

    # Fetch the trip
    fetched = get_trip(created.id, user_id=user_id)

    assert fetched.checkin_interval_min == 90
    assert fetched.notify_start_hour == 9
    assert fetched.notify_end_hour == 20

    cleanup_test_data(user_id)


def test_get_trips_includes_notification_settings():
    """Test that get_trips returns notification settings for all trips"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)

    # Create trip with custom settings
    create_trip(
        TripCreate(
            title="Trip 1",
            activity="Hiking",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            contact1=contact_id,
            checkin_interval_min=45,
            notify_start_hour=8,
            notify_end_hour=22
        ),
        background_tasks,
        user_id=user_id
    )

    # Create trip with default settings
    create_trip(
        TripCreate(
            title="Trip 2",
            activity="Biking",
            start=now,
            eta=now + timedelta(hours=1),
            grace_min=20,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    trips = get_trips(user_id=user_id)

    trip1 = next(t for t in trips if t.title == "Trip 1")
    trip2 = next(t for t in trips if t.title == "Trip 2")

    assert trip1.checkin_interval_min == 45
    assert trip1.notify_start_hour == 8
    assert trip1.notify_end_hour == 22

    assert trip2.checkin_interval_min == 30  # Default
    assert trip2.notify_start_hour is None
    assert trip2.notify_end_hour is None

    cleanup_test_data(user_id)


def test_get_active_trip_includes_notification_settings():
    """Test that get_active_trip returns notification settings"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active with Settings",
        activity="Running",
        start=now,  # Starts now = active
        eta=now + timedelta(hours=1),
        grace_min=15,
        contact1=contact_id,
        checkin_interval_min=15,
        notify_start_hour=6,
        notify_end_hour=23
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    create_trip(trip_data, background_tasks, user_id=user_id)

    active = get_active_trip(user_id=user_id)

    assert active is not None
    assert active.checkin_interval_min == 15
    assert active.notify_start_hour == 6
    assert active.notify_end_hour == 23

    cleanup_test_data(user_id)
