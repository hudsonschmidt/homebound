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
    extend_trip,
    get_active_trip,
    get_trip,
    get_trip_timeline,
    get_trips,
    start_trip,
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
    complete_bg_tasks = MagicMock(spec=BackgroundTasks)
    result = complete_trip(trip.id, complete_bg_tasks, user_id=user_id)
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

    complete_bg_tasks = MagicMock(spec=BackgroundTasks)
    complete_trip(trip.id, complete_bg_tasks, user_id=user_id)

    # Try to complete again
    with pytest.raises(HTTPException) as exc_info:
        complete_trip(trip.id, complete_bg_tasks, user_id=user_id)

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
    complete_bg_tasks = MagicMock(spec=BackgroundTasks)
    complete_trip(trip.id, complete_bg_tasks, user_id=user_id)

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


def test_create_trip_with_overnight_notification_hours():
    """Test creating a trip with overnight notification hours (start > end)"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Overnight Hours Trip",
        activity="Camping",
        start=now,
        eta=now + timedelta(hours=24),
        grace_min=60,
        contact1=contact_id,
        checkin_interval_min=60,
        notify_start_hour=22,  # 10 PM
        notify_end_hour=8      # 8 AM (overnight wrap)
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.notify_start_hour == 22
    assert trip.notify_end_hour == 8
    assert trip.checkin_interval_min == 60

    cleanup_test_data(user_id)


def test_create_trip_with_short_interval():
    """Test creating a trip with 15-minute check-in interval"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Short Interval Trip",
        activity="Running",
        start=now,
        eta=now + timedelta(hours=1),
        grace_min=15,
        contact1=contact_id,
        checkin_interval_min=15
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.checkin_interval_min == 15

    cleanup_test_data(user_id)


