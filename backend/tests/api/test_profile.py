"""Tests for profile API endpoints"""
import pytest
from src import database as db
import sqlalchemy
from src.api.profile import (
    ProfileUpdate,
    ProfileResponse,
    get_profile,
    update_profile,
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

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_profile():
    """Test updating user profile"""
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
    updated = update_profile(update_data, user_id=user_id)

    assert updated.first_name == "Updated"
    assert updated.last_name == "Profile"
    assert updated.age == 26
    assert updated.email == test_email  # Email should not change

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_update_profile_partial():
    """Test updating only some profile fields"""
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
    updated = update_profile(update_data, user_id=user_id)

    assert updated.first_name == "Partial"  # Should remain unchanged
    assert updated.last_name == "Update"  # Should remain unchanged
    assert updated.age == 31  # Should be updated

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
