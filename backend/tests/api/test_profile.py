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
    test_email = "profile-test@homeboundapp.com"
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
    test_email = "update-profile@homeboundapp.com"
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
    test_email = "partial-update@homeboundapp.com"
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
    test_email = "delete-account@homeboundapp.com"
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
    test_email = "patch-test@homeboundapp.com"
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
    test_email = "completed-test@homeboundapp.com"

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
    test_email = "onboarding-test@homeboundapp.com"

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
    test_email = "firstname-only@homeboundapp.com"

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
    test_email = "lastname-only@homeboundapp.com"

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
    test_email = "empty-strings@homeboundapp.com"

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
    test_email = "zero-age@homeboundapp.com"

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
