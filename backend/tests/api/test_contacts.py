"""Tests for contacts API endpoints"""
import pytest
import sqlalchemy
from fastapi import HTTPException

from src import database as db
from src.api.contacts import (
    Contact,
    ContactCreate,
    ContactUpdate,
    create_contact,
    delete_contact,
    get_contact,
    get_contacts,
    update_contact,
)


def test_create_and_get_contact():
    """Test creating and retrieving a contact"""
    # Create test user first
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up any existing data
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
        email="test@homeboundapp.com"
    )

    contact = create_contact(contact_data, user_id=user_id)

    assert isinstance(contact, Contact)
    assert contact.name == "John Doe"
    assert contact.email == "test@homeboundapp.com"
    assert contact.user_id == user_id

    # Get the contact
    retrieved = get_contact(contact.id, user_id=user_id)
    assert retrieved.id == contact.id
    assert retrieved.name == contact.name
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
    test_email = "test@homeboundapp.com"
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
    create_contact(
        ContactCreate(name="Alice Smith", email="test@homeboundapp.com"),
        user_id=user_id
    )
    create_contact(
        ContactCreate(name="Bob Jones", email="test@homeboundapp.com"),
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
    test_email = "test@homeboundapp.com"
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
        ContactCreate(name="Original Name", email="test@homeboundapp.com"),
        user_id=user_id
    )

    # Update the contact
    update_data = ContactUpdate(name="New Name", email="test@homeboundapp.com")
    updated = update_contact(contact.id, update_data, user_id=user_id)

    assert updated.name == "New Name"
    assert updated.email == "test@homeboundapp.com"

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
    test_email = "test@homeboundapp.com"
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
        ContactCreate(name="To Delete", email="test@homeboundapp.com"),
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


def test_contact_id_is_integer():
    """Test that contact ID is returned as integer (not string)"""
    test_email = "test@homeboundapp.com"
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
                "first_name": "ID",
                "last_name": "Test",
                "age": 29
            }
        )
        user_id = result.fetchone()[0]

    # Create contact
    contact = create_contact(
        ContactCreate(name="Test Contact", email="test@homeboundapp.com"),
        user_id=user_id
    )

    # Verify ID is integer
    assert isinstance(contact.id, int), f"Contact ID should be int, got {type(contact.id)}"
    assert isinstance(contact.user_id, int), f"User ID should be int, got {type(contact.user_id)}"

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


def test_user_cannot_access_other_users_contacts():
    """Test that users cannot access contacts belonging to other users"""
    test_email1 = "test@homeboundapp.com"
    test_email2 = "test@homeboundapp.com"

    with db.engine.begin() as connection:
        # Clean up
        for email in [test_email1, test_email2]:
            connection.execute(
                sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": email}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": email}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": email}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": email}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": email}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM users WHERE email = :email"),
                {"email": email}
            )

        # Create two users
        result1 = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
                RETURNING id
                """
            ),
            {
                "email": test_email1,
                "first_name": "User",
                "last_name": "One",
                "age": 30
            }
        )
        user1_id = result1.fetchone()[0]

        result2 = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
                RETURNING id
                """
            ),
            {
                "email": test_email2,
                "first_name": "User",
                "last_name": "Two",
                "age": 28
            }
        )
        user2_id = result2.fetchone()[0]

    # User 1 creates a contact
    contact1 = create_contact(
        ContactCreate(name="User1 Contact", email="test@homeboundapp.com"),
        user_id=user1_id
    )

    # User 2 tries to access User 1's contact - should fail
    with pytest.raises(HTTPException) as exc_info:
        get_contact(contact1.id, user_id=user2_id)
    assert exc_info.value.status_code == 404

    # User 2 tries to update User 1's contact - should fail
    with pytest.raises(HTTPException) as exc_info:
        update_contact(contact1.id, ContactUpdate(name="Hacked"), user_id=user2_id)
    assert exc_info.value.status_code == 404

    # User 2 tries to delete User 1's contact - should fail
    with pytest.raises(HTTPException) as exc_info:
        delete_contact(contact1.id, user_id=user2_id)
    assert exc_info.value.status_code == 404

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (:user1_id, :user2_id)"),
            {"user1_id": user1_id, "user2_id": user2_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id IN (:user1_id, :user2_id)"),
            {"user1_id": user1_id, "user2_id": user2_id}
        )


