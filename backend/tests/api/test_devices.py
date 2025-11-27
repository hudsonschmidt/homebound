"""Tests for devices API endpoints"""
import pytest
from src import database as db
import sqlalchemy
from src.api.devices import (
    DeviceRegister,
    DeviceResponse,
    register_device,
    get_devices,
    delete_device,
    delete_device_by_token
)
from fastapi import HTTPException


def test_register_device():
    """Test registering a new device"""
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
                "first_name": "Device",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Register device
    device_data = DeviceRegister(
        platform="ios",
        token="test_token_123",
        bundle_id="com.homeboundapp",
        env="development"
    )

    device = register_device(device_data, user_id=user_id)

    assert isinstance(device, DeviceResponse)
    assert device.platform == "ios"
    assert device.token == "test_token_123"
    assert device.bundle_id == "com.homeboundapp"
    assert device.env == "development"

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_register_device_update_existing():
    """Test that registering the same token updates the existing device"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE token = :token"),
            {"token": "update_token_456"}
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
                "age": 25
            }
        )
        user_id = result.fetchone()[0]

    # Register device first time
    device_data = DeviceRegister(
        platform="ios",
        token="update_token_456",
        bundle_id="com.homeboundapp",
        env="development"
    )
    device1 = register_device(device_data, user_id=user_id)

    # Register same token again
    device2 = register_device(device_data, user_id=user_id)

    # Should be the same device ID (updated, not created new)
    assert device1.id == device2.id
    assert device2.token == "update_token_456"

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE token = :token"),
            {"token": "update_token_456"}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_get_devices():
    """Test retrieving all devices for a user"""
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
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

    # Register multiple devices
    register_device(
        DeviceRegister(platform="ios", token="token1", bundle_id="com.app", env="production"),
        user_id=user_id
    )
    register_device(
        DeviceRegister(platform="android", token="token2", bundle_id="com.app", env="production"),
        user_id=user_id
    )

    # Get all devices
    devices = get_devices(user_id=user_id)

    assert len(devices) == 2
    assert all(isinstance(d, DeviceResponse) for d in devices)
    tokens = [d.token for d in devices]
    assert "token1" in tokens
    assert "token2" in tokens

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_delete_device():
    """Test deleting a device by ID"""
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
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

    # Register device
    device = register_device(
        DeviceRegister(platform="ios", token="delete_token", bundle_id="com.app", env="development"),
        user_id=user_id
    )

    # Delete device
    result = delete_device(device.id, user_id=user_id)
    assert result["ok"] is True

    # Verify it's deleted
    devices = get_devices(user_id=user_id)
    assert len(devices) == 0

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_delete_device_by_token():
    """Test deleting a device by token"""
    test_email = "test@homeboundapp.com"
    with db.engine.begin() as connection:
        # Clean up
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE token = :token"),
            {"token": "delete_by_token"}
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
                "first_name": "Token",
                "last_name": "Delete",
                "age": 32
            }
        )
        user_id = result.fetchone()[0]

    # Register device
    register_device(
        DeviceRegister(platform="android", token="delete_by_token", bundle_id="com.app", env="production"),
        user_id=user_id
    )

    # Delete by token
    result = delete_device_by_token("delete_by_token", user_id=user_id)
    assert result["ok"] is True

    # Verify it's deleted
    devices = get_devices(user_id=user_id)
    assert len(devices) == 0

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


def test_register_device_invalid_platform():
    """Test registering device with invalid platform"""
    with pytest.raises(HTTPException) as exc_info:
        register_device(
            DeviceRegister(platform="invalid", token="token", bundle_id="com.app", env="production"),
            user_id=1
        )
    assert exc_info.value.status_code == 400
    assert "platform" in exc_info.value.detail.lower()


def test_register_device_invalid_env():
    """Test registering device with invalid environment"""
    with pytest.raises(HTTPException) as exc_info:
        register_device(
            DeviceRegister(platform="ios", token="token", bundle_id="com.app", env="invalid"),
            user_id=1
        )
    assert exc_info.value.status_code == 400
    assert "env" in exc_info.value.detail.lower()


def test_delete_nonexistent_device():
    """Test deleting a device that doesn't exist"""
    with pytest.raises(HTTPException) as exc_info:
        delete_device(999999, user_id=1)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_delete_nonexistent_device_by_token():
    """Test deleting by token that doesn't exist"""
    with pytest.raises(HTTPException) as exc_info:
        delete_device_by_token("nonexistent_token", user_id=1)
    assert exc_info.value.status_code == 404
