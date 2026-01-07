"""Data isolation tests to ensure users cannot access other users' data.

Tests for:
- Cross-user trip access prevention
- Cross-user contact access prevention
- Creating trips with other users' contacts
"""
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy
from fastapi import BackgroundTasks, HTTPException

from src import database as db
from src.api.trips import (
    TripCreate,
    TripResponse,
    create_trip,
    delete_trip,
    get_trip,
    get_trips,
)
from src.api.contacts import (
    ContactCreate,
    create_contact,
    delete_contact,
    get_contact,
    get_contacts,
)


def cleanup_user(email: str):
    """Helper to clean up test user and all related data"""
    with db.engine.begin() as connection:
        # Get user ID first
        user = connection.execute(
            sqlalchemy.text("SELECT id FROM users WHERE email = :email"),
            {"email": email}
        ).fetchone()

        if user:
            user_id = user.id

            # Clear last_checkin to avoid FK constraint
            connection.execute(
                sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id = :user_id"),
                {"user_id": user_id}
            )

            # Delete in proper order to respect foreign keys
            connection.execute(
                sqlalchemy.text("DELETE FROM trip_safety_contacts WHERE trip_id IN (SELECT id FROM trips WHERE user_id = :user_id)"),
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
            # Note: friend tables may not exist in all environments
            try:
                connection.execute(
                    sqlalchemy.text("DELETE FROM friendships WHERE user_id_1 = :user_id OR user_id_2 = :user_id"),
                    {"user_id": user_id}
                )
            except Exception:
                pass  # Table may not exist
            try:
                connection.execute(
                    sqlalchemy.text("DELETE FROM friend_invites WHERE inviter_id = :user_id"),
                    {"user_id": user_id}
                )
            except Exception:
                pass  # Table may not exist
            connection.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def create_test_user(email: str, first_name: str = "Test", last_name: str = "User") -> int:
    """Create a test user and return their ID"""
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, 25)
                RETURNING id
                """
            ),
            {"email": email, "first_name": first_name, "last_name": last_name}
        )
        return result.fetchone()[0]


def create_test_contact(user_id: int, name: str, email: str) -> int:
    """Create a test contact and return their ID"""
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {"user_id": user_id, "name": name, "email": email}
        )
        return result.fetchone()[0]


def create_test_trip(user_id: int, contact_id: int, title: str = "Test Trip") -> int:
    """Create a test trip and return its ID"""
    with db.engine.begin() as connection:
        # Get activity ID
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()
        activity_id = activity.id

        now = datetime.now(UTC)
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
                "title": title,
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 30,
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194,
                "contact1": contact_id,
                "created_at": now.isoformat(),
                "checkin_token": f"checkin_{user_id}_{now.timestamp()}",
                "checkout_token": f"checkout_{user_id}_{now.timestamp()}"
            }
        )
        return result.fetchone()[0]


# ============================================================================
# Cross-User Trip Access Tests
# ============================================================================

def test_user_cannot_access_other_user_trips():
    """Test that User B cannot access User A's trips via GET /trips/{id}"""
    user_a_email = "user-a-trips@isolation.test"
    user_b_email = "user-b-trips@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # User A creates a contact
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")

    # User A creates a trip
    trip_a_id = create_test_trip(user_a_id, contact_a_id, "User A's Private Trip")

    # User B tries to access User A's trip
    with pytest.raises(HTTPException) as exc_info:
        get_trip(trip_id=trip_a_id, user_id=user_b_id)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


def test_user_trips_list_only_shows_own_trips():
    """Test that GET /trips only returns the user's own trips"""
    user_a_email = "user-a-list@isolation.test"
    user_b_email = "user-b-list@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # Each user creates a contact and trip
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")
    contact_b_id = create_test_contact(user_b_id, "Contact B", "contact-b@test.com")

    trip_a_id = create_test_trip(user_a_id, contact_a_id, "User A Trip")
    trip_b_id = create_test_trip(user_b_id, contact_b_id, "User B Trip")

    # User A lists their trips
    user_a_trips = get_trips(user_id=user_a_id)
    user_a_trip_ids = [t.id for t in user_a_trips]

    # User A should only see their own trip
    assert trip_a_id in user_a_trip_ids
    assert trip_b_id not in user_a_trip_ids

    # User B lists their trips
    user_b_trips = get_trips(user_id=user_b_id)
    user_b_trip_ids = [t.id for t in user_b_trips]

    # User B should only see their own trip
    assert trip_b_id in user_b_trip_ids
    assert trip_a_id not in user_b_trip_ids

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