def _create_test_user_and_contacts(connection, email: str, num_contacts: int = 3):
    """Helper to create a test user with contacts."""
    # Clean up existing data
    connection.execute(
        sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM users WHERE email = :email"),
        {"email": email}
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
        {"email": email, "first_name": "Test", "last_name": "User", "age": 30}
    )
    user_id = result.fetchone()[0]

    # Create contacts
    contact_ids = []
    for i in range(num_contacts):
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {"user_id": user_id, "name": f"Contact {i+1}", "email": f"contact{i+1}@test.com"}
        )
        contact_ids.append(result.fetchone()[0])

    return user_id, contact_ids


def _get_activity_id(connection) -> int:
    """Get the first activity ID for test trips."""
    result = connection.execute(
        sqlalchemy.text("SELECT id FROM activities LIMIT 1")
    ).fetchone()
    return result[0]


def _ensure_deleted_contact_exists(connection):
    """Ensure the DELETED placeholder contact (id=1) exists."""
    existing = connection.execute(
        sqlalchemy.text("SELECT id FROM contacts WHERE id = 1")
    ).fetchone()

    if not existing:
        # Create a system user (id=1) if it doesn't exist
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (id, email, first_name, last_name, age)
                VALUES (1, 'system@homeboundapp.com', 'System', 'User', 0)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        # Create the DELETED placeholder contact
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (id, user_id, name, email)
                VALUES (1, 1, 'DELETED', 'DELETED')
                ON CONFLICT (id) DO NOTHING
                """
            )
        )


def _create_test_trip(connection, user_id: int, activity_id: int, contact1: int,
                      contact2: int | None = None, contact3: int | None = None,
                      status: str = "completed"):
    """Helper to create a test trip."""
    result = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO trips (
                user_id, title, start, eta, activity, grace_min,
                location_text, gen_lat, gen_lon, contact1, contact2, contact3, status
            )
            VALUES (
                :user_id, :title, NOW(), NOW() + interval '2 hours', :activity, 30,
                'Test Location', 0.0, 0.0, :contact1, :contact2, :contact3, :status
            )
            RETURNING id
            """
        ),
        {
            "user_id": user_id,
            "title": "Test Trip",
            "activity": activity_id,
            "contact1": contact1,
            "contact2": contact2,
            "contact3": contact3,
            "status": status,
        }
    )
    return result.fetchone()[0]


def test_cannot_delete_contact_used_by_active_trip():
    """Test that deleting a contact used by an active trip fails with 409."""
    test_email = "trip_test@homeboundapp.com"

    with db.engine.begin() as connection:
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 1)
        activity_id = _get_activity_id(connection)
        _create_test_trip(connection, user_id, activity_id, contact_ids[0], status="active")

    # Try to delete the contact - should fail
    with pytest.raises(HTTPException) as exc_info:
        delete_contact(contact_ids[0], user_id=user_id)

    assert exc_info.value.status_code == 409
    assert "Cannot delete contact" in exc_info.value.detail

    # Clean up
    with db.engine.begin() as connection:
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


def test_cannot_delete_contact_used_by_planned_trip():
    """Test that deleting a contact used by a planned trip fails with 409."""
    test_email = "planned_trip_test@homeboundapp.com"

    with db.engine.begin() as connection:
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 1)
        activity_id = _get_activity_id(connection)
        _create_test_trip(connection, user_id, activity_id, contact_ids[0], status="planned")

    # Try to delete the contact - should fail
    with pytest.raises(HTTPException) as exc_info:
        delete_contact(contact_ids[0], user_id=user_id)

    assert exc_info.value.status_code == 409
    assert "Cannot delete contact" in exc_info.value.detail

    # Clean up
    with db.engine.begin() as connection:
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


