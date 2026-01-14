"""Tests for notification service functions"""
from datetime import datetime, UTC
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sqlalchemy

from src import database as db
from src.services.notifications import (
    send_push_to_user,
    log_notification,
    send_live_activity_update,
    parse_datetime,
    format_datetime_with_tz,
    get_current_time_formatted,
    should_display_location,
    get_attr,
    send_email,
    send_background_push_to_user,
    send_magic_link_email,
)


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
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, 'Notification', 'Test', 30, 'free')
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create device (use 'sandbox' env to match APNS_USE_SANDBOX=True)
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'test_apns_token_12345', 'com.homeboundapp.test', 'sandbox', NOW(), NOW())
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
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

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
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

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
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'
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


# --- Notification Preference Tests ---

@pytest.fixture
def test_user_with_device_prefs_disabled():
    """Create a test user with device and notification preferences disabled"""
    test_email = "notification_prefs_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up any existing test data
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

        # Create user with notifications disabled
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age, notify_trip_reminders, notify_checkin_alerts)
                VALUES (:email, 'Prefs', 'Test', 30, false, false)
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create device (use 'sandbox' env to match APNS_USE_SANDBOX=True)
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'test_prefs_token_12345', 'com.homeboundapp.test', 'sandbox', NOW(), NOW())
            """),
            {"user_id": user_id}
        )

    yield {"user_id": user_id, "email": test_email, "token": "test_prefs_token_12345"}

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
async def test_trip_reminder_respects_user_preference_disabled(test_user_with_device_prefs_disabled):
    """Test that trip reminders are skipped when user has disabled them"""
    user_id = test_user_with_device_prefs_disabled["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"

            # Send trip_reminder notification - should be skipped
            await send_push_to_user(
                user_id,
                "Trip Reminder",
                "Your trip starts soon!",
                notification_type="trip_reminder"
            )

            # Sender should NOT have been called because preference is disabled
            mock_sender.send.assert_not_called()


@pytest.mark.asyncio
async def test_checkin_alert_respects_user_preference_disabled(test_user_with_device_prefs_disabled):
    """Test that check-in alerts are skipped when user has disabled them"""
    user_id = test_user_with_device_prefs_disabled["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"

            # Send checkin notification - should be skipped
            await send_push_to_user(
                user_id,
                "Check-in Reminder",
                "Please check in!",
                notification_type="checkin"
            )

            # Sender should NOT have been called because preference is disabled
            mock_sender.send.assert_not_called()


@pytest.mark.asyncio
async def test_emergency_notification_ignores_preferences(test_user_with_device_prefs_disabled):
    """Test that emergency notifications are always sent regardless of preferences"""
    user_id = test_user_with_device_prefs_disabled["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

            # Send emergency notification - should always be sent
            await send_push_to_user(
                user_id,
                "Emergency Alert",
                "This is urgent!",
                notification_type="emergency"
            )

            # Sender SHOULD have been called even though preferences are disabled
            mock_sender.send.assert_called_once()
            call_args = mock_sender.send.call_args
            assert call_args[0][1] == "Emergency Alert"


@pytest.mark.asyncio
async def test_general_notification_ignores_preferences(test_user_with_device_prefs_disabled):
    """Test that general notifications are sent regardless of specific preferences"""
    user_id = test_user_with_device_prefs_disabled["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

            # Send general notification (default type) - should be sent
            await send_push_to_user(
                user_id,
                "General Notice",
                "Just an update"
            )

            # Sender SHOULD have been called (general doesn't check specific prefs)
            mock_sender.send.assert_called_once()


@pytest.mark.asyncio
async def test_trip_reminder_sent_when_preference_enabled(test_user_with_device):
    """Test that trip reminders are sent when user has them enabled"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

            # Send trip_reminder notification - should be sent (default preference is True)
            await send_push_to_user(
                user_id,
                "Trip Reminder",
                "Your trip starts soon!",
                notification_type="trip_reminder"
            )

            # Sender SHOULD have been called
            mock_sender.send.assert_called_once()
            call_args = mock_sender.send.call_args
            assert call_args[0][1] == "Trip Reminder"


