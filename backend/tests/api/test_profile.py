"""Tests for profile API endpoints"""
import pytest
from src import database as db
import sqlalchemy
from src.api.profile import (
    ProfileUpdate,
    ProfileResponse,
    ProfileUpdateResponse,
    get_profile,
    update_profile,
    patch_profile,
    delete_account
)
from fastapi import HTTPException


def test_get_profile():
    """Test retrieving user profile"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Profile",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Get profile
    profile = get_profile(user_id=user_id)

    assert isinstance(profile, ProfileResponse)
    assert profile.id == user_id
    assert profile.email == test_email
    assert profile.first_name == "Profile"
    assert profile.last_name == "Test"
    assert profile.age == 30
    assert profile.profile_completed is True  # All fields filled

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_profile():
    """Test updating user profile with PUT endpoint (returns ProfileUpdateResponse)"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Original",
                "last_name": "Name",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Update profile
    update_data = ProfileUpdate(
        first_name="Updated",
        last_name="Profile",
        age=26
    )
    response = update_profile(update_data, user_id=user_id)

    # Check response format (new format for iOS compatibility)
    assert isinstance(response, ProfileUpdateResponse)
    assert response.ok is True
    assert response.user is not None
    assert response.user["first_name"] == "Updated"
    assert response.user["last_name"] == "Profile"
    assert response.user["age"] == 26
    assert response.user["profile_completed"] is True  # All fields filled

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_profile_partial():
    """Test updating only some profile fields with PUT endpoint"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Partial",
                "last_name": "Update",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Update only age
    update_data = ProfileUpdate(age=31)
    response = update_profile(update_data, user_id=user_id)

    assert response.ok is True
    assert response.user["first_name"] == "Partial"  # Should remain unchanged
    assert response.user["last_name"] == "Update"  # Should remain unchanged
    assert response.user["age"] == 31  # Should be updated
    assert response.user["profile_completed"] is True  # Still complete

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_delete_account():
    """Test deleting user account"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Delete",
                "last_name": "Account",
                "age": 35
            }
        )
        user_id = result.fetchone()[0]

    # Delete account
    result = delete_account(user_id=user_id)
    assert result["ok"] is True
    assert "deleted" in result["message"].lower()

    # Verify user is deleted
    with pytest.raises(HTTPException) as exc_info:
        get_profile(user_id=user_id)
    assert exc_info.value.status_code == 404


def test_get_nonexistent_profile():
    """Test retrieving profile for non-existent user"""
    with pytest.raises(HTTPException) as exc_info:
        get_profile(user_id=999999)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_patch_profile():
    """Test PATCH endpoint for partial profile updates"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Patch",
                "last_name": "Test",
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

    # Update only first_name via PATCH
    update_data = ProfileUpdate(first_name="NewFirst")
    response = patch_profile(update_data, user_id=user_id)

    assert response["ok"] is True
    assert "successfully" in response["message"].lower()

    # Verify the update
    profile = get_profile(user_id=user_id)
    assert profile.first_name == "NewFirst"
    assert profile.last_name == "Test"  # Unchanged
    assert profile.age == 28  # Unchanged

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_profile_completed_logic():
    """Test profile_completed flag is set correctly"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with incomplete profile (empty first_name)
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

    # Profile should be incomplete
    update_data = ProfileUpdate()  # No updates
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is False

    # Update to complete profile
    update_data = ProfileUpdate(first_name="Complete", last_name="User", age=25)
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is True

    # Update to make incomplete again (age = 0)
    update_data = ProfileUpdate(age=0)
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is False

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_onboarding_flow_simulation():
    """Test the complete onboarding flow as iOS app would use it"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Step 1: User created via auto-registration (from magic link request)
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

    # Step 2: User fills out onboarding with first_name, last_name, age
    update_data = ProfileUpdate(
        first_name="John",
        last_name="Doe",
        age=30
    )
    response = update_profile(update_data, user_id=user_id)

    # Verify iOS-compatible response
    assert response.ok is True
    assert response.user["first_name"] == "John"
    assert response.user["last_name"] == "Doe"
    assert response.user["age"] == 30
    assert response.user["profile_completed"] is True

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_only_first_name():
    """Test updating only first_name leaves last_name intact"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Original",
                "last_name": "LastName",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Update only first_name
    update_data = ProfileUpdate(first_name="NewFirst")
    response = update_profile(update_data, user_id=user_id)

    assert response.user["first_name"] == "NewFirst"
    assert response.user["last_name"] == "LastName"  # Should remain unchanged
    assert response.user["age"] == 25

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_only_last_name():
    """Test updating only last_name leaves first_name intact"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "FirstName",
                "last_name": "Original",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Update only last_name
    update_data = ProfileUpdate(last_name="NewLast")
    response = update_profile(update_data, user_id=user_id)

    assert response.user["first_name"] == "FirstName"  # Should remain unchanged
    assert response.user["last_name"] == "NewLast"
    assert response.user["age"] == 25

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_empty_strings_mark_profile_incomplete():
    """Test that empty strings in first/last name mark profile as incomplete"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Valid",
                "last_name": "Name",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Update first_name to empty string
    update_data = ProfileUpdate(first_name="")
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is False

    # Restore first_name but set last_name to empty
    update_data = ProfileUpdate(first_name="Valid", last_name="")
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is False

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_zero_age_marks_profile_incomplete():
    """Test that age=0 marks profile as incomplete"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

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
                "first_name": "Test",
                "last_name": "User",
                "age": 0
            }
        )
        user_id = result.fetchone()[0]

    # Profile with age=0 should be incomplete
    update_data = ProfileUpdate()  # No changes
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is False

    # Update to valid age
    update_data = ProfileUpdate(age=25)
    response = update_profile(update_data, user_id=user_id)
    assert response.user["profile_completed"] is True

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_delete_account_with_contacts():
    """Test deleting account with saved contacts (cascade delete)"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
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
                "first_name": "Delete",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

        # Create contacts for this user
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES
                    (:user_id, :name1, :email1),
                    (:user_id, :name2, :email2)
                """
            ),
            {
                "user_id": user_id,
                "name1": "Contact One",
                "email1": "test@homeboundapp.com",
                "name2": "Contact Two",
                "email2": "test@homeboundapp.com"
            }
        )

    # Delete account - should cascade delete contacts
    result = delete_account(user_id=user_id)
    assert result["ok"] is True

    # Verify user and contacts are both deleted
    with db.engine.begin() as connection:
        user_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_check == 0

        contacts_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert contacts_check == 0


def test_delete_account_with_trips_and_events():
    """Test deleting account with trips and events (cascade delete)"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up with cascade deletion order
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
                "first_name": "Delete",
                "last_name": "Trips",
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

        # Create contacts for the trip
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
                "name": "Emergency Contact",
                "email": "test@homeboundapp.com"
            }
        )
        contact_id = contact_result.fetchone()[0]

        # Create a trip
        from datetime import datetime, timedelta
        now = datetime.utcnow()
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
                "activity": 1,  # ID for "Hiking"
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

        # Create events for this trip
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

    # Delete account - should cascade delete trips and events
    result = delete_account(user_id=user_id)
    assert result["ok"] is True

    # Verify everything is deleted
    with db.engine.begin() as connection:
        user_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_check == 0

        trips_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert trips_check == 0

        events_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert events_check == 0


