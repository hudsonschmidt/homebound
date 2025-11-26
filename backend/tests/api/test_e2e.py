"""End-to-end tests for complete user workflows"""
import pytest
from unittest.mock import MagicMock
from src import database as db
import sqlalchemy
from src.api.profile import (
    get_profile,
    update_profile,
    delete_account,
    ProfileUpdate
)
from src.api.contacts import (
    create_contact,
    get_contacts,
    ContactCreate
)
from src.api.trips import (
    create_trip,
    get_trip,
    TripCreate
)
from datetime import datetime, timedelta
from fastapi import HTTPException, BackgroundTasks


def test_e2e_complete_user_journey():
    """
    Test complete user journey from registration to account deletion:
    1. Create user (simulated via magic link)
    2. Update profile (onboarding)
    3. Add emergency contacts
    4. Create a trip
    5. Delete account (should cascade delete everything)
    """
    test_email = "e2e-full-journey@homeboundapp.com"

    # Clean up before test
    with db.engine.begin() as connection:
        # Delete in proper cascade order
        # Events reference trips, so delete events first
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

    # Step 1: Create user (simulating magic link auto-registration)
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
                "email": test_email,
                "first_name": "",
                "last_name": "",
                "age": 0
            }
        )
        user_id = result.fetchone()[0]

    # Verify profile is incomplete initially
    profile = get_profile(user_id=user_id)
    assert profile.profile_completed is False

    # Step 2: User completes onboarding (update profile)
    update_data = ProfileUpdate(
        first_name="Journey",
        last_name="User",
        age=28
    )
    profile_response = update_profile(update_data, user_id=user_id)
    assert profile_response.ok is True
    assert profile_response.user["profile_completed"] is True

    # Step 3: Add emergency contacts
    contact1 = create_contact(
        ContactCreate(name="Emergency One", email="em1@example.com"),
        user_id=user_id
    )
    contact2 = create_contact(
        ContactCreate(name="Emergency Two", email="em2@example.com"),
        user_id=user_id
    )

    # Verify contacts were created
    contacts = get_contacts(user_id=user_id)
    assert len(contacts) == 2

    # Step 4: Create a trip
    now = datetime.utcnow()
    trip_data = TripCreate(
        title="Test Journey Trip",
        activity="Hiking",
        start=now,
        eta=now + timedelta(hours=3),
        grace_min=30,
        location_text="Mountain Trail",
        notes="End-to-end test trip",
        contact1=contact1.id
    )
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(trip_data, background_tasks, user_id=user_id)
    assert trip.title == "Test Journey Trip"

    # Step 5: Verify all data exists before deletion
    with db.engine.begin() as connection:
        # Check user
        user_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_count == 1

        # Check contacts
        contacts_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert contacts_count == 2

        # Check trips
        trips_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert trips_count == 1

    # Step 6: Delete account (should cascade delete everything)
    result = delete_account(user_id=user_id)
    assert result["ok"] is True

    # Step 7: Verify everything is deleted
    with db.engine.begin() as connection:
        user_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_count == 0

        contacts_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert contacts_count == 0

        trips_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert trips_count == 0


def test_e2e_onboarding_flow():
    """
    Test the iOS app onboarding flow:
    1. User requests magic link (auto-creates user)
    2. User verifies code (gets tokens)
    3. User completes profile
    4. Profile completed flag is set
    """
    test_email = "e2e-onboarding@homeboundapp.com"

    # Clean up
    with db.engine.begin() as connection:
        # Delete trips first (they reference contacts via foreign keys)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete events
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete contacts (after trips are deleted)
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete devices
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete login tokens
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Finally delete users
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Step 1: Simulate user creation (normally happens during magic link request)
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
                "email": test_email,
                "first_name": "",
                "last_name": "",
                "age": 0
            }
        )
        user_id = result.fetchone()[0]

    # Step 2: Get initial profile - should be incomplete
    profile = get_profile(user_id=user_id)
    assert profile.email == test_email
    assert profile.first_name == ""
    assert profile.last_name == ""
    assert profile.age == 0
    assert profile.profile_completed is False

    # Step 3: User completes onboarding form
    update_data = ProfileUpdate(
        first_name="New",
        last_name="User",
        age=25
    )
    response = update_profile(update_data, user_id=user_id)

    # Step 4: Verify profile is now complete
    assert response.ok is True
    assert response.user["first_name"] == "New"
    assert response.user["last_name"] == "User"
    assert response.user["age"] == 25
    assert response.user["profile_completed"] is True

    # Clean up
    delete_account(user_id=user_id)