# ============================================================================
# FRIEND NOTIFICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_send_friend_trip_created_push():
    """Test sending push notification when friend is added as safety contact"""
    from src.services.notifications import send_friend_trip_created_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_trip_created_push(
            friend_user_id=123,
            user_name="John",
            trip_title="Mountain Hike"
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == 123  # friend_user_id
        assert "Safety Contact Added" in call_args[0][1]  # title
        assert "John" in call_args[0][2]  # body contains user name


@pytest.mark.asyncio
async def test_send_friend_trip_starting_push():
    """Test sending push notification when monitored trip starts"""
    from src.services.notifications import send_friend_trip_starting_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_trip_starting_push(
            friend_user_id=456,
            user_name="Jane",
            trip_title="Beach Run"
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == 456
        assert "Trip Started" in call_args[0][1]


@pytest.mark.asyncio
async def test_send_friend_overdue_push():
    """Test sending urgent push notification when trip is overdue"""
    from src.services.notifications import send_friend_overdue_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_overdue_push(
            friend_user_id=789,
            user_name="Bob",
            trip_title="Forest Walk",
            trip_id=100
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == 789
        assert "URGENT" in call_args[0][1]
        assert "Bob" in call_args[0][1]
        assert call_args[1]["notification_type"] == "emergency"


@pytest.mark.asyncio
async def test_send_friend_trip_completed_push():
    """Test sending push notification when trip is completed"""
    from src.services.notifications import send_friend_trip_completed_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_trip_completed_push(
            friend_user_id=111,
            user_name="Alice",
            trip_title="Sunset Hike"
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "safe" in call_args[0][1].lower()


@pytest.mark.asyncio
async def test_send_friend_overdue_resolved_push():
    """Test sending push notification when overdue is resolved"""
    from src.services.notifications import send_friend_overdue_resolved_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_overdue_resolved_push(
            friend_user_id=222,
            user_name="Charlie",
            trip_title="River Trail"
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "safe" in call_args[0][1].lower()
        assert call_args[1]["notification_type"] == "emergency"


@pytest.mark.asyncio
async def test_send_friend_checkin_push():
    """Test sending push notification when friend checks in"""
    from src.services.notifications import send_friend_checkin_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_checkin_push(
            friend_user_id=333,
            user_name="Dave",
            trip_title="City Walk"
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Check-in" in call_args[0][1]


@pytest.mark.asyncio
async def test_send_friend_trip_extended_push():
    """Test sending push notification when trip is extended"""
    from src.services.notifications import send_friend_trip_extended_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_trip_extended_push(
            friend_user_id=444,
            user_name="Eve",
            trip_title="Mountain Climb",
            extended_by_minutes=30
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Extended" in call_args[0][1]
        assert "30" in call_args[0][2]


@pytest.mark.asyncio
async def test_send_friend_request_accepted_push():
    """Test sending push notification when friend request is accepted"""
    from src.services.notifications import send_friend_request_accepted_push

    with patch("src.services.notifications.send_push_to_user") as mock_send:
        mock_send.return_value = None

        await send_friend_request_accepted_push(
            inviter_user_id=555,
            accepter_name="Frank"
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "Friend Request Accepted" in call_args[0][1]
        assert "Frank" in call_args[0][2]


@pytest.mark.asyncio
async def test_checkin_alert_sent_when_preference_enabled(test_user_with_device):
    """Test that check-in alerts are sent when user has them enabled"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

            # Send checkin notification - should be sent (default preference is True)
            await send_push_to_user(
                user_id,
                "Check-in Reminder",
                "Please check in!",
                notification_type="checkin"
            )

            # Sender SHOULD have been called
            mock_sender.send.assert_called_once()
            call_args = mock_sender.send.call_args
            assert call_args[0][1] == "Check-in Reminder"


@pytest.fixture
def test_user_with_mixed_preferences():
    """Create a test user with trip reminders enabled but check-in alerts disabled"""
    test_email = "mixed_prefs_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up any existing test data
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

        # Create user with trip reminders ON, check-in alerts OFF
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age, notify_trip_reminders, notify_checkin_alerts)
                VALUES (:email, 'Mixed', 'Prefs', 28, true, false)
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create device (use 'sandbox' env to match APNS_USE_SANDBOX=True)
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'test_mixed_token_12345', 'com.homeboundapp.test', 'sandbox', NOW(), NOW())
            """),
            {"user_id": user_id}
        )

    yield {"user_id": user_id, "email": test_email, "token": "test_mixed_token_12345"}

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
async def test_mixed_preferences_trip_reminder_sent(test_user_with_mixed_preferences):
    """Test that trip reminders are sent when only that preference is enabled"""
    user_id = test_user_with_mixed_preferences["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

            # Trip reminder should be sent (enabled)
            await send_push_to_user(
                user_id,
                "Trip Reminder",
                "Your trip starts soon!",
                notification_type="trip_reminder"
            )

            mock_sender.send.assert_called_once()


@pytest.mark.asyncio
async def test_mixed_preferences_checkin_alert_skipped(test_user_with_mixed_preferences):
    """Test that check-in alerts are skipped when only that preference is disabled"""
    user_id = test_user_with_mixed_preferences["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True  # Match device env='sandbox'

            # Check-in alert should be skipped (disabled)
            await send_push_to_user(
                user_id,
                "Check-in Reminder",
                "Please check in!",
                notification_type="checkin"
            )

            mock_sender.send.assert_not_called()


# ============================================================================
# Live Activity Update Tests
# ============================================================================

@pytest.fixture
def test_user_with_trip_and_la_token():
    """Create a test user with a trip and Live Activity token"""
    from datetime import UTC, datetime, timedelta

    test_email = "la_update_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up any existing test data
        conn.execute(
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": test_email}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        # Create user
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, 'LA', 'Test', 30, 'free')
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Get activity ID
        activity_result = conn.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()
        activity_id = activity_result[0]

        # Create trip
        now = datetime.now(UTC)
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, status, created_at,
                    checkin_token, checkout_token
                )
                VALUES (
                    :user_id, 'LA Test Trip', :activity, :start, :eta, 30,
                    'Test Location', 37.7749, -122.4194, 'active', :created_at,
                    'la_test_checkin', 'la_test_checkout'
                )
                RETURNING id
            """),
            {
                "user_id": user_id,
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "created_at": now.isoformat()
            }
        )
        trip_id = result.fetchone()[0]

        # Create Live Activity token
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO live_activity_tokens (trip_id, user_id, token, bundle_id, env, created_at, updated_at)
                VALUES (:trip_id, :user_id, 'test_la_token_xyz', 'com.homeboundapp.Homebound', 'development', :now, :now)
            """),
            {"trip_id": trip_id, "user_id": user_id, "now": now.isoformat()}
        )

    yield {
        "user_id": user_id,
        "trip_id": trip_id,
        "email": test_email,
        "token": "test_la_token_xyz",
        "eta": now + timedelta(hours=2)
    }

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM events WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM trips WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


@pytest.mark.asyncio
async def test_send_live_activity_update_success(test_user_with_trip_and_la_token):
    """Test successful Live Activity update"""
    from datetime import datetime

    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=True, status=200, detail="apns-id-123")
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True  # Match the "development" env

            await send_live_activity_update(
                trip_id=trip_id,
                status="active",
                eta=eta,
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0
            )

            # Verify Live Activity update was called
            mock_sender.send_live_activity_update.assert_called_once()
            call_args = mock_sender.send_live_activity_update.call_args

            # Check token
            assert call_args[1]["live_activity_token"] == "test_la_token_xyz"
            # Check event
            assert call_args[1]["event"] == "update"
            # Check content-state
            content_state = call_args[1]["content_state"]
            assert content_state["status"] == "active"
            assert content_state["isOverdue"] is False
            assert content_state["checkinCount"] == 0


@pytest.mark.asyncio
async def test_send_live_activity_update_with_checkin(test_user_with_trip_and_la_token):
    """Test Live Activity update after check-in"""
    from datetime import UTC, datetime

    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]
    last_checkin = datetime.now(UTC)

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=True, status=200)
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            await send_live_activity_update(
                trip_id=trip_id,
                status="active",
                eta=eta,
                last_checkin_time=last_checkin,
                is_overdue=False,
                checkin_count=3
            )

            call_args = mock_sender.send_live_activity_update.call_args
            content_state = call_args[1]["content_state"]

            # Verify check-in info is included
            assert content_state["lastCheckinTime"] is not None
            assert content_state["checkinCount"] == 3


@pytest.mark.asyncio
async def test_send_live_activity_update_overdue(test_user_with_trip_and_la_token):
    """Test Live Activity update with overdue status"""
    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=True, status=200)
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            await send_live_activity_update(
                trip_id=trip_id,
                status="overdue",
                eta=eta,
                last_checkin_time=None,
                is_overdue=True,
                checkin_count=0
            )

            call_args = mock_sender.send_live_activity_update.call_args
            content_state = call_args[1]["content_state"]

            assert content_state["status"] == "overdue"
            assert content_state["isOverdue"] is True


@pytest.mark.asyncio
async def test_send_live_activity_update_end_event(test_user_with_trip_and_la_token):
    """Test Live Activity update with end event"""
    from datetime import datetime

    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=True, status=200)
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            await send_live_activity_update(
                trip_id=trip_id,
                status="completed",
                eta=eta,
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0,
                event="end"
            )

            call_args = mock_sender.send_live_activity_update.call_args
            assert call_args[1]["event"] == "end"


