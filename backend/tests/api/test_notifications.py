"""Tests for notification service functions"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sqlalchemy

from src import database as db
from src.services.notifications import send_push_to_user, log_notification


class MockPushResult:
    """Mock result from APNs push sender"""
    def __init__(self, ok=True, status=200, detail=None):
        self.ok = ok
        self.status = status
        self.detail = detail


def table_exists(conn, table_name):
    """Check if a table exists in the database"""
    try:
        result = conn.execute(
            sqlalchemy.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = :table_name
                )
            """),
            {"table_name": table_name}
        ).fetchone()
        return result[0] if result else False
    except Exception:
        return False


@pytest.fixture
def test_user_with_device():
    """Create a test user with a device for notification tests"""
    test_email = "notification_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up any existing test data (check if tables exist first)
        if table_exists(conn, "notification_logs"):
            conn.execute(
                sqlalchemy.text("DELETE FROM notification_logs WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": test_email}
            )
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, 'Notification', 'Test', 30)
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create device
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'test_apns_token_12345', 'com.homeboundapp.test', 'development', NOW(), NOW())
            """),
            {"user_id": user_id}
        )

    yield {"user_id": user_id, "email": test_email, "token": "test_apns_token_12345"}

    # Cleanup
    with db.engine.begin() as conn:
        if table_exists(conn, "notification_logs"):
            conn.execute(
                sqlalchemy.text("DELETE FROM notification_logs WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


@pytest.mark.asyncio
async def test_send_push_to_user_success(test_user_with_device):
    """Test successful push notification sending"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"

            await send_push_to_user(user_id, "Test Title", "Test Body")

            # Verify send was called
            mock_sender.send.assert_called_once()
            call_args = mock_sender.send.call_args
            assert call_args[0][0] == "test_apns_token_12345"
            assert call_args[0][1] == "Test Title"
            assert call_args[0][2] == "Test Body"


@pytest.mark.asyncio
async def test_send_push_to_user_device_gone(test_user_with_device):
    """Test that 410 response removes device from database"""
    user_id = test_user_with_device["user_id"]
    token = test_user_with_device["token"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=False, status=410, detail="Device unregistered"))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"

            await send_push_to_user(user_id, "Test Title", "Test Body")

            # Verify device was removed
            with db.engine.begin() as conn:
                result = conn.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM devices WHERE token = :token"),
                    {"token": token}
                ).fetchone()
                assert result[0] == 0


@pytest.mark.asyncio
async def test_send_push_to_user_failure_with_retry(test_user_with_device):
    """Test that failed push retries before giving up"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    # Fail all attempts
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=False, status=500, detail="Server error"))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            with patch("asyncio.sleep", new_callable=AsyncMock):  # Skip actual delays

                await send_push_to_user(user_id, "Test Title", "Test Body")

                # Should have retried 3 times
                assert mock_sender.send.call_count == 3


@pytest.mark.asyncio
async def test_send_push_no_devices():
    """Test sending push to user with no devices"""
    # Use a non-existent user ID
    mock_sender = AsyncMock()

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"

            # Should not raise, just return
            await send_push_to_user(999999, "Test Title", "Test Body")

            # Sender should not have been called
            mock_sender.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_push_dummy_backend():
    """Test that dummy backend just logs and doesn't send"""
    mock_sender = AsyncMock()

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "dummy"

            await send_push_to_user(1, "Test Title", "Test Body")

            # Sender should not have been called for dummy backend
            mock_sender.send.assert_not_called()


def test_notification_logging(test_user_with_device):
    """Test that notifications are logged to database"""
    user_id = test_user_with_device["user_id"]

    # Check if table exists first
    with db.engine.begin() as conn:
        if not table_exists(conn, "notification_logs"):
            pytest.skip("notification_logs table not created yet (run migration)")

    # Log a notification
    log_notification(
        user_id=user_id,
        notification_type="push",
        title="Test Notification",
        body="Test body content",
        status="sent",
        device_token="test_token_xyz"
    )

    # Verify it was logged
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text("""
                SELECT notification_type, title, body, status, device_token
                FROM notification_logs
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"user_id": user_id}
        ).fetchone()

        assert result is not None
        assert result[0] == "push"
        assert result[1] == "Test Notification"
        assert result[2] == "Test body content"
        assert result[3] == "sent"
        assert result[4] == "test_token_xyz"


def test_notification_logging_failure(test_user_with_device):
    """Test that failed notifications are logged with error message"""
    user_id = test_user_with_device["user_id"]

    # Check if table exists first
    with db.engine.begin() as conn:
        if not table_exists(conn, "notification_logs"):
            pytest.skip("notification_logs table not created yet (run migration)")

    # Log a failed notification
    log_notification(
        user_id=user_id,
        notification_type="push",
        title="Failed Notification",
        body="This failed",
        status="failed",
        device_token="test_token_abc",
        error_message="Connection timeout"
    )

    # Verify it was logged with error
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text("""
                SELECT status, error_message
                FROM notification_logs
                WHERE user_id = :user_id AND title = 'Failed Notification'
            """),
            {"user_id": user_id}
        ).fetchone()

        assert result is not None
        assert result[0] == "failed"
        assert result[1] == "Connection timeout"
