"""Tests for profile API endpoints"""
import pytest
import sqlalchemy
from fastapi import HTTPException

from src import database as db
from src.api.profile import (
    ProfileResponse,
    ProfileUpdate,
    ProfileUpdateResponse,
    delete_account,
    export_user_data,
    get_profile,
    patch_profile,
    update_profile,
)


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


def test_export_user_data_basic():
    """Test exporting user data with just profile (no trips or contacts)"""
    test_email = "export-test@homeboundapp.com"

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
                "first_name": "Export",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Export data
    export = export_user_data(user_id=user_id)

    # Verify structure
    assert "exported_at" in export
    assert "profile" in export
    assert "trips" in export
    assert "contacts" in export
    assert "total_trips" in export
    assert "total_contacts" in export

    # Verify profile data
    assert export["profile"]["id"] == user_id
    assert export["profile"]["email"] == test_email
    assert export["profile"]["first_name"] == "Export"
    assert export["profile"]["last_name"] == "Test"
    assert export["profile"]["age"] == 30

    # Verify counts
    assert export["total_trips"] == 0
    assert export["total_contacts"] == 0
    assert len(export["trips"]) == 0
    assert len(export["contacts"]) == 0

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_export_user_data_with_contacts():
    """Test exporting user data with contacts"""
    test_email = "export-contacts@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
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
                "first_name": "Export",
                "last_name": "Contacts",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

        # Create contacts
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES
                    (:user_id, 'Contact One', 'contact1@test.com'),
                    (:user_id, 'Contact Two', 'contact2@test.com')
                """
            ),
            {"user_id": user_id}
        )

    # Export data
    export = export_user_data(user_id=user_id)

    # Verify contacts
    assert export["total_contacts"] == 2
    assert len(export["contacts"]) == 2

    contact_names = [c["name"] for c in export["contacts"]]
    assert "Contact One" in contact_names
    assert "Contact Two" in contact_names

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_export_user_data_with_trips():
    """Test exporting user data with trips"""
    test_email = "export-trips@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
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
                "first_name": "Export",
                "last_name": "Trips",
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

        # Create a contact for the trip
        contact_result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, 'Emergency Contact', 'emergency@test.com')
                RETURNING id
                """
            ),
            {"user_id": user_id}
        )
        contact_id = contact_result.fetchone()[0]

        # Create trips
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, location_text, gen_lat, gen_lon, contact1, contact2, contact3, status)
                VALUES
                    (:user_id, 'Morning Hike', 1, :start1, :eta1, 30, 'Mountain Trail', 37.7749, -122.4194, :contact_id, NULL, NULL, 'completed'),
                    (:user_id, 'Evening Run', 3, :start2, :eta2, 15, 'Park Loop', 37.7849, -122.4094, :contact_id, NULL, NULL, 'active')
                """
            ),
            {
                "user_id": user_id,
                "start1": now - timedelta(days=1),
                "eta1": now - timedelta(days=1) + timedelta(hours=2),
                "start2": now,
                "eta2": now + timedelta(hours=1),
                "contact_id": contact_id
            }
        )

    # Export data
    export = export_user_data(user_id=user_id)

    # Verify trips
    assert export["total_trips"] == 2
    assert len(export["trips"]) == 2

    trip_titles = [t["title"] for t in export["trips"]]
    assert "Morning Hike" in trip_titles
    assert "Evening Run" in trip_titles

    # Verify trip has expected fields
    trip = export["trips"][0]
    assert "id" in trip
    assert "title" in trip
    assert "activity" in trip or "activity_name" in trip
    assert "status" in trip
    assert "location_text" in trip

    # Clean up
    with db.engine.begin() as connection:
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


def test_export_user_data_nonexistent_user():
    """Test exporting data for non-existent user returns 404"""
    with pytest.raises(HTTPException) as exc_info:
        export_user_data(user_id=999999)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_get_profile_includes_notification_preferences():
    """Test that get_profile returns notification preferences"""
    test_email = "notification-prefs@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with default notification preferences
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
                "first_name": "Notify",
                "last_name": "Test",
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

    # Get profile
    profile = get_profile(user_id=user_id)

    # Verify notification preferences are included with default values (True)
    assert hasattr(profile, 'notify_trip_reminders')
    assert hasattr(profile, 'notify_checkin_alerts')
    assert profile.notify_trip_reminders is True
    assert profile.notify_checkin_alerts is True

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_notification_preferences():
    """Test updating notification preferences via PUT endpoint"""
    test_email = "update-notify@homeboundapp.com"

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
                "first_name": "Update",
                "last_name": "Notify",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Disable trip reminders
    update_data = ProfileUpdate(notify_trip_reminders=False)
    response = update_profile(update_data, user_id=user_id)

    assert response.ok is True
    assert response.user["notify_trip_reminders"] is False
    assert response.user["notify_checkin_alerts"] is True  # Should remain unchanged

    # Disable check-in alerts
    update_data = ProfileUpdate(notify_checkin_alerts=False)
    response = update_profile(update_data, user_id=user_id)

    assert response.user["notify_trip_reminders"] is False  # Should remain unchanged
    assert response.user["notify_checkin_alerts"] is False

    # Re-enable both
    update_data = ProfileUpdate(notify_trip_reminders=True, notify_checkin_alerts=True)
    response = update_profile(update_data, user_id=user_id)

    assert response.user["notify_trip_reminders"] is True
    assert response.user["notify_checkin_alerts"] is True

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_patch_notification_preferences():
    """Test updating notification preferences via PATCH endpoint"""
    test_email = "patch-notify@homeboundapp.com"

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
                "last_name": "Notify",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Disable trip reminders via PATCH
    update_data = ProfileUpdate(notify_trip_reminders=False)
    response = patch_profile(update_data, user_id=user_id)

    assert response["ok"] is True

    # Verify the update persisted
    profile = get_profile(user_id=user_id)
    assert profile.notify_trip_reminders is False
    assert profile.notify_checkin_alerts is True  # Should remain unchanged

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_profile_with_notification_prefs_and_other_fields():
    """Test updating notification preferences along with other profile fields"""
    test_email = "combo-update@homeboundapp.com"

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
                "first_name": "Combo",
                "last_name": "Update",
                "age": 22
            }
        )
        user_id = result.fetchone()[0]

    # Update profile fields and notification preferences together
    update_data = ProfileUpdate(
        first_name="Updated",
        age=23,
        notify_trip_reminders=False,
        notify_checkin_alerts=False
    )
    response = update_profile(update_data, user_id=user_id)

    assert response.ok is True
    assert response.user["first_name"] == "Updated"
    assert response.user["last_name"] == "Update"  # Unchanged
    assert response.user["age"] == 23
    assert response.user["notify_trip_reminders"] is False
    assert response.user["notify_checkin_alerts"] is False

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_export_user_data_full():
    """Test exporting complete user data with profile, trips, and contacts"""
    test_email = "export-full@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
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
                "first_name": "Full",
                "last_name": "Export",
                "age": 35
            }
        )
        user_id = result.fetchone()[0]

        # Create multiple contacts
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES
                    (:user_id, 'Mom', 'mom@family.com'),
                    (:user_id, 'Best Friend', 'friend@email.com'),
                    (:user_id, 'Work Contact', 'work@company.com')
                """
            ),
            {"user_id": user_id}
        )

        # Get a contact ID for trips
        contact_result = connection.execute(
            sqlalchemy.text("SELECT id FROM contacts WHERE user_id = :user_id LIMIT 1"),
            {"user_id": user_id}
        )
        contact_id = contact_result.fetchone()[0]

        # Create trips with activity join
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, location_text, gen_lat, gen_lon, contact1, contact2, contact3, status, notes)
                VALUES
                    (:user_id, 'Weekend Camping', 4, :start1, :eta1, 60, 'Yosemite National Park', 37.8651, -119.5383, :contact_id, NULL, NULL, 'completed', 'Bring extra water'),
                    (:user_id, 'City Walk', 5, :start2, :eta2, 15, 'Downtown', 37.7749, -122.4194, :contact_id, NULL, NULL, 'active', NULL)
                """
            ),
            {
                "user_id": user_id,
                "start1": now - timedelta(days=7),
                "eta1": now - timedelta(days=5),
                "start2": now,
                "eta2": now + timedelta(hours=2),
                "contact_id": contact_id
            }
        )

    # Export data
    export = export_user_data(user_id=user_id)

    # Verify complete export
    assert export["total_trips"] == 2
    assert export["total_contacts"] == 3

    # Verify profile
    assert export["profile"]["first_name"] == "Full"
    assert export["profile"]["last_name"] == "Export"

    # Verify contacts have all fields
    contact = export["contacts"][0]
    assert "id" in contact
    assert "name" in contact
    assert "email" in contact

    # Verify trips have activity info (from JOIN)
    trip = export["trips"][0]
    assert "title" in trip
    # activity_name and activity_icon come from the JOIN
    assert "activity_name" in trip or "activity" in trip

    # Clean up
    with db.engine.begin() as connection:
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


# ==================== Friend Visibility Settings Tests ====================

from src.api.profile import (
    FriendVisibilitySettings,
    get_friend_visibility,
    update_friend_visibility,
)


def test_get_friend_visibility_defaults():
    """Test that friend visibility settings have correct defaults."""
    test_email = "friend-visibility-defaults@test.com"

    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user with default settings
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
                "first_name": "Visibility",
                "last_name": "Test",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    try:
        settings = get_friend_visibility(user_id=user_id)

        assert isinstance(settings, FriendVisibilitySettings)
        # Check defaults
        assert settings.friend_share_checkin_locations is True
        assert settings.friend_share_live_location is False
        assert settings.friend_share_notes is True
        assert settings.friend_allow_update_requests is True
    finally:
        with db.engine.begin() as connection:
            connection.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_update_friend_visibility():
    """Test updating friend visibility settings."""
    test_email = "friend-visibility-update@test.com"

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
                "first_name": "Update",
                "last_name": "Visibility",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    try:
        # Update all settings
        new_settings = FriendVisibilitySettings(
            friend_share_checkin_locations=False,
            friend_share_live_location=True,
            friend_share_notes=False,
            friend_allow_update_requests=False,
            friend_share_achievements=True
        )
        result = update_friend_visibility(new_settings, user_id=user_id)

        assert result.friend_share_checkin_locations is False
        assert result.friend_share_live_location is True
        assert result.friend_share_notes is False
        assert result.friend_allow_update_requests is False

        # Verify changes persisted
        settings = get_friend_visibility(user_id=user_id)
        assert settings.friend_share_checkin_locations is False
        assert settings.friend_share_live_location is True
        assert settings.friend_share_notes is False
        assert settings.friend_allow_update_requests is False
    finally:
        with db.engine.begin() as connection:
            connection.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_update_friend_visibility_partial():
    """Test that updating some settings doesn't affect others."""
    test_email = "friend-visibility-partial@test.com"

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
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

    try:
        # First update - disable checkin locations
        settings1 = FriendVisibilitySettings(
            friend_share_checkin_locations=False,
            friend_share_live_location=False,
            friend_share_notes=True,
            friend_allow_update_requests=True,
            friend_share_achievements=True
        )
        update_friend_visibility(settings1, user_id=user_id)

        # Verify
        result = get_friend_visibility(user_id=user_id)
        assert result.friend_share_checkin_locations is False
        assert result.friend_share_live_location is False
        assert result.friend_share_notes is True
        assert result.friend_allow_update_requests is True

        # Second update - enable live location, disable notes
        settings2 = FriendVisibilitySettings(
            friend_share_checkin_locations=False,
            friend_share_live_location=True,
            friend_share_notes=False,
            friend_allow_update_requests=True,
            friend_share_achievements=True
        )
        update_friend_visibility(settings2, user_id=user_id)

        # Verify all settings are as expected
        result = get_friend_visibility(user_id=user_id)
        assert result.friend_share_checkin_locations is False
        assert result.friend_share_live_location is True
        assert result.friend_share_notes is False
        assert result.friend_allow_update_requests is True
    finally:
        with db.engine.begin() as connection:
            connection.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


def test_get_friend_visibility_nonexistent_user():
    """Test getting visibility settings for non-existent user returns 404."""
    with pytest.raises(HTTPException) as exc_info:
        get_friend_visibility(user_id=999999)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()