def test_delete_account_with_devices():
    """Test deleting account with registered devices (cascade delete)"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
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
                "first_name": "Delete",
                "last_name": "Devices",
                "age": 32
            }
        )
        user_id = result.fetchone()[0]

        # Create devices
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO devices (user_id, token, platform, bundle_id, env)
                VALUES (:user_id, :token1, :platform1, :bundle_id1, :env1),
                    (:user_id, :token2, :platform2, :bundle_id2, :env2)
                """
            ),
            {
                "user_id": user_id,
                "token1": "device-token-1",
                "platform1": "ios",
                "bundle_id1": "com.homeboundapp.Homebound",
                "env1": "production",
                "token2": "device-token-2",
                "platform2": "ios",
                "bundle_id2": "com.homeboundapp.Homebound",
                "env2": "production"
            }
        )

    # Delete account - should cascade delete devices
    result = delete_account(user_id=user_id)
    assert result["ok"] is True

    # Verify everything is deleted
    with db.engine.begin() as connection:
        user_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_check == 0

        devices_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert devices_check == 0


def test_delete_account_with_login_tokens():
    """Test deleting account with login tokens (cascade delete)"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
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
                "first_name": "Delete",
                "last_name": "Tokens",
                "age": 27
            }
        )
        user_id = result.fetchone()[0]

        # Create login tokens
        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(days=90)
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
                "token": "test-refresh-token",
                "expires_at": expires
            }
        )

    # Delete account - should cascade delete login tokens
    result = delete_account(user_id=user_id)
    assert result["ok"] is True

    # Verify everything is deleted
    with db.engine.begin() as connection:
        user_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_check == 0

        tokens_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM login_tokens WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert tokens_check == 0


def test_delete_account_full_cascade():
    """Test deleting account with ALL related data (comprehensive cascade delete test)"""
    test_email = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up with cascade deletion order
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
                "first_name": "Delete",
                "last_name": "Everything",
                "age": 29
            }
        )
        user_id = result.fetchone()[0]

        # Create ALL types of related data
        from datetime import datetime, timedelta
        now = datetime.utcnow()

        # Login tokens
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
                "token": "full-test-token",
                "expires_at": now + timedelta(days=90)
            }
        )

        # Contacts
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
                "name": "Emergency Contact",
                "email": "test@homeboundapp.com"
            }
        )
        contact_id = contact_result.fetchone()[0]

        # Trip
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
                "title": "Full Test Trip",
                "activity": 19,  # ID for "Other Activity"
                "start": now,
                "eta": now + timedelta(hours=3),
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

        # Events
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

        # Devices
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO devices (user_id, token, platform, bundle_id, env)
                VALUES (:user_id, :token, :platform, :bundle_id, :env)
                """
            ),
            {
                "user_id": user_id,
                "token": "full-test-device-token",
                "platform": "ios"
            ,
                "bundle_id": "com.homeboundapp.Homebound",
                "env": "production"
            }
        )

    # Delete account - should cascade delete EVERYTHING
    result = delete_account(user_id=user_id)
    assert result["ok"] is True

    # Verify EVERYTHING is deleted in the correct order
    with db.engine.begin() as connection:
        # Check user
        user_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert user_check == 0, "User should be deleted"

        # Check login_tokens
        tokens_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM login_tokens WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert tokens_check == 0, "Login tokens should be deleted"

        # Check contacts
        contacts_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert contacts_check == 0, "Contacts should be deleted"

        # Check events
        events_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert events_check == 0, "Events should be deleted"

        # Check trips
        trips_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert trips_check == 0, "Trips should be deleted"

        # Check devices
        devices_check = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone()[0]
        assert devices_check == 0, "Devices should be deleted"