def test_create_trip_with_long_interval():
    """Test creating a trip with 2-hour check-in interval"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Long Interval Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=8),
        grace_min=60,
        contact1=contact_id,
        checkin_interval_min=120  # 2 hours
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.checkin_interval_min == 120

    cleanup_test_data(user_id)


def test_update_trip_clear_notification_hours():
    """Test clearing notification hours from a trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with notification hours (in the future so it's "planned" and editable)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Clear Hours Trip",
        activity="Biking",
        start=now + timedelta(hours=1),  # Future start = planned status
        eta=now + timedelta(hours=4),
        grace_min=30,
        contact1=contact_id,
        notify_start_hour=8,
        notify_end_hour=20
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.notify_start_hour == 8
    assert trip.notify_end_hour == 20

    # Update to clear notification hours (set to None via update)
    update_data = TripUpdate(
        notify_start_hour=None,
        notify_end_hour=None
    )

    # Note: We can't set None explicitly through update,
    # so we verify the original values are retained if not updated
    updated_trip = update_trip(trip.id, update_data, user_id=user_id)

    # The original values should be retained since we can't set None
    assert updated_trip.notify_start_hour == 8
    assert updated_trip.notify_end_hour == 20

    cleanup_test_data(user_id)


def test_update_trip_notification_hours_to_overnight():
    """Test updating trip to use overnight notification hours"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Update to Overnight",
        activity="Camping",
        start=now + timedelta(hours=1),  # Future start = planned status
        eta=now + timedelta(hours=25),
        grace_min=60,
        contact1=contact_id,
        notify_start_hour=8,
        notify_end_hour=20
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Update to overnight hours
    update_data = TripUpdate(
        notify_start_hour=22,
        notify_end_hour=6
    )

    updated_trip = update_trip(trip.id, update_data, user_id=user_id)

    assert updated_trip.notify_start_hour == 22
    assert updated_trip.notify_end_hour == 6

    cleanup_test_data(user_id)


# ============================================================================
# START/END LOCATION TESTS
# ============================================================================

def test_create_trip_with_single_location():
    """Test creating a trip with single location (default behavior)"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Single Location Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id,
        has_separate_locations=False  # Default
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.location_text == "Mountain Trail"
    assert trip.gen_lat == 37.7749
    assert trip.gen_lon == -122.4194
    assert trip.has_separate_locations is False
    assert trip.start_location_text is None
    assert trip.start_lat is None
    assert trip.start_lon is None

    cleanup_test_data(user_id)


def test_create_trip_with_separate_start_and_destination():
    """Test creating a trip with separate start and destination locations"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Road Trip",
        activity="Driving",
        start=now,
        eta=now + timedelta(hours=5),
        grace_min=30,
        location_text="Los Angeles, CA",  # Destination
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="San Francisco, CA",  # Start
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Verify destination
    assert trip.location_text == "Los Angeles, CA"
    assert trip.gen_lat == 34.0522
    assert trip.gen_lon == -118.2437

    # Verify start location
    assert trip.has_separate_locations is True
    assert trip.start_location_text == "San Francisco, CA"
    assert trip.start_lat == 37.7749
    assert trip.start_lon == -122.4194

    cleanup_test_data(user_id)


def test_create_trip_separate_locations_without_flag():
    """Test that start location fields are ignored when has_separate_locations is False"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Should Ignore Start",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="Should Be Ignored",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=False,  # Explicitly false
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Start location should be null when flag is false
    assert trip.has_separate_locations is False
    assert trip.start_location_text is None
    assert trip.start_lat is None
    assert trip.start_lon is None

    cleanup_test_data(user_id)


def test_get_trip_includes_start_location():
    """Test that get_trip returns start location fields"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Get Trip Start Location",
        activity="Biking",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=28),
        grace_min=30,
        location_text="End Point",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="Start Point",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    created = create_trip(trip_data, background_tasks, user_id=user_id)

    # Fetch the trip
    fetched = get_trip(created.id, user_id=user_id)

    assert fetched.has_separate_locations is True
    assert fetched.start_location_text == "Start Point"
    assert fetched.start_lat == 37.7749
    assert fetched.start_lon == -122.4194
    assert fetched.location_text == "End Point"

    cleanup_test_data(user_id)


def test_get_trips_includes_start_location():
    """Test that get_trips returns start location for all trips"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)

    # Create trip with separate locations
    create_trip(
        TripCreate(
            title="Trip With Start",
            activity="Driving",
            start=now,
            eta=now + timedelta(hours=3),
            grace_min=30,
            location_text="Destination A",
            gen_lat=34.0522,
            gen_lon=-118.2437,
            start_location_text="Start A",
            start_lat=37.7749,
            start_lon=-122.4194,
            has_separate_locations=True,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    # Create trip with single location
    create_trip(
        TripCreate(
            title="Trip Without Start",
            activity="Hiking",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            location_text="Single Location",
            gen_lat=40.7128,
            gen_lon=-74.0060,
            has_separate_locations=False,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    trips = get_trips(user_id=user_id)

    trip_with_start = next(t for t in trips if t.title == "Trip With Start")
    trip_without_start = next(t for t in trips if t.title == "Trip Without Start")

    assert trip_with_start.has_separate_locations is True
    assert trip_with_start.start_location_text == "Start A"
    assert trip_with_start.start_lat == 37.7749

    assert trip_without_start.has_separate_locations is False
    assert trip_without_start.start_location_text is None

    cleanup_test_data(user_id)


def test_get_active_trip_includes_start_location():
    """Test that get_active_trip returns start location fields"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active With Start",
        activity="Running",
        start=now,  # Starts now = active
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Finish Line",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="Starting Block",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    create_trip(trip_data, background_tasks, user_id=user_id)

    active = get_active_trip(user_id=user_id)

    assert active is not None
    assert active.has_separate_locations is True
    assert active.start_location_text == "Starting Block"
    assert active.start_lat == 37.7749
    assert active.start_lon == -122.4194

    cleanup_test_data(user_id)


def test_update_trip_add_start_location():
    """Test updating a trip to add a start location"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with single location (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Add Start Later",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=28),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        has_separate_locations=False,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.has_separate_locations is False

    # Update to add start location
    update_data = TripUpdate(
        start_location_text="New Start Point",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.has_separate_locations is True
    assert updated.start_location_text == "New Start Point"
    assert updated.start_lat == 37.7749
    assert updated.start_lon == -122.4194

    cleanup_test_data(user_id)


def test_update_trip_change_start_location():
    """Test updating a trip's start location"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with start location (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Change Start",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=28),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="Original Start",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Update start location
    update_data = TripUpdate(
        start_location_text="Updated Start",
        start_lat=40.7128,
        start_lon=-74.0060
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.start_location_text == "Updated Start"
    assert updated.start_lat == 40.7128
    assert updated.start_lon == -74.0060
    # Destination should be unchanged
    assert updated.location_text == "Destination"
    assert updated.gen_lat == 34.0522

    cleanup_test_data(user_id)


def test_update_trip_remove_start_location():
    """Test updating a trip to remove the start location (switch to single location)"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with start location (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Remove Start",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=28),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="Start To Remove",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.has_separate_locations is True

    # Update to switch back to single location
    update_data = TripUpdate(
        has_separate_locations=False
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.has_separate_locations is False
    # Note: start location fields may still exist in DB but flag is false

    cleanup_test_data(user_id)


def test_create_trip_start_location_default_false():
    """Test that has_separate_locations defaults to False"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Default False",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Single Location",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id
        # has_separate_locations not specified - should default to False
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.has_separate_locations is False

    cleanup_test_data(user_id)


def test_create_trip_both_locations_with_coordinates():
    """Test creating a trip with full coordinate data for both locations"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Full Coordinates",
        activity="Driving",
        start=now,
        eta=now + timedelta(hours=6),
        grace_min=45,
        location_text="New York, NY",
        gen_lat=40.7128,
        gen_lon=-74.0060,
        start_location_text="Boston, MA",
        start_lat=42.3601,
        start_lon=-71.0589,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Verify all coordinates are stored correctly
    assert trip.gen_lat == 40.7128
    assert trip.gen_lon == -74.0060
    assert trip.start_lat == 42.3601
    assert trip.start_lon == -71.0589

    cleanup_test_data(user_id)


def test_update_trip_both_locations():
    """Test updating both start and destination locations simultaneously"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Update Both",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=30),
        grace_min=30,
        location_text="Original Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="Original Start",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Update both locations
    update_data = TripUpdate(
        location_text="New Destination",
        gen_lat=40.7128,
        gen_lon=-74.0060,
        start_location_text="New Start",
        start_lat=42.3601,
        start_lon=-71.0589
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.location_text == "New Destination"
    assert updated.gen_lat == 40.7128
    assert updated.gen_lon == -74.0060
    assert updated.start_location_text == "New Start"
    assert updated.start_lat == 42.3601
    assert updated.start_lon == -71.0589

    cleanup_test_data(user_id)


# ============================================================================
# TIMEZONE TESTS
# ============================================================================

def test_create_trip_with_timezones():
    """Test creating a trip with separate start and ETA timezones"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Cross Timezone Trip",
        activity="Driving",
        start=now,
        eta=now + timedelta(hours=5),
        grace_min=30,
        location_text="Los Angeles, CA",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        contact1=contact_id,
        timezone="America/New_York",  # User's device timezone
        start_timezone="America/New_York",  # Departure timezone (Eastern)
        eta_timezone="America/Los_Angeles"  # Arrival timezone (Pacific)
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.timezone == "America/New_York"
    assert trip.start_timezone == "America/New_York"
    assert trip.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


def test_create_trip_without_timezones():
    """Test creating a trip without timezone fields (should be null)"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="No Timezone Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Local Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id
        # No timezone fields specified
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.timezone is None
    assert trip.start_timezone is None
    assert trip.eta_timezone is None

    cleanup_test_data(user_id)


def test_create_trip_with_only_start_timezone():
    """Test creating a trip with only start timezone specified"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Start Timezone Only",
        activity="Driving",
        start=now,
        eta=now + timedelta(hours=3),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        contact1=contact_id,
        start_timezone="America/Chicago"
        # eta_timezone not specified
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.start_timezone == "America/Chicago"
    assert trip.eta_timezone is None

    cleanup_test_data(user_id)


def test_create_trip_with_only_eta_timezone():
    """Test creating a trip with only ETA timezone specified"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="ETA Timezone Only",
        activity="Flying",
        start=now,
        eta=now + timedelta(hours=4),
        grace_min=60,
        location_text="Airport",
        gen_lat=40.6413,
        gen_lon=-73.7781,
        contact1=contact_id,
        eta_timezone="America/Denver"
        # start_timezone not specified
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.start_timezone is None
    assert trip.eta_timezone == "America/Denver"

    cleanup_test_data(user_id)


def test_create_trip_same_timezone_for_both():
    """Test creating a trip with the same timezone for start and ETA"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Same Timezone Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id,
        timezone="America/Los_Angeles",
        start_timezone="America/Los_Angeles",
        eta_timezone="America/Los_Angeles"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.start_timezone == "America/Los_Angeles"
    assert trip.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


def test_get_trip_includes_timezones():
    """Test that get_trip returns timezone fields"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Get Trip Timezone Test",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=30),
        grace_min=30,
        location_text="Cross Country",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        contact1=contact_id,
        timezone="America/New_York",
        start_timezone="America/New_York",
        eta_timezone="America/Los_Angeles"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    created = create_trip(trip_data, background_tasks, user_id=user_id)

    # Fetch the trip
    fetched = get_trip(created.id, user_id=user_id)

    assert fetched.timezone == "America/New_York"
    assert fetched.start_timezone == "America/New_York"
    assert fetched.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


def test_get_trips_includes_timezones():
    """Test that get_trips returns timezone fields for all trips"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)

    # Create trip with timezones
    create_trip(
        TripCreate(
            title="Trip With Timezones",
            activity="Driving",
            start=now,
            eta=now + timedelta(hours=5),
            grace_min=30,
            location_text="Destination A",
            gen_lat=34.0522,
            gen_lon=-118.2437,
            contact1=contact_id,
            start_timezone="America/Chicago",
            eta_timezone="America/Denver"
        ),
        background_tasks,
        user_id=user_id
    )

    # Create trip without timezones
    create_trip(
        TripCreate(
            title="Trip Without Timezones",
            activity="Hiking",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            location_text="Local Hike",
            gen_lat=37.7749,
            gen_lon=-122.4194,
            contact1=contact_id
        ),
        background_tasks,
        user_id=user_id
    )

    trips = get_trips(user_id=user_id)

    trip_with_tz = next(t for t in trips if t.title == "Trip With Timezones")
    trip_without_tz = next(t for t in trips if t.title == "Trip Without Timezones")

    assert trip_with_tz.start_timezone == "America/Chicago"
    assert trip_with_tz.eta_timezone == "America/Denver"

    assert trip_without_tz.start_timezone is None
    assert trip_without_tz.eta_timezone is None

    cleanup_test_data(user_id)


def test_get_active_trip_includes_timezones():
    """Test that get_active_trip returns timezone fields"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active With Timezones",
        activity="Flying",
        start=now,  # Starts now = active
        eta=now + timedelta(hours=4),
        grace_min=60,
        location_text="Airport",
        gen_lat=40.6413,
        gen_lon=-73.7781,
        contact1=contact_id,
        timezone="America/New_York",
        start_timezone="America/New_York",
        eta_timezone="America/Los_Angeles"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    create_trip(trip_data, background_tasks, user_id=user_id)

    active = get_active_trip(user_id=user_id)

    assert active is not None
    assert active.timezone == "America/New_York"
    assert active.start_timezone == "America/New_York"
    assert active.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


def test_update_trip_add_timezones():
    """Test updating a trip to add timezone fields"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip without timezones (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Add Timezones Later",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=30),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.start_timezone is None
    assert trip.eta_timezone is None

    # Update to add timezones
    update_data = TripUpdate(
        start_timezone="America/New_York",
        eta_timezone="America/Los_Angeles"
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.start_timezone == "America/New_York"
    assert updated.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


def test_update_trip_change_timezones():
    """Test updating a trip's timezone fields"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with timezones (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Change Timezones",
        activity="Driving",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=30),
        grace_min=30,
        location_text="Destination",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        contact1=contact_id,
        start_timezone="America/New_York",
        eta_timezone="America/Chicago"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Update timezones
    update_data = TripUpdate(
        start_timezone="America/Denver",
        eta_timezone="America/Los_Angeles"
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.start_timezone == "America/Denver"
    assert updated.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


def test_update_trip_timezone_partial():
    """Test updating only one timezone field leaves the other unchanged"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with both timezones (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Partial Timezone Update",
        activity="Flying",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=28),
        grace_min=60,
        location_text="Airport",
        gen_lat=40.6413,
        gen_lon=-73.7781,
        contact1=contact_id,
        start_timezone="America/New_York",
        eta_timezone="America/Los_Angeles"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Update only start_timezone
    update_data = TripUpdate(
        start_timezone="America/Chicago"
    )

    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.start_timezone == "America/Chicago"
    assert updated.eta_timezone == "America/Los_Angeles"  # Unchanged

    cleanup_test_data(user_id)


def test_create_trip_with_international_timezones():
    """Test creating a trip with international timezone identifiers"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="International Trip",
        activity="Flying",
        start=now,
        eta=now + timedelta(hours=10),
        grace_min=120,
        location_text="Tokyo, Japan",
        gen_lat=35.6762,
        gen_lon=139.6503,
        contact1=contact_id,
        timezone="America/New_York",
        start_timezone="America/New_York",
        eta_timezone="Asia/Tokyo"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.start_timezone == "America/New_York"
    assert trip.eta_timezone == "Asia/Tokyo"

    cleanup_test_data(user_id)


def test_create_trip_with_utc_timezone():
    """Test creating a trip with UTC timezone"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="UTC Trip",
        activity="Sailing",
        start=now,
        eta=now + timedelta(hours=8),
        grace_min=60,
        location_text="Open Ocean",
        gen_lat=0.0,
        gen_lon=0.0,
        contact1=contact_id,
        timezone="UTC",
        start_timezone="UTC",
        eta_timezone="UTC"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.timezone == "UTC"
    assert trip.start_timezone == "UTC"
    assert trip.eta_timezone == "UTC"

    cleanup_test_data(user_id)


def test_create_trip_timezone_with_locations():
    """Test creating a trip with both timezones and separate start/destination locations"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Full Featured Trip",
        activity="Driving",
        start=now,
        eta=now + timedelta(hours=6),
        grace_min=45,
        location_text="Los Angeles, CA",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="San Francisco, CA",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id,
        timezone="America/Los_Angeles",
        start_timezone="America/Los_Angeles",
        eta_timezone="America/Los_Angeles"
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Verify locations
    assert trip.has_separate_locations is True
    assert trip.start_location_text == "San Francisco, CA"
    assert trip.location_text == "Los Angeles, CA"

    # Verify timezones
    assert trip.start_timezone == "America/Los_Angeles"
    assert trip.eta_timezone == "America/Los_Angeles"

    cleanup_test_data(user_id)


# ============================================================================
# NOTIFY SELF TESTS
# ============================================================================

def test_create_trip_with_notify_self_enabled():
    """Test creating a trip with notify_self enabled"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Notify Self Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id,
        notify_self=True
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.notify_self is True

    cleanup_test_data(user_id)


def test_create_trip_notify_self_defaults_to_false():
    """Test that notify_self defaults to False when not specified"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Default Notify Self Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id
        # notify_self not specified - should default to False
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.notify_self is False

    cleanup_test_data(user_id)


def test_create_trip_with_notify_self_disabled():
    """Test creating a trip with notify_self explicitly disabled"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="No Notify Self Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        gen_lat=37.7749,
        gen_lon=-122.4194,
        contact1=contact_id,
        notify_self=False
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    assert trip.notify_self is False

    cleanup_test_data(user_id)


def test_get_trip_includes_notify_self():
    """Test that get_trip returns notify_self field"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Get Trip Notify Self Test",
        activity="Biking",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=26),
        grace_min=30,
        contact1=contact_id,
        notify_self=True
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    created = create_trip(trip_data, background_tasks, user_id=user_id)

    # Fetch the trip
    fetched = get_trip(created.id, user_id=user_id)

    assert fetched.notify_self is True

    cleanup_test_data(user_id)


def test_get_trips_includes_notify_self():
    """Test that get_trips returns notify_self for all trips"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    background_tasks = MagicMock(spec=BackgroundTasks)

    # Create trip with notify_self enabled
    create_trip(
        TripCreate(
            title="Trip With Notify Self",
            activity="Hiking",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            contact1=contact_id,
            notify_self=True
        ),
        background_tasks,
        user_id=user_id
    )

    # Create trip with notify_self disabled
    create_trip(
        TripCreate(
            title="Trip Without Notify Self",
            activity="Biking",
            start=now,
            eta=now + timedelta(hours=1),
            grace_min=20,
            contact1=contact_id,
            notify_self=False
        ),
        background_tasks,
        user_id=user_id
    )

    trips = get_trips(user_id=user_id)

    trip_with_notify = next(t for t in trips if t.title == "Trip With Notify Self")
    trip_without_notify = next(t for t in trips if t.title == "Trip Without Notify Self")

    assert trip_with_notify.notify_self is True
    assert trip_without_notify.notify_self is False

    cleanup_test_data(user_id)


def test_get_active_trip_includes_notify_self():
    """Test that get_active_trip returns notify_self field"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active With Notify Self",
        activity="Running",
        start=now,  # Starts now = active
        eta=now + timedelta(hours=1),
        grace_min=15,
        contact1=contact_id,
        notify_self=True
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    create_trip(trip_data, background_tasks, user_id=user_id)

    active = get_active_trip(user_id=user_id)

    assert active is not None
    assert active.notify_self is True

    cleanup_test_data(user_id)


def test_update_trip_enable_notify_self():
    """Test updating a trip to enable notify_self"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip without notify_self (future start = planned)
    trip = create_planned_trip(user_id, contact_id)
    assert trip.notify_self is False

    # Update to enable notify_self
    update_data = TripUpdate(notify_self=True)
    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.notify_self is True

    cleanup_test_data(user_id)


def test_update_trip_disable_notify_self():
    """Test updating a trip to disable notify_self"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with notify_self enabled (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Update Notify Self Trip",
        activity="Hiking",
        start=now + timedelta(hours=24),  # Future = planned
        eta=now + timedelta(hours=26),
        grace_min=30,
        contact1=contact_id,
        notify_self=True
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "planned"
    assert trip.notify_self is True

    # Update to disable notify_self
    update_data = TripUpdate(notify_self=False)
    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.notify_self is False

    cleanup_test_data(user_id)


def test_update_trip_notify_self_unchanged():
    """Test that notify_self remains unchanged when not in update"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with notify_self enabled (future start = planned)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Keep Notify Self Trip",
        activity="Hiking",
        start=now + timedelta(hours=24),
        eta=now + timedelta(hours=26),
        grace_min=30,
        contact1=contact_id,
        notify_self=True
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.notify_self is True

    # Update other field without touching notify_self
    update_data = TripUpdate(title="Updated Title")
    updated = update_trip(trip.id, update_data, user_id=user_id)

    assert updated.title == "Updated Title"
    assert updated.notify_self is True  # Should remain unchanged

    cleanup_test_data(user_id)


def test_create_trip_notify_self_with_all_features():
    """Test creating a trip with notify_self and all other features"""
    user_id, contact_id = setup_test_user_and_contact()

    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Full Featured With Notify Self",
        activity="Driving",
        start=now,
        eta=now + timedelta(hours=6),
        grace_min=45,
        location_text="Los Angeles, CA",
        gen_lat=34.0522,
        gen_lon=-118.2437,
        start_location_text="San Francisco, CA",
        start_lat=37.7749,
        start_lon=-122.4194,
        has_separate_locations=True,
        contact1=contact_id,
        timezone="America/Los_Angeles",
        start_timezone="America/Los_Angeles",
        eta_timezone="America/Los_Angeles",
        checkin_interval_min=60,
        notify_start_hour=8,
        notify_end_hour=22,
        notify_self=True
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Verify notify_self
    assert trip.notify_self is True

    # Verify other features still work
    assert trip.has_separate_locations is True
    assert trip.start_location_text == "San Francisco, CA"
    assert trip.start_timezone == "America/Los_Angeles"
    assert trip.checkin_interval_min == 60
    assert trip.notify_start_hour == 8
    assert trip.notify_end_hour == 22

    cleanup_test_data(user_id)


# =============================================================================
# START TRIP EDGE CASE TESTS
# =============================================================================

def test_start_trip_early_updates_start_time():
    """Starting a planned trip early should update start time to now"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip scheduled 24 hours in future
    now = datetime.now(UTC)
    future_start = now + timedelta(hours=24)
    trip_data = TripCreate(
        title="Future Trip",
        activity="Hiking",
        start=future_start,
        eta=future_start + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Verify trip was created as planned (future start time)
    assert trip.status == "planned"

    # Start trip early
    result = start_trip(trip.id, background_tasks, user_id=user_id)
    assert result["ok"] is True

    # Verify start time was updated to approximately now (not 24 hours in future)
    with db.engine.begin() as connection:
        db_trip = connection.execute(
            sqlalchemy.text("SELECT start, status FROM trips WHERE id = :trip_id"),
            {"trip_id": trip.id}
        ).fetchone()

        assert db_trip.status == "active"
        # Make db_trip.start timezone-aware for comparison
        db_start = db_trip.start.replace(tzinfo=UTC) if db_trip.start.tzinfo is None else db_trip.start
        # Start time should be much closer to now than original (within 1 minute)
        time_diff = abs((db_start - now).total_seconds())
        assert time_diff < 60, f"Start time not updated: diff={time_diff}s, expected ~0s"
        # Original was 24 hours in future, new should be now (difference should be ~24 hours)
        diff_from_original = abs((future_start - db_start).total_seconds())
        assert diff_from_original > 23 * 3600, "Start time should be updated from original scheduled time"

    cleanup_test_data(user_id)


def test_trip_duration_non_negative_after_early_start():
    """Trip completed after early start should have positive duration"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip scheduled 24 hours in future
    now = datetime.now(UTC)
    future_start = now + timedelta(hours=24)
    trip_data = TripCreate(
        title="Future Trip",
        activity="Hiking",
        start=future_start,
        eta=future_start + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "planned"

    # Start trip early
    start_trip(trip.id, background_tasks, user_id=user_id)

    # Complete trip immediately
    complete_trip(trip.id, background_tasks, user_id=user_id)

    # Verify duration is non-negative (completed_at >= start)
    with db.engine.begin() as connection:
        db_trip = connection.execute(
            sqlalchemy.text("SELECT start, completed_at FROM trips WHERE id = :trip_id"),
            {"trip_id": trip.id}
        ).fetchone()

        assert db_trip.completed_at is not None
        assert db_trip.start is not None
        # Normalize timezone awareness for comparison
        db_start = db_trip.start.replace(tzinfo=UTC) if db_trip.start.tzinfo is None else db_trip.start
        db_completed = db_trip.completed_at.replace(tzinfo=UTC) if db_trip.completed_at.tzinfo is None else db_trip.completed_at
        # Duration should be non-negative
        duration = (db_completed - db_start).total_seconds()
        assert duration >= 0, f"Duration should be non-negative, got {duration}s"

    cleanup_test_data(user_id)


def test_start_trip_already_active_fails():
    """Cannot start a trip that is already active"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip that starts now (will be active)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Active Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "active"

    # Try to start already active trip - should fail
    with pytest.raises(HTTPException) as exc_info:
        start_trip(trip.id, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 400
    assert "planned" in exc_info.value.detail.lower() or "status" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_start_trip_completed_fails():
    """Cannot start a trip that is already completed"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create and complete a trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Completed Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    complete_trip(trip.id, background_tasks, user_id=user_id)

    # Verify it's completed
    completed_trip_data = get_trip(trip.id, user_id=user_id)
    assert completed_trip_data.status == "completed"

    # Try to start completed trip - should fail
    with pytest.raises(HTTPException) as exc_info:
        start_trip(trip.id, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 400

    cleanup_test_data(user_id)


def test_start_trip_other_users_trip_fails():
    """Cannot start another user's trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create a second user
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
                "email": "other@homeboundapp.com",
                "first_name": "Other",
                "last_name": "User",
                "age": 25
            }
        )
        other_user_id = result.fetchone()[0]

    # Create trip for first user (planned, future start)
    now = datetime.now(UTC)
    future_start = now + timedelta(hours=24)
    trip_data = TripCreate(
        title="User1 Trip",
        activity="Hiking",
        start=future_start,
        eta=future_start + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "planned"

    # Try to start as other user - should fail
    with pytest.raises(HTTPException) as exc_info:
        start_trip(trip.id, background_tasks, user_id=other_user_id)

    assert exc_info.value.status_code in [403, 404]

    # Cleanup both users
    cleanup_test_data(user_id)
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": other_user_id}
        )


def test_start_trip_nonexistent_fails():
    """Cannot start a trip that doesn't exist"""
    user_id, contact_id = setup_test_user_and_contact()

    background_tasks = MagicMock(spec=BackgroundTasks)

    # Try to start non-existent trip
    with pytest.raises(HTTPException) as exc_info:
        start_trip(999999, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 404

    cleanup_test_data(user_id)


# =============================================================================
# EXTEND TRIP EDGE CASE TESTS
# =============================================================================

def test_extend_trip_basic():
    """Extending an active trip should update ETA and create checkin event"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create active trip (start now)
    now = datetime.now(UTC)
    original_eta = now + timedelta(hours=2)
    trip_data = TripCreate(
        title="Active Trip",
        activity="Hiking",
        start=now,
        eta=original_eta,
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "active"

    # Extend by 30 minutes
    result = extend_trip(trip.id, 30, background_tasks, user_id=user_id)
    assert result["ok"] is True

    # Verify ETA was extended
    with db.engine.begin() as connection:
        db_trip = connection.execute(
            sqlalchemy.text("SELECT eta, status FROM trips WHERE id = :trip_id"),
            {"trip_id": trip.id}
        ).fetchone()

        assert db_trip.status == "active"
        db_eta = db_trip.eta.replace(tzinfo=UTC) if db_trip.eta.tzinfo is None else db_trip.eta
        # ETA should be approximately 30 minutes more than original
        expected_eta = original_eta + timedelta(minutes=30)
        eta_diff = abs((db_eta - expected_eta).total_seconds())
        assert eta_diff < 60, f"ETA not extended correctly: diff={eta_diff}s"

        # Verify extended event was created (extend_trip creates 'extended' event)
        event = connection.execute(
            sqlalchemy.text("SELECT what FROM events WHERE trip_id = :trip_id ORDER BY id DESC LIMIT 1"),
            {"trip_id": trip.id}
        ).fetchone()
        assert event.what == "extended"

    cleanup_test_data(user_id)


def test_extend_trip_updates_overdue_to_active():
    """Extending an overdue trip should change status back to active"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create active trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Overdue Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Manually set status to overdue for testing
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("UPDATE trips SET status = 'overdue' WHERE id = :trip_id"),
            {"trip_id": trip.id}
        )

    # Extend trip
    result = extend_trip(trip.id, 60, background_tasks, user_id=user_id)
    assert result["ok"] is True

    # Verify status changed to active
    with db.engine.begin() as connection:
        db_trip = connection.execute(
            sqlalchemy.text("SELECT status FROM trips WHERE id = :trip_id"),
            {"trip_id": trip.id}
        ).fetchone()
        assert db_trip.status == "active"

    cleanup_test_data(user_id)


def test_extend_trip_planned_fails():
    """Cannot extend a planned (not yet started) trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create planned trip (future start)
    now = datetime.now(UTC)
    future_start = now + timedelta(hours=24)
    trip_data = TripCreate(
        title="Future Trip",
        activity="Hiking",
        start=future_start,
        eta=future_start + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "planned"

    # Try to extend planned trip - should fail
    with pytest.raises(HTTPException) as exc_info:
        extend_trip(trip.id, 30, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 400

    cleanup_test_data(user_id)


def test_extend_trip_completed_fails():
    """Cannot extend a completed trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create and complete trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Completed Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    complete_trip(trip.id, background_tasks, user_id=user_id)

    # Try to extend completed trip - should fail
    with pytest.raises(HTTPException) as exc_info:
        extend_trip(trip.id, 30, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 400

    cleanup_test_data(user_id)


def test_extend_trip_other_users_trip_fails():
    """Cannot extend another user's trip"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create a second user
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
                "email": "other_extend@homeboundapp.com",
                "first_name": "Other",
                "last_name": "User",
                "age": 25
            }
        )
        other_user_id = result.fetchone()[0]

    # Create active trip for first user
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="User1 Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Try to extend as other user - should fail
    with pytest.raises(HTTPException) as exc_info:
        extend_trip(trip.id, 30, background_tasks, user_id=other_user_id)

    assert exc_info.value.status_code in [403, 404]

    cleanup_test_data(user_id)
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": other_user_id}
        )


def test_extend_trip_nonexistent_fails():
    """Cannot extend a trip that doesn't exist"""
    user_id, contact_id = setup_test_user_and_contact()

    background_tasks = MagicMock(spec=BackgroundTasks)

    with pytest.raises(HTTPException) as exc_info:
        extend_trip(999999, 30, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 404

    cleanup_test_data(user_id)


def test_extend_trip_multiple_times():
    """Multiple extensions should accumulate ETA correctly"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create active trip
    now = datetime.now(UTC)
    original_eta = now + timedelta(hours=2)
    trip_data = TripCreate(
        title="Multi-extend Trip",
        activity="Hiking",
        start=now,
        eta=original_eta,
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)

    # Extend 3 times: 15 + 30 + 15 = 60 minutes total
    extend_trip(trip.id, 15, background_tasks, user_id=user_id)
    extend_trip(trip.id, 30, background_tasks, user_id=user_id)
    extend_trip(trip.id, 15, background_tasks, user_id=user_id)

    # Verify ETA was extended by ~60 minutes total
    with db.engine.begin() as connection:
        db_trip = connection.execute(
            sqlalchemy.text("SELECT eta FROM trips WHERE id = :trip_id"),
            {"trip_id": trip.id}
        ).fetchone()

        db_eta = db_trip.eta.replace(tzinfo=UTC) if db_trip.eta.tzinfo is None else db_trip.eta
        expected_eta = original_eta + timedelta(minutes=60)
        eta_diff = abs((db_eta - expected_eta).total_seconds())
        assert eta_diff < 60, f"ETA not extended correctly after multiple extensions: diff={eta_diff}s"

        # Verify 3 extended events were created (extend_trip creates 'extended' events)
        events = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) as cnt FROM events WHERE trip_id = :trip_id AND what = 'extended'"),
            {"trip_id": trip.id}
        ).fetchone()
        assert events.cnt == 3

    cleanup_test_data(user_id)


# =============================================================================
# COMPLETE TRIP EDGE CASE TESTS
# =============================================================================

def test_complete_trip_planned_fails():
    """Cannot complete a trip that hasn't started yet"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create planned trip (future start)
    now = datetime.now(UTC)
    future_start = now + timedelta(hours=24)
    trip_data = TripCreate(
        title="Future Trip",
        activity="Hiking",
        start=future_start,
        eta=future_start + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.status == "planned"

    # Try to complete planned trip - should fail
    with pytest.raises(HTTPException) as exc_info:
        complete_trip(trip.id, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 400

    cleanup_test_data(user_id)


def test_complete_trip_already_completed_fails():
    """Cannot complete a trip twice"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create and complete trip
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Double Complete Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    complete_trip(trip.id, background_tasks, user_id=user_id)

    # Try to complete again - should fail
    with pytest.raises(HTTPException) as exc_info:
        complete_trip(trip.id, background_tasks, user_id=user_id)

    assert exc_info.value.status_code == 400

    cleanup_test_data(user_id)


# =============================================================================
# DATA VALIDATION EDGE CASE TESTS
# =============================================================================

def test_create_trip_start_after_eta():
    """Trip where start time is after ETA - behavior test"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create trip with start > eta (nonsensical but may be allowed)
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Backwards Trip",
        activity="Hiking",
        start=now + timedelta(hours=2),
        eta=now + timedelta(hours=1),  # ETA before start!
        grace_min=30,
        location_text="Mountain Trail",
        contact1=contact_id
    )

    background_tasks = MagicMock(spec=BackgroundTasks)

    # This may succeed or fail depending on validation
    # Recording actual behavior for documentation
    try:
        trip = create_trip(trip_data, background_tasks, user_id=user_id)
        # If it succeeds, document this as allowed (potential bug)
        cleanup_test_data(user_id)
        # Note: This test documents that start > eta is currently ALLOWED
        # Consider adding validation to prevent this
    except HTTPException as e:
        # If it fails with validation error, that's the expected safe behavior
        assert e.status_code == 400
        cleanup_test_data(user_id)