@pytest.mark.asyncio
async def test_send_live_activity_update_no_token():
    """Test that Live Activity update is skipped when no token exists"""
    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock()

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            from datetime import datetime
            # Use non-existent trip ID
            await send_live_activity_update(
                trip_id=999999,
                status="active",
                eta=datetime.now(),
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0
            )

            # Should not have called send_live_activity_update
            mock_sender.send_live_activity_update.assert_not_called()


@pytest.mark.asyncio
async def test_send_live_activity_update_env_mismatch(test_user_with_trip_and_la_token):
    """Test that Live Activity update is skipped when env doesn't match"""
    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock()

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            # Token is "development" but we're in "production"
            mock_settings.APNS_USE_SANDBOX = False  # production

            await send_live_activity_update(
                trip_id=trip_id,
                status="active",
                eta=eta,
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0
            )

            # Should not have called send_live_activity_update due to env mismatch
            mock_sender.send_live_activity_update.assert_not_called()


@pytest.mark.asyncio
async def test_send_live_activity_update_token_invalidation(test_user_with_trip_and_la_token):
    """Test that invalid token is removed from database on 410 response"""
    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=False, status=410, detail="Unregistered")
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            await send_live_activity_update(
                trip_id=trip_id,
                status="active",
                eta=eta,
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0
            )

            # Token should be removed from database
            with db.engine.begin() as conn:
                result = conn.execute(
                    sqlalchemy.text("SELECT id FROM live_activity_tokens WHERE trip_id = :trip_id"),
                    {"trip_id": trip_id}
                ).fetchone()
                assert result is None


