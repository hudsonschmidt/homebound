"""Tests for notification service functions"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sqlalchemy

from src import database as db
from src.services.notifications import send_push_to_user, log_notification, send_live_activity_update


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

        # Create device
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'test_prefs_token_12345', 'com.homeboundapp.test', 'development', NOW(), NOW())
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


@pytest.mark.asyncio
async def test_checkin_alert_sent_when_preference_enabled(test_user_with_device):
    """Test that check-in alerts are sent when user has them enabled"""
    user_id = test_user_with_device["user_id"]

    mock_sender = AsyncMock()
    mock_sender.send = AsyncMock(return_value=MockPushResult(ok=True, status=200))

    with patch("src.messaging.apns.get_push_sender", return_value=mock_sender):
        with patch("src.services.notifications.settings") as mock_settings:
            mock_settings.PUSH_BACKEND = "apns"

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

        # Create device
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                VALUES (:user_id, 'ios', 'test_mixed_token_12345', 'com.homeboundapp.test', 'development', NOW(), NOW())
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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, 'LA', 'Test', 30)
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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

    with patch("src.services.notifications.get_push_sender", return_value=mock_sender):
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
