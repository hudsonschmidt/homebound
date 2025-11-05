"""Tests for contacts API endpoints"""
import pytest
from src import database as db
import sqlalchemy
from src.api.contacts import (
    ContactCreate,
    ContactUpdate,
    Contact,
    get_contacts,
    get_contact,
    create_contact,
    update_contact,
    delete_contact
)
from fastapi import HTTPException


def test_create_and_get_contact():
    """Test creating and retrieving a contact"""
    # Create test user first
    test_email = "contact-test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up any existing data
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
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
                "first_name": "Contact",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Create a contact
    contact_data = ContactCreate(
        name="John Doe",
        phone="+1234567890",
        email="john@example.com"
    )

    contact = create_contact(contact_data, user_id=user_id)

    assert isinstance(contact, Contact)
    assert contact.name == "John Doe"
    assert contact.phone == "+1234567890"
    assert contact.email == "john@example.com"
    assert contact.user_id == user_id

    # Get the contact
    retrieved = get_contact(contact.id, user_id=user_id)
    assert retrieved.id == contact.id
    assert retrieved.name == contact.name
    assert retrieved.phone == contact.phone
    assert retrieved.email == contact.email

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


def test_get_all_contacts():
    """Test retrieving all contacts for a user"""
    test_email = "contacts-list@homeboundapp.com"
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
                "first_name": "List",
                "last_name": "Test",
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Create multiple contacts
    contact1 = create_contact(
        ContactCreate(name="Alice Smith", phone="111", email="alice@example.com"),
        user_id=user_id
    )
    contact2 = create_contact(
        ContactCreate(name="Bob Jones", phone="222", email="bob@example.com"),
        user_id=user_id
    )

    # Get all contacts
    contacts = get_contacts(user_id=user_id)

    assert len(contacts) == 2
    assert all(isinstance(c, Contact) for c in contacts)
    contact_names = [c.name for c in contacts]
    assert "Alice Smith" in contact_names
    assert "Bob Jones" in contact_names

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


def test_update_contact():
    """Test updating a contact"""
    test_email = "update-contact@homeboundapp.com"
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
                "last_name": "Test",
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

    # Create a contact
    contact = create_contact(
        ContactCreate(name="Original Name", phone="111", email="old@example.com"),
        user_id=user_id
    )

    # Update the contact
    update_data = ContactUpdate(name="New Name", email="new@example.com")
    updated = update_contact(contact.id, update_data, user_id=user_id)

    assert updated.name == "New Name"
    assert updated.phone == "111"  # Should remain unchanged
    assert updated.email == "new@example.com"

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


def test_delete_contact():
    """Test deleting a contact"""
    test_email = "delete-contact@homeboundapp.com"
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
                "age": 35
            }
        )
        user_id = result.fetchone()[0]

    # Create a contact
    contact = create_contact(
        ContactCreate(name="To Delete", phone="999", email="delete@example.com"),
        user_id=user_id
    )

    # Delete the contact
    result = delete_contact(contact.id, user_id=user_id)
    assert result["ok"] is True

    # Verify it's deleted
    with pytest.raises(HTTPException) as exc_info:
        get_contact(contact.id, user_id=user_id)
    assert exc_info.value.status_code == 404

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_get_nonexistent_contact():
    """Test retrieving a contact that doesn't exist"""
    with pytest.raises(HTTPException) as exc_info:
        get_contact(999999, user_id=1)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_update_nonexistent_contact():
    """Test updating a contact that doesn't exist"""
    update_data = ContactUpdate(name="Doesn't Matter")
    with pytest.raises(HTTPException) as exc_info:
        update_contact(999999, update_data, user_id=1)
    assert exc_info.value.status_code == 404


def test_delete_nonexistent_contact():
    """Test deleting a contact that doesn't exist"""
    with pytest.raises(HTTPException) as exc_info:
        delete_contact(999999, user_id=1)
    assert exc_info.value.status_code == 404