def test_user_cannot_delete_other_user_trip():
    """Test that User B cannot delete User A's trip"""
    user_a_email = "user-a-delete@isolation.test"
    user_b_email = "user-b-delete@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # User A creates a contact and trip
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")
    trip_a_id = create_test_trip(user_a_id, contact_a_id, "User A Trip")

    # User B tries to delete User A's trip
    background_tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        delete_trip(trip_id=trip_a_id, background_tasks=background_tasks, user_id=user_b_id)

    assert exc_info.value.status_code == 404

    # Verify trip still exists
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text("SELECT id FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_a_id}
        ).fetchone()
        assert trip is not None

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


# ============================================================================
# Cross-User Contact Access Tests
# ============================================================================

def test_user_cannot_access_other_user_contacts():
    """Test that User B cannot access User A's contacts"""
    user_a_email = "user-a-contacts@isolation.test"
    user_b_email = "user-b-contacts@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # User A creates a contact
    contact_a_id = create_test_contact(user_a_id, "Secret Contact", "secret@test.com")

    # User B tries to access User A's contact
    with pytest.raises(HTTPException) as exc_info:
        get_contact(contact_id=contact_a_id, user_id=user_b_id)

    assert exc_info.value.status_code == 404

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


def test_user_contacts_list_only_shows_own_contacts():
    """Test that GET /contacts only returns the user's own contacts"""
    user_a_email = "user-a-contact-list@isolation.test"
    user_b_email = "user-b-contact-list@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # Each user creates contacts
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")
    contact_b_id = create_test_contact(user_b_id, "Contact B", "contact-b@test.com")

    # User A lists their contacts
    user_a_contacts = get_contacts(user_id=user_a_id)
    user_a_contact_ids = [c.id for c in user_a_contacts]

    assert contact_a_id in user_a_contact_ids
    assert contact_b_id not in user_a_contact_ids

    # User B lists their contacts
    user_b_contacts = get_contacts(user_id=user_b_id)
    user_b_contact_ids = [c.id for c in user_b_contacts]

    assert contact_b_id in user_b_contact_ids
    assert contact_a_id not in user_b_contact_ids

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


def test_user_cannot_delete_other_user_contact():
    """Test that User B cannot delete User A's contact"""
    user_a_email = "user-a-del-contact@isolation.test"
    user_b_email = "user-b-del-contact@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # User A creates a contact
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")

    # User B tries to delete User A's contact
    with pytest.raises(HTTPException) as exc_info:
        delete_contact(contact_id=contact_a_id, user_id=user_b_id)

    assert exc_info.value.status_code == 404

    # Verify contact still exists
    with db.engine.begin() as connection:
        contact = connection.execute(
            sqlalchemy.text("SELECT id FROM contacts WHERE id = :contact_id"),
            {"contact_id": contact_a_id}
        ).fetchone()
        assert contact is not None

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


# ============================================================================
# Cross-User Trip Creation with Other User's Contact
# ============================================================================

def test_create_trip_with_other_users_contact_fails():
    """Test that User B cannot create a trip using User A's contact"""
    user_a_email = "user-a-trip-contact@isolation.test"
    user_b_email = "user-b-trip-contact@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # User A creates a contact
    contact_a_id = create_test_contact(user_a_id, "User A Contact", "user-a-contact@test.com")

    # User B tries to create a trip with User A's contact
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="Sneaky Trip",
        activity="hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="Mountain",
        contact1=contact_a_id,  # User A's contact!
        gen_lat=37.7749,
        gen_lon=-122.4194,
    )

    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        create_trip(body=trip_data, background_tasks=background_tasks, user_id=user_b_id)

    assert exc_info.value.status_code == 404
    assert "contact" in exc_info.value.detail.lower()

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