@pytest.mark.asyncio
async def test_send_live_activity_update_bad_device_token(test_user_with_trip_and_la_token):
    """Test that BadDeviceToken error removes token from database"""
    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=False, status=400, detail="BadDeviceToken")
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            await send_live_activity_update(
                trip_id=trip_id,
                status="active",
                eta=eta,
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0
            )

            # Token should be removed from database
            with db.engine.begin() as conn:
                result = conn.execute(
                    sqlalchemy.text("SELECT id FROM live_activity_tokens WHERE trip_id = :trip_id"),
                    {"trip_id": trip_id}
                ).fetchone()
                assert result is None


@pytest.mark.asyncio
async def test_send_live_activity_update_content_state_format(test_user_with_trip_and_la_token):
    """Test that content-state uses correct camelCase keys for iOS"""
    from datetime import UTC, datetime

    trip_id = test_user_with_trip_and_la_token["trip_id"]
    eta = test_user_with_trip_and_la_token["eta"]
    last_checkin = datetime.now(UTC)

    mock_sender = MagicMock()
    mock_sender.send_live_activity_update = AsyncMock(
        return_value=MockPushResult(ok=True, status=200)
    )

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.APNS_USE_SANDBOX = True

            await send_live_activity_update(
                trip_id=trip_id,
                status="active",
                eta=eta,
                last_checkin_time=last_checkin,
                is_overdue=False,
                checkin_count=5
            )

            call_args = mock_sender.send_live_activity_update.call_args
            content_state = call_args[1]["content_state"]

            # Verify camelCase keys (required by iOS Codable)
            assert "status" in content_state
            assert "eta" in content_state
            assert "lastCheckinTime" in content_state  # camelCase
            assert "isOverdue" in content_state  # camelCase
            assert "checkinCount" in content_state  # camelCase

            # Verify NO snake_case keys
            assert "last_checkin_time" not in content_state
            assert "is_overdue" not in content_state
            assert "checkin_count" not in content_state


# ============================================================================
# Notification Reliability Tests
# ============================================================================