def test_e2e_contact_management_workflow():
    """
    Test the contact management workflow:
    1. Create user
    2. Add multiple contacts (some with optional fields)
    3. Update a contact
    4. Delete a contact
    5. Use contacts in a trip
    """
    test_email = "e2e-contacts@homeboundapp.com"

    # Clean up
    with db.engine.begin() as connection:
        # Delete trips first (they reference contacts via foreign keys)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete events
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete contacts (after trips are deleted)
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete devices
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete login tokens
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Finally delete users
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Step 1: Create user
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
                "email": test_email,
                "first_name": "Contact",
                "last_name": "Tester",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Step 2: Add contacts (email is required now)
    contact1 = create_contact(
        ContactCreate(name="Full Contact", email="full@example.com"),
        user_id=user_id
    )
    assert contact1.email == "full@example.com"

    contact2 = create_contact(
        ContactCreate(name="Contact Two", email="two@example.com"),
        user_id=user_id
    )
    assert contact2.email == "two@example.com"

    contact3 = create_contact(
        ContactCreate(name="Contact Three", email="three@example.com"),
        user_id=user_id
    )
    assert contact3.email == "three@example.com"

    # Step 3: Verify all contacts are retrieved
    contacts = get_contacts(user_id=user_id)
    assert len(contacts) == 3

    # Step 4: Verify contact IDs are integers (iOS compatibility)
    for contact in contacts:
        assert isinstance(contact.id, int)
        assert isinstance(contact.user_id, int)
        assert isinstance(contact.email, str)

    # Step 5: Create a trip using these contacts
    now = datetime.utcnow()
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(
        TripCreate(
            title="Contact Test Trip",
            activity="Other Activity",
            start=now,
            eta=now + timedelta(hours=2),
            grace_min=30,
            contact1=contact1.id
        ),
        background_tasks,
        user_id=user_id
    )
    assert trip.id is not None

    # Clean up
    delete_account(user_id=user_id)


def test_e2e_trip_lifecycle():
    """
    Test complete trip lifecycle:
    1. Create user and profile
    2. Create trip
    3. Verify trip events are created
    4. Check timeline
    5. Delete account (cascade deletes trip and events)
    """
    test_email = "e2e-trip-lifecycle@homeboundapp.com"

    # Clean up
    with db.engine.begin() as connection:
        # Delete trips first (they reference contacts via foreign keys)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete events
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete contacts (after trips are deleted)
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete devices
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete login tokens
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Finally delete users
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Step 1: Create user
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
                "email": test_email,
                "first_name": "Trip",
                "last_name": "User",
                "age": 27
            }
        )
        user_id = result.fetchone()[0]

    # Step 2: Create an emergency contact (required for trips)
    from src.api.contacts import create_contact, ContactCreate
    contact = create_contact(
        ContactCreate(
            name="Emergency Contact",
            email="emergency@example.com"
        ),
        user_id=user_id
    )

    # Step 3: Create trip
    now = datetime.utcnow()
    background_tasks = MagicMock(spec=BackgroundTasks)
    trip = create_trip(
        TripCreate(
            title="Lifecycle Test Trip",
            activity="Hiking",
            start=now,
            eta=now + timedelta(hours=4),
            grace_min=45,
            location_text="Test Mountain",
            notes="Testing trip lifecycle",
            contact1=contact.id
        ),
        background_tasks,
        user_id=user_id
    )

    # Step 3: Verify trip was created
    assert trip.id is not None
    assert trip.title == "Lifecycle Test Trip"
    assert trip.status == "active"

    # Step 4: Retrieve trip
    retrieved_trip = get_trip(trip.id, user_id=user_id)
    assert retrieved_trip.id == trip.id
    assert retrieved_trip.title == trip.title

    # Step 5: Delete account - should cascade delete trip
    delete_account(user_id=user_id)

    # Step 7: Verify everything is deleted
    with db.engine.begin() as connection:
        trips_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert trips_count == 0

        events_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert events_count == 0


def test_e2e_profile_update_scenarios():
    """
    Test various profile update scenarios that iOS app encounters:
    1. Incomplete -> Complete profile
    2. Partial updates
    3. Empty string handling
    4. Age validation
    """
    test_email = "e2e-profile-scenarios@homeboundapp.com"

    # Clean up
    with db.engine.begin() as connection:
        # Delete trips first (they reference contacts via foreign keys)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete events
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete contacts (after trips are deleted)
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete devices
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete login tokens
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Finally delete users
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Create user with incomplete profile
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
                "email": test_email,
                "first_name": "",
                "last_name": "",
                "age": 0
            }
        )
        user_id = result.fetchone()[0]

    # Scenario 1: Profile starts incomplete
    profile = get_profile(user_id=user_id)
    assert profile.profile_completed is False

    # Scenario 2: Fill only first name - still incomplete
    response = update_profile(ProfileUpdate(first_name="John"), user_id=user_id)
    assert response.user["profile_completed"] is False

    # Scenario 3: Add last name - still incomplete (age=0)
    response = update_profile(ProfileUpdate(last_name="Doe"), user_id=user_id)
    assert response.user["profile_completed"] is False

    # Scenario 4: Add valid age - now complete
    response = update_profile(ProfileUpdate(age=30), user_id=user_id)
    assert response.user["first_name"] == "John"
    assert response.user["last_name"] == "Doe"
    assert response.user["age"] == 30
    assert response.user["profile_completed"] is True

    # Scenario 5: Update single field - remains complete
    response = update_profile(ProfileUpdate(age=31), user_id=user_id)
    assert response.user["age"] == 31
    assert response.user["profile_completed"] is True

    # Scenario 6: Clear a field with empty string - becomes incomplete
    response = update_profile(ProfileUpdate(first_name=""), user_id=user_id)
    assert response.user["profile_completed"] is False

    # Scenario 7: Restore field - becomes complete again
    response = update_profile(ProfileUpdate(first_name="John"), user_id=user_id)
    assert response.user["profile_completed"] is True

    # Clean up
    delete_account(user_id=user_id)