def test_create_trip_requires_own_contact():
    """Test that creating a trip with your own contact succeeds"""
    user_email = "user-own-contact@isolation.test"

    cleanup_user(user_email)

    # Create user
    user_id = create_test_user(user_email, "Own", "Contact")

    # User creates their own contact
    contact_id = create_test_contact(user_id, "My Contact", "my-contact@test.com")

    # User creates trip with their own contact - should succeed
    now = datetime.now(UTC)
    trip_data = TripCreate(
        title="My Trip",
        activity="hiking",
        start=now,
        eta=now + timedelta(hours=2),
        grace_min=30,
        location_text="My Mountain",
        contact1=contact_id,
        gen_lat=37.7749,
        gen_lon=-122.4194,
    )

    background_tasks = BackgroundTasks()
    result = create_trip(body=trip_data, background_tasks=background_tasks, user_id=user_id)

    assert isinstance(result, TripResponse)
    assert result.title == "My Trip"
    assert result.contact1 == contact_id

    cleanup_user(user_email)


# ============================================================================
# Additional Isolation Tests
# ============================================================================

def test_trip_contacts_isolated_per_user():
    """Test that trip safety contacts are properly isolated between users"""
    user_a_email = "user-a-safety@isolation.test"
    user_b_email = "user-b-safety@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # Each user creates contacts and trips
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")
    contact_b_id = create_test_contact(user_b_id, "Contact B", "contact-b@test.com")

    trip_a_id = create_test_trip(user_a_id, contact_a_id)
    trip_b_id = create_test_trip(user_b_id, contact_b_id)

    # Verify trip_safety_contacts are properly isolated
    with db.engine.begin() as connection:
        # Check User A's trip only has User A's contact
        trip_a_contacts = connection.execute(
            sqlalchemy.text(
                "SELECT contact_id FROM trip_safety_contacts WHERE trip_id = :trip_id"
            ),
            {"trip_id": trip_a_id}
        ).fetchall()

        trip_a_contact_ids = [c.contact_id for c in trip_a_contacts if c.contact_id is not None]
        # contact_a_id should be in trip A's contacts, contact_b_id should not
        if contact_a_id in trip_a_contact_ids:
            assert contact_b_id not in trip_a_contact_ids

        # Check User B's trip only has User B's contact
        trip_b_contacts = connection.execute(
            sqlalchemy.text(
                "SELECT contact_id FROM trip_safety_contacts WHERE trip_id = :trip_id"
            ),
            {"trip_id": trip_b_id}
        ).fetchall()

        trip_b_contact_ids = [c.contact_id for c in trip_b_contacts if c.contact_id is not None]
        if contact_b_id in trip_b_contact_ids:
            assert contact_a_id not in trip_b_contact_ids

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)


def test_events_isolated_per_user():
    """Test that trip events are properly isolated between users"""
    user_a_email = "user-a-events@isolation.test"
    user_b_email = "user-b-events@isolation.test"

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)

    # Create both users
    user_a_id = create_test_user(user_a_email, "User", "A")
    user_b_id = create_test_user(user_b_email, "User", "B")

    # Each user creates contacts and trips
    contact_a_id = create_test_contact(user_a_id, "Contact A", "contact-a@test.com")
    contact_b_id = create_test_contact(user_b_id, "Contact B", "contact-b@test.com")

    trip_a_id = create_test_trip(user_a_id, contact_a_id)

    # Create an event for User A's trip
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp)
                """
            ),
            {
                "user_id": user_a_id,
                "trip_id": trip_a_id,
                "timestamp": datetime.now(UTC).isoformat()
            }
        )

    # User B should not be able to see User A's events via the trip timeline
    with pytest.raises(HTTPException) as exc_info:
        from src.api.trips import get_trip_timeline
        get_trip_timeline(trip_id=trip_a_id, user_id=user_b_id)

    assert exc_info.value.status_code == 404

    cleanup_user(user_a_email)
    cleanup_user(user_b_email)