@pytest.fixture
def test_user_with_multiple_devices():
    """Create a test user with multiple devices for failure recovery tests"""
    test_email = "multi_device_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up any existing test data
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
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, 'Multi', 'Device', 30, 'free')
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create multiple devices
        from datetime import UTC, datetime
        now = datetime.now(UTC)

        for i in range(3):
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                    VALUES (:user_id, 'ios', :token, 'com.homeboundapp.test', 'sandbox', :now, :now)
                """),
                {
                    "user_id": user_id,
                    "token": f"device_token_{i}_{now.timestamp()}",
                    "now": now.isoformat()
                }
            )

    yield {
        "user_id": user_id,
        "email": test_email
    }

    # Cleanup
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        conn.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )


@pytest.mark.asyncio
async def test_partial_device_failure_continues_to_next_device(test_user_with_multiple_devices):
    """Test that if one device fails, notification still goes to other devices"""
    user_id = test_user_with_multiple_devices["user_id"]

    failed_token = [None]
    successful_tokens = []

    async def mock_send(device_token, title, body, data=None, category=None):
        # First unique device fails, others succeed
        if failed_token[0] is None:
            failed_token[0] = device_token
            return MockPushResult(ok=False, status=500, detail="Internal Server Error")
        elif device_token == failed_token[0]:
            # Retry on same failed device
            return MockPushResult(ok=False, status=500, detail="Internal Server Error")
        else:
            successful_tokens.append(device_token)
            return MockPushResult(ok=True, status=200)

    mock_sender = AsyncMock()
    mock_sender.send = mock_send

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_push_to_user(
                user_id,
                "Test Notification",
                "Testing partial failure recovery"
            )

    # At least 2 devices should have succeeded (devices 2 and 3)
    # First device fails and may be retried
    assert len(successful_tokens) >= 2


@pytest.mark.asyncio
async def test_device_410_unregistered_removes_device(test_user_with_multiple_devices):
    """Test that 410 Unregistered response removes device from database"""
    user_id = test_user_with_multiple_devices["user_id"]

    # Get initial device count
    with db.engine.begin() as conn:
        initial_count = conn.execute(
            sqlalchemy.text("SELECT COUNT(*) as count FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone().count

    call_count = [0]

    async def mock_send(device_token, title, body, data=None, category=None):
        call_count[0] += 1
        # First device returns 410 (should be removed)
        if call_count[0] == 1:
            return MockPushResult(ok=False, status=410, detail="Unregistered")
        else:
            return MockPushResult(ok=True, status=200)

    mock_sender = AsyncMock()
    mock_sender.send = mock_send

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_push_to_user(
                user_id,
                "Test Notification",
                "Testing 410 cleanup"
            )

    # Device count should be reduced by 1
    with db.engine.begin() as conn:
        final_count = conn.execute(
            sqlalchemy.text("SELECT COUNT(*) as count FROM devices WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchone().count

    assert final_count == initial_count - 1


@pytest.mark.asyncio
async def test_device_env_mismatch_skipped():
    """Test that devices with mismatched environment are skipped"""
    test_email = "env_mismatch_test@homeboundapp.com"

    with db.engine.begin() as conn:
        # Clean up
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
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, 'Env', 'Test', 30, 'free')
                RETURNING id
            """),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create device with PRODUCTION env
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'production_device_token', 'com.homeboundapp.test', 'production', :now, :now)
            """),
            {"user_id": user_id, "now": now.isoformat()}
        )

    try:
        mock_sender = AsyncMock()
        mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

        with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
            with patch("src.services.notifications.settings") as mock_settings:
                mock_settings.PUSH_BACKEND = "apns"
                mock_settings.APNS_USE_SANDBOX = True  # SANDBOX mode

                await send_push_to_user(
                    user_id,
                    "Test Notification",
                    "Testing env mismatch"
                )

        # Device should be skipped (production device in sandbox mode)
        mock_sender.send.assert_not_called()
    finally:
        # Cleanup
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ============================================================================
# Utility Function Tests
# ============================================================================

class TestParseDatetime:
    """Tests for parse_datetime function"""

    def test_parse_datetime_with_none(self):
        """Test that None returns None"""
        assert parse_datetime(None) is None

    def test_parse_datetime_with_datetime_object(self):
        """Test that datetime objects are returned as-is"""
        dt = datetime.now(UTC)
        result = parse_datetime(dt)
        assert result == dt

    def test_parse_datetime_with_string(self):
        """Test parsing ISO format string"""
        dt_string = "2025-12-21T15:30:00"
        result = parse_datetime(dt_string)
        assert result is not None
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 21
        assert result.hour == 15
        assert result.minute == 30

    def test_parse_datetime_with_string_and_z_suffix(self):
        """Test parsing ISO format string with Z suffix"""
        dt_string = "2025-12-21T15:30:00Z"
        result = parse_datetime(dt_string)
        assert result is not None
        assert result.year == 2025

    def test_parse_datetime_with_space_separator(self):
        """Test parsing string with space instead of T"""
        dt_string = "2025-12-21 15:30:00"
        result = parse_datetime(dt_string)
        assert result is not None
        assert result.year == 2025


class TestFormatDatetimeWithTz:
    """Tests for format_datetime_with_tz function"""

    def test_format_with_none_datetime(self):
        """Test that None datetime returns 'Not specified'"""
        result, tz_display = format_datetime_with_tz(None, "America/New_York")
        assert result == "Not specified"
        assert tz_display == ""

    def test_format_with_valid_timezone(self):
        """Test formatting with valid timezone"""
        dt = datetime(2025, 12, 21, 15, 30, 0)
        result, tz_display = format_datetime_with_tz(dt, "America/Los_Angeles")
        assert "December 21, 2025" in result
        assert "PST" in result or "PDT" in result

    def test_format_with_invalid_timezone(self):
        """Test formatting with invalid timezone falls back gracefully"""
        dt = datetime(2025, 12, 21, 15, 30, 0)
        result, tz_display = format_datetime_with_tz(dt, "Invalid/Timezone")
        # Should still format the datetime, just without timezone conversion
        assert "December 21, 2025" in result

    def test_format_with_no_timezone(self):
        """Test formatting without timezone"""
        dt = datetime(2025, 12, 21, 15, 30, 0)
        result, tz_display = format_datetime_with_tz(dt, None)
        assert "December 21, 2025" in result


class TestGetCurrentTimeFormatted:
    """Tests for get_current_time_formatted function"""

    def test_get_current_time_with_timezone(self):
        """Test getting current time with timezone"""
        result, tz_display = get_current_time_formatted("America/New_York")
        assert result is not None
        # Result should contain a year
        assert "202" in result  # Will match 2024, 2025, etc.


class TestShouldDisplayLocation:
    """Tests for should_display_location function"""

    def test_empty_string_returns_false(self):
        """Test that empty string returns False"""
        assert should_display_location("") is False

    def test_none_returns_false(self):
        """Test that None returns False"""
        assert should_display_location(None) is False

    def test_current_location_returns_false(self):
        """Test that 'Current Location' returns False"""
        assert should_display_location("Current Location") is False
        assert should_display_location("current location") is False

    def test_coordinates_returns_false(self):
        """Test that coordinate strings return False"""
        assert should_display_location("37.7749, -122.4194") is False
        assert should_display_location("37.7749°N, 122.4194°W") is False

    def test_valid_location_returns_true(self):
        """Test that valid location names return True"""
        assert should_display_location("San Francisco, CA") is True
        assert should_display_location("Yosemite National Park") is True
        assert should_display_location("123 Main Street") is True


class TestGetAttr:
    """Tests for get_attr helper function"""

    def test_get_attr_from_dict(self):
        """Test getting attribute from dict"""
        data = {"name": "John", "age": 30}
        assert get_attr(data, "name") == "John"
        assert get_attr(data, "age") == 30
        assert get_attr(data, "missing", "default") == "default"

    def test_get_attr_from_object(self):
        """Test getting attribute from object"""
        class MockObj:
            name = "Jane"
            age = 25
        obj = MockObj()
        assert get_attr(obj, "name") == "Jane"
        assert get_attr(obj, "missing", "default") == "default"


# ============================================================================
# Email Function Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_email_console_backend():
    """Test that console backend logs email instead of sending"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.EMAIL_BACKEND = "console"

        await send_email(
            email="test@example.com",
            subject="Test Subject",
            body="Test body"
        )
        # Should not raise, just log


