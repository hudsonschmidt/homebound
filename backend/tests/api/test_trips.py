"""Tests for trips API endpoints"""
import pytest
from datetime import datetime, timezone, timedelta
from src import database as db
import sqlalchemy
from src.api.trips import (
    TripCreate,
    TripResponse,
    TimelineEvent,
    create_trip,
    get_trips,
    get_active_trip,
    get_trip,
    complete_trip,
    delete_trip,
    get_trip_timeline
)
from fastapi import HTTPException


def setup_test_user_and_contact():
    """Helper function to set up test user and contact"""
    test_email = "trip-test@homeboundapp.com"
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
                INSERT INTO contacts (user_id, name, phone, email)
                VALUES (:user_id, :name, :phone, :email)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "name": "Emergency Contact",
                "phone": "+1234567890",
                "email": "emergency@example.com"
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
    now = datetime.now(timezone.utc)
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

    trip = create_trip(trip_data, user_id=user_id)

    assert isinstance(trip, TripResponse)
    assert trip.title == "Hiking Trip"
    assert trip.activity == "Hiking"
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

    now = datetime.now(timezone.utc)
    trip_data = TripCreate(
        title="Invalid Trip",
        activity="NonExistentActivity",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=contact_id
    )

    with pytest.raises(HTTPException) as exc_info:
        create_trip(trip_data, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "activity" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_create_trip_invalid_contact():
    """Test creating trip with non-existent contact"""
    user_id, _ = setup_test_user_and_contact()

    now = datetime.now(timezone.utc)
    trip_data = TripCreate(
        title="Invalid Contact Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        contact1=999999  # Non-existent contact
    )

    with pytest.raises(HTTPException) as exc_info:
        create_trip(trip_data, user_id=user_id)

    assert exc_info.value.status_code == 404
    assert "contact" in exc_info.value.detail.lower()

    cleanup_test_data(user_id)


def test_get_trips():
    """Test retrieving all trips for a user"""
    user_id, contact_id = setup_test_user_and_contact()

    # Create multiple trips
    now = datetime.now(timezone.utc)

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
    now = datetime.now(timezone.utc)
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

    create_trip(trip_data, user_id=user_id)

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
    now = datetime.now(timezone.utc)
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
        user_id=user_id
    )

    # Get the trip
    trip = get_trip(created.id, user_id=user_id)

    assert trip.id == created.id
    assert trip.title == "Specific Trip"
    assert trip.activity == "Camping"

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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
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
    event_types = [e.what for e in timeline]
    assert "started" in event_types

    cleanup_test_data(user_id)


def test_get_timeline_nonexistent_trip():
    """Test getting timeline for non-existent trip"""
    with pytest.raises(HTTPException) as exc_info:
        get_trip_timeline(999999, user_id=1)

    assert exc_info.value.status_code == 404