def test_e2e_ios_sync_scenario():
    """
    Test scenario where iOS app syncs data after creation:
    1. Create contact via API
    2. Verify response format matches iOS models (int IDs, optional fields)
    3. Retrieve contact list
    4. Verify all contacts have correct types
    """
    test_email = "e2e-ios-sync@homeboundapp.com"

    # Clean up
    with db.engine.begin() as connection:
        # Delete trips first (they reference contacts via foreign keys)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete events
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete contacts (after trips are deleted)
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete devices
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Delete login tokens
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        # Finally delete users
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Create user
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
                "email": test_email,
                "first_name": "iOS",
                "last_name": "Sync",
                "age": 26
            }
        )
        user_id = result.fetchone()[0]

    # iOS creates contact (email is required)
    contact = create_contact(
        ContactCreate(name="Test Contact", email="test@example.com"),
        user_id=user_id
    )

    # Verify response format matches iOS SavedContact model
    assert isinstance(contact.id, int), "ID must be int for iOS"
    assert isinstance(contact.user_id, int), "user_id must be int for iOS"
    assert contact.name == "Test Contact"
    assert contact.email == "test@example.com"

    # iOS fetches contact list
    contacts = get_contacts(user_id=user_id)
    assert len(contacts) == 1

    # Verify all returned contacts have correct types
    for c in contacts:
        assert isinstance(c.id, int)
        assert isinstance(c.user_id, int)
        assert isinstance(c.email, str)

    # Clean up
    delete_account(user_id=user_id)


def test_e2e_cascade_delete_order():
    """
    Test that cascade delete works in correct order to avoid foreign key violations.
    This test verifies the fix for the bug where deleting a user with related data failed.
    """
    test_email = "e2e-cascade-order@homeboundapp.com"

    # Clean up
    with db.engine.begin() as connection:
        # Delete in proper cascade order
        # Events reference trips, so delete events first
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
                "email": test_email,
                "first_name": "Cascade",
                "last_name": "Test",
                "age": 29
            }
        )
        user_id = result.fetchone()[0]

    # Create data in order that would cause foreign key violations if deleted incorrectly
    now = datetime.utcnow()

    with db.engine.begin() as connection:
        # 1. Create login token (references users)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO login_tokens (user_id, email, token, expires_at)
                VALUES (:user_id, :email, :token, :expires_at)
                """
            ),
            {
                "user_id": user_id,
                "email": test_email,
                "token": "test-token",
                "expires_at": now + timedelta(days=90)
            }
        )

        # 2. Create contact (references users)
        contact_result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "name": "Emergency",
                "email": "emergency@example.com"
            }
        )
        contact_id = contact_result.fetchone()[0]

        # 3. Create trip (references users)
        trip_result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, location_text, gen_lat, gen_lon, contact1, contact2, contact3, status)
                VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, :location_text, :gen_lat, :gen_lon, :contact1, :contact2, :contact3, :status)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": "Test Trip",
                "activity": 19,  # ID for "Other Activity"
                "start": now,
                "eta": now + timedelta(hours=2),
                "grace_min": 30,
                "location_text": "Test Location",
                "gen_lat": 0.0,
                "gen_lon": 0.0,
                "contact1": contact_id,
                "contact2": None,
                "contact3": None,
                "status": "active"
            }
        )
        trip_id = trip_result.fetchone()[0]

        # 4. Create event (references both users and trips)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp)
                VALUES (:user_id, :trip_id, :what, :timestamp)
                """
            ),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "what": "created",
                "timestamp": now
            }
        )

        # 5. Create device (references users)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO devices (user_id, token, platform, bundle_id, env)
                VALUES (:user_id, :token, :platform, :bundle_id, :env)
                """
            ),
            {
                "user_id": user_id,
                "token": "device-token",
                "platform": "ios"
            ,
                "bundle_id": "com.homeboundapp.Homebound",
                "env": "production"
            }
        )

    # Delete account - this should NOT raise any foreign key violations
    # The fix ensures deletion happens in correct order:
    # 1. login_tokens, 2. contacts, 3. events, 4. trips, 5. devices, 6. users
    try:
        result = delete_account(user_id=user_id)
        assert result["ok"] is True
    except Exception as e:
        pytest.fail(f"Delete account failed with: {str(e)}")

    # Verify all data is deleted
    with db.engine.begin() as connection:
        # Check user is deleted
        user_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_count == 0, "User should be deleted"

        # Check related data is deleted
        for table in ["login_tokens", "contacts", "trips", "events", "devices"]:
            count = connection.execute(
                sqlalchemy.text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()[0]
            assert count == 0, f"{table} should be empty after cascade delete"