@pytest.mark.asyncio
async def test_send_email_console_backend_high_priority():
    """Test console backend with high priority flag"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.EMAIL_BACKEND = "console"

        await send_email(
            email="test@example.com",
            subject="Urgent Subject",
            body="Urgent body",
            high_priority=True
        )
        # Should not raise, just log with priority note


@pytest.mark.asyncio
async def test_send_email_unknown_backend():
    """Test warning for unknown email backend"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.EMAIL_BACKEND = "unknown_backend"

        await send_email(
            email="test@example.com",
            subject="Test Subject",
            body="Test body"
        )
        # Should not raise, just log warning


@pytest.mark.asyncio
async def test_send_email_resend_backend():
    """Test resend backend sends email"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.EMAIL_BACKEND = "resend"

        with patch("src.messaging.resend_backend.send_resend_email") as mock_send:
            mock_send.return_value = True

            await send_email(
                email="test@example.com",
                subject="Test Subject",
                body="Test body",
                html_body="<p>Test</p>",
                from_email="noreply@example.com"
            )

            mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_resend_failure_logged():
    """Test that resend failure is logged"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.EMAIL_BACKEND = "resend"

        with patch("src.messaging.resend_backend.send_resend_email") as mock_send:
            mock_send.return_value = False  # Failure

            await send_email(
                email="test@example.com",
                subject="Test Subject",
                body="Test body"
            )
            # Should log error but not raise


# ============================================================================
# Background Push Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_background_push_dummy_backend():
    """Test background push with dummy backend"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.PUSH_BACKEND = "dummy"

        await send_background_push_to_user(
            user_id=1,
            data={"action": "refresh"}
        )
        # Should just log and return


@pytest.mark.asyncio
async def test_send_background_push_unknown_backend():
    """Test background push with unknown backend"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.PUSH_BACKEND = "unknown"

        await send_background_push_to_user(
            user_id=1,
            data={"action": "refresh"}
        )
        # Should log warning and return


@pytest.mark.asyncio
async def test_send_background_push_no_devices():
    """Test background push when user has no devices"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.PUSH_BACKEND = "apns"
        mock_settings.APNS_USE_SANDBOX = True

        await send_background_push_to_user(
            user_id=999999,  # Non-existent user
            data={"action": "refresh"}
        )
        # Should log warning about no devices


@pytest.mark.asyncio
async def test_send_background_push_success(test_user_with_device):
    """Test successful background push"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send_background = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_background_push_to_user(
                user_id=user_id,
                data={"action": "start_live_activity", "trip_id": 123}
            )

            mock_sender.send_background.assert_called_once()