def test_delete_only_contact_on_completed_trip_replaces_with_deleted():
    """Test that deleting the only contact on a completed trip replaces it with DELETED placeholder."""
    test_email = "only_contact_test@homeboundapp.com"

    with db.engine.begin() as connection:
        _ensure_deleted_contact_exists(connection)
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 1)
        activity_id = _get_activity_id(connection)
        # Create a completed trip with only contact1 (no contact2 or contact3)
        trip_id = _create_test_trip(connection, user_id, activity_id, contact_ids[0], status="completed")

    # Delete the only contact - should succeed
    result = delete_contact(contact_ids[0], user_id=user_id)
    assert result["ok"] is True

    # Verify contact1 is replaced with DELETED placeholder (id=1)
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text("SELECT contact1, contact2, contact3 FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        assert trip.contact1 == 1, "contact1 should be replaced with DELETED placeholder (id=1)"

    # Clean up
    with db.engine.begin() as connection:
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


def test_delete_contact1_replaces_with_deleted_placeholder():
    """Test that deleting contact1 replaces it with DELETED placeholder (id=1)."""
    test_email = "replace_contact1_test@homeboundapp.com"

    with db.engine.begin() as connection:
        _ensure_deleted_contact_exists(connection)
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 3)
        activity_id = _get_activity_id(connection)
        trip_id = _create_test_trip(
            connection, user_id, activity_id,
            contact1=contact_ids[0],
            contact2=contact_ids[1],
            contact3=contact_ids[2],
            status="completed"
        )

    # Delete contact1
    result = delete_contact(contact_ids[0], user_id=user_id)
    assert result["ok"] is True

    # Verify contact1 is replaced with DELETED placeholder (id=1)
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text("SELECT contact1, contact2, contact3 FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        assert trip.contact1 == 1, "contact1 should be replaced with DELETED placeholder (id=1)"
        assert trip.contact2 == contact_ids[1], "contact2 should be unchanged"
        assert trip.contact3 == contact_ids[2], "contact3 should be unchanged"

    # Clean up
    with db.engine.begin() as connection:
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


def test_delete_contact2_sets_null():
    """Test that deleting contact2 sets it to NULL."""
    test_email = "null_contact2_test@homeboundapp.com"

    with db.engine.begin() as connection:
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 3)
        activity_id = _get_activity_id(connection)
        trip_id = _create_test_trip(
            connection, user_id, activity_id,
            contact1=contact_ids[0],
            contact2=contact_ids[1],
            contact3=contact_ids[2],
            status="completed"
        )

    # Delete contact2
    result = delete_contact(contact_ids[1], user_id=user_id)
    assert result["ok"] is True

    # Verify contact2 is set to NULL
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text("SELECT contact1, contact2, contact3 FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        assert trip.contact1 == contact_ids[0], "contact1 should be unchanged"
        assert trip.contact2 is None, "contact2 should be NULL"
        assert trip.contact3 == contact_ids[2], "contact3 should be unchanged"

    # Clean up
    with db.engine.begin() as connection:
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


def test_delete_contact3_nulls_it_out():
    """Test that deleting contact3 just sets it to NULL."""
    test_email = "delete_contact3_test@homeboundapp.com"

    with db.engine.begin() as connection:
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 3)
        activity_id = _get_activity_id(connection)
        trip_id = _create_test_trip(
            connection, user_id, activity_id,
            contact1=contact_ids[0],
            contact2=contact_ids[1],
            contact3=contact_ids[2],
            status="completed"
        )

    # Delete contact3
    result = delete_contact(contact_ids[2], user_id=user_id)
    assert result["ok"] is True

    # Verify: contact1 and contact2 unchanged, contact3 is NULL
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text("SELECT contact1, contact2, contact3 FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        assert trip.contact1 == contact_ids[0], "contact1 should be unchanged"
        assert trip.contact2 == contact_ids[1], "contact2 should be unchanged"
        assert trip.contact3 is None, "contact3 should be NULL"

    # Clean up
    with db.engine.begin() as connection:
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


def test_delete_contact_not_used_by_any_trip():
    """Test that deleting a contact not used by any trip succeeds."""
    test_email = "unused_contact_test@homeboundapp.com"

    with db.engine.begin() as connection:
        user_id, contact_ids = _create_test_user_and_contacts(connection, test_email, 2)
        activity_id = _get_activity_id(connection)
        # Only use contact1 in the trip
        _create_test_trip(
            connection, user_id, activity_id,
            contact1=contact_ids[0],
            status="completed"
        )

    # Delete contact2 (not used by any trip) - should succeed
    result = delete_contact(contact_ids[1], user_id=user_id)
    assert result["ok"] is True

    # Verify contact2 is deleted
    with pytest.raises(HTTPException) as exc_info:
        get_contact(contact_ids[1], user_id=user_id)
    assert exc_info.value.status_code == 404

    # Clean up
    with db.engine.begin() as connection:
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