@pytest.mark.asyncio
async def test_send_background_push_failure(test_user_with_device):
    """Test background push failure handling"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send_background = AsyncMock(return_value=MockPushResult(ok=False, status=500, detail="Error"))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_background_push_to_user(
                user_id=user_id,
                data={"action": "refresh"}
            )
            # Should log warning but not raise


@pytest.mark.asyncio
async def test_send_background_push_exception(test_user_with_device):
    """Test background push exception handling"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send_background = AsyncMock(side_effect=Exception("Connection error"))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_background_push_to_user(
                user_id=user_id,
                data={"action": "refresh"}
            )
            # Should log error but not raise


@pytest.mark.asyncio
async def test_send_background_push_no_send_background_method(test_user_with_device):
    """Test background push with sender lacking send_background method"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    # Remove send_background method
    del mock_sender.send_background

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_background_push_to_user(
                user_id=user_id,
                data={"action": "refresh"}
            )
            # Should log warning about unsupported method


# ============================================================================
# Magic Link Email Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_magic_link_email():
    """Test sending magic link email"""
    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.EMAIL_BACKEND = "resend"
            mock_settings.RESEND_FROM_EMAIL = "noreply@homeboundapp.com"

            await send_magic_link_email("test@example.com", "123456")

            mock_send_email.assert_called_once()
            call_args = mock_send_email.call_args
            assert call_args[0][0] == "test@example.com"
            assert "123456" in call_args[0][2]  # Code in body


@pytest.mark.asyncio
async def test_send_magic_link_email_console_backend():
    """Test sending magic link email with console backend"""
    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.EMAIL_BACKEND = "console"
            mock_settings.RESEND_FROM_EMAIL = "noreply@homeboundapp.com"

            await send_magic_link_email("test@example.com", "654321")

            mock_send_email.assert_called_once()


# ============================================================================
# Push Notification Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_push_to_user_bad_device_token_removed(test_user_with_device):
    """Test that BadDeviceToken response removes device from database"""
    user_id = test_user_with_device["user_id"]
    token = test_user_with_device["token"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=False, status=400, detail="BadDeviceToken"))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True

            await send_push_to_user(user_id, "Test", "Body")

            # Device should be removed
            with db.engine.begin() as conn:
                result = conn.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM devices WHERE token = :token"),
                    {"token": token}
                ).fetchone()
                assert result[0] == 0


@pytest.mark.asyncio
async def test_send_push_to_user_exception_handling(test_user_with_device):
    """Test that exceptions during send are handled gracefully"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(side_effect=Exception("Network error"))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"
            mock_settings.APNS_USE_SANDBOX = True
            with patch("asyncio.sleep", new_callable=AsyncMock):

                await send_push_to_user(user_id, "Test", "Body")
                # Should retry 3 times
                assert mock_sender.send.call_count == 3


@pytest.mark.asyncio
async def test_send_push_unknown_backend():
    """Test warning for unknown push backend"""
    with patch("src.services.notifications.settings") as mock_settings:
        mock_settings.PUSH_BACKEND = "unknown_backend"

        await send_push_to_user(1, "Test", "Body")
        # Should log warning and return


# ============================================================================
# Log Notification Error Handling Tests
# ============================================================================

def test_log_notification_handles_db_error(test_user_with_device):
    """Test that log_notification handles database errors gracefully"""
    user_id = test_user_with_device["user_id"]

    with patch("src.services.notifications.db.engine") as mock_engine:
        mock_engine.begin.side_effect = Exception("Database error")

        # Should not raise
        log_notification(
            user_id=user_id,
            notification_type="push",
            title="Test",
            body="Body",
            status="sent"
        )


# ============================================================================
# Email Notification Function Tests
# ============================================================================

class MockTrip:
    """Mock trip object for testing email notifications"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.title = kwargs.get('title', 'Test Trip')
        self.user_id = kwargs.get('user_id', 1)
        self.location_text = kwargs.get('location_text', 'Test Location')
        self.start_location_text = kwargs.get('start_location_text', None)
        self.notes = kwargs.get('notes', None)
        self.activity_name = kwargs.get('activity_name', 'Hiking')
        self.eta = kwargs.get('eta', '2025-12-21T15:00:00')
        self.start = kwargs.get('start', '2025-12-21T10:00:00')
        self.checkout_token = kwargs.get('checkout_token', 'test_checkout')
        self.has_separate_locations = kwargs.get('has_separate_locations', False)


class MockContact:
    """Mock contact object for testing email notifications"""
    def __init__(self, name='Test Contact', email='contact@test.com'):
        self.name = name
        self.email = email


@pytest.mark.asyncio
async def test_send_overdue_notifications():
    """Test sending overdue notification emails"""
    from src.services.notifications import send_overdue_notifications

    trip = MockTrip()
    contacts = [MockContact(email='contact1@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        with patch("src.services.notifications.send_push_to_user") as mock_push:
            mock_push.return_value = None

            await send_overdue_notifications(
                trip=trip,
                contacts=contacts,
                user_name="John Doe",
                user_timezone="America/Los_Angeles"
            )

            # Should have sent email to contact
            assert mock_send_email.call_count >= 1
            # Should have sent push to user
            mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_send_overdue_notifications_with_owner_email():
    """Test sending overdue notification to owner as well"""
    from src.services.notifications import send_overdue_notifications

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        with patch("src.services.notifications.send_push_to_user") as mock_push:
            mock_push.return_value = None

            await send_overdue_notifications(
                trip=trip,
                contacts=contacts,
                user_name="Jane Doe",
                owner_email="owner@test.com"
            )

            # Should have sent to contact AND owner
            assert mock_send_email.call_count == 2


@pytest.mark.asyncio
async def test_send_trip_created_emails():
    """Test sending trip created notification emails"""
    from src.services.notifications import send_trip_created_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_created_emails(
            trip=trip,
            contacts=contacts,
            user_name="Alice",
            activity_name="Hiking",
            user_timezone="America/New_York"
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args
        assert "Alice" in call_args[0][1]  # Subject contains user name


@pytest.mark.asyncio
async def test_send_trip_created_emails_with_owner():
    """Test sending trip created emails to owner"""
    from src.services.notifications import send_trip_created_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_created_emails(
            trip=trip,
            contacts=contacts,
            user_name="Bob",
            activity_name="Running",
            owner_email="owner@test.com"
        )

        # Should send to contact and owner
        assert mock_send_email.call_count == 2


@pytest.mark.asyncio
async def test_send_trip_starting_now_emails():
    """Test sending trip starting now notification emails"""
    from src.services.notifications import send_trip_starting_now_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_starting_now_emails(
            trip=trip,
            contacts=contacts,
            user_name="Charlie",
            activity_name="Cycling",
            user_timezone="America/Chicago"
        )

        mock_send_email.assert_called_once()


@pytest.mark.asyncio
async def test_send_checkin_update_emails():
    """Test sending check-in update notification emails"""
    from src.services.notifications import send_checkin_update_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_checkin_update_emails(
            trip=trip,
            contacts=contacts,
            user_name="Dave",
            activity_name="Hiking",
            user_timezone="UTC"
        )

        mock_send_email.assert_called_once()


@pytest.mark.asyncio
async def test_send_trip_extended_emails():
    """Test sending trip extended notification emails"""
    from src.services.notifications import send_trip_extended_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_extended_emails(
            trip=trip,
            contacts=contacts,
            user_name="Eve",
            activity_name="Hiking",
            extended_by_minutes=30,
            user_timezone="America/Denver"
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args
        assert "Extended" in call_args[0][1]  # Subject contains 'Extended'


@pytest.mark.asyncio
async def test_send_trip_completed_emails():
    """Test sending trip completed notification emails"""
    from src.services.notifications import send_trip_completed_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_completed_emails(
            trip=trip,
            contacts=contacts,
            user_name="Frank",
            activity_name="Running",
            user_timezone="America/Phoenix"
        )

        mock_send_email.assert_called_once()


@pytest.mark.asyncio
async def test_send_overdue_resolved_emails():
    """Test sending overdue resolved notification emails"""
    from src.services.notifications import send_overdue_resolved_emails

    trip = MockTrip()
    contacts = [MockContact(email='contact@test.com')]

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_overdue_resolved_emails(
            trip=trip,
            contacts=contacts,
            user_name="Grace",
            activity_name="Cycling",
            user_timezone="Pacific/Honolulu"
        )

        mock_send_email.assert_called_once()


@pytest.mark.asyncio
async def test_email_functions_handle_no_contacts():
    """Test that email functions handle empty contact list gracefully"""
    from src.services.notifications import send_trip_created_emails

    trip = MockTrip()
    contacts = []  # No contacts

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_created_emails(
            trip=trip,
            contacts=contacts,
            user_name="Henry",
            activity_name="Swimming"
        )

        # Should not have sent any emails
        mock_send_email.assert_not_called()


@pytest.mark.asyncio
async def test_email_functions_handle_contacts_without_email():
    """Test that email functions skip contacts without email"""
    from src.services.notifications import send_trip_created_emails

    trip = MockTrip()
    contacts = [MockContact(email=None)]  # Contact without email

    with patch("src.services.notifications.send_email") as mock_send_email:
        mock_send_email.return_value = None

        await send_trip_created_emails(
            trip=trip,
            contacts=contacts,
            user_name="Ivy",
            activity_name="Walking"
        )

        # Should not have sent any emails
        mock_send_email.assert_not_called()
