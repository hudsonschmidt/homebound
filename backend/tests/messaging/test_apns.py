"""Tests for APNs push notification module"""
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.messaging.apns import (
    APNsClient,
    DummyPush,
    DummyPushWithLiveActivity,
    PushResult,
    get_push_sender,
)


# ============================================================================
# PushResult Tests
# ============================================================================

def test_push_result_success():
    """Test PushResult with successful response"""
    result = PushResult(ok=True, status=200, detail="success")

    assert result.ok is True
    assert result.status == 200
    assert result.detail == "success"


def test_push_result_failure():
    """Test PushResult with failed response"""
    result = PushResult(ok=False, status=400, detail="BadDeviceToken")

    assert result.ok is False
    assert result.status == 400
    assert result.detail == "BadDeviceToken"


def test_push_result_dict():
    """Test PushResult dict() method"""
    result = PushResult(ok=True, status=200, detail="apns-id-123")
    result_dict = result.dict()

    assert result_dict == {"ok": True, "status": 200, "detail": "apns-id-123"}


# ============================================================================
# DummyPush Tests
# ============================================================================

@pytest.mark.asyncio
async def test_dummy_push_send():
    """Test DummyPush send method"""
    dummy = DummyPush()
    result = await dummy.send(
        device_token="test_token",
        title="Test Title",
        body="Test Body",
        data={"key": "value"},
        category="TEST_CATEGORY"
    )

    assert result.ok is True
    assert result.status == 200
    assert result.detail == "dummy"


# ============================================================================
# DummyPushWithLiveActivity Tests
# ============================================================================

@pytest.mark.asyncio
async def test_dummy_push_with_live_activity_send():
    """Test DummyPushWithLiveActivity inherits send method"""
    dummy = DummyPushWithLiveActivity()
    result = await dummy.send(
        device_token="test_token",
        title="Test Title",
        body="Test Body"
    )

    assert result.ok is True
    assert result.status == 200


@pytest.mark.asyncio
async def test_dummy_push_with_live_activity_update():
    """Test DummyPushWithLiveActivity send_live_activity_update method"""
    dummy = DummyPushWithLiveActivity()

    content_state = {
        "status": "active",
        "eta": "2025-12-21T15:00:00",
        "lastCheckinTime": None,
        "isOverdue": False,
        "checkinCount": 2
    }

    result = await dummy.send_live_activity_update(
        live_activity_token="test_la_token_12345",
        content_state=content_state,
        event="update",
        timestamp=int(time.time())
    )

    assert result.ok is True
    assert result.status == 200
    assert result.detail == "dummy"


@pytest.mark.asyncio
async def test_dummy_push_live_activity_end_event():
    """Test DummyPushWithLiveActivity with end event"""
    dummy = DummyPushWithLiveActivity()

    content_state = {
        "status": "completed",
        "eta": "2025-12-21T15:00:00",
        "lastCheckinTime": None,
        "isOverdue": False,
        "checkinCount": 0
    }

    result = await dummy.send_live_activity_update(
        live_activity_token="test_la_token",
        content_state=content_state,
        event="end"
    )

    assert result.ok is True


# ============================================================================
# get_push_sender Tests
# ============================================================================

def test_get_push_sender_apns():
    """Test get_push_sender returns APNsClient for apns backend"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.PUSH_BACKEND = "apns"
        mock_settings.APNS_TEAM_ID = "TEAM123"
        mock_settings.APNS_KEY_ID = "KEY123"
        mock_settings.APNS_BUNDLE_ID = "com.homeboundapp.Homebound"
        mock_settings.APNS_USE_SANDBOX = True
        mock_settings.get_apns_private_key.return_value = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"

        sender = get_push_sender()
        assert isinstance(sender, APNsClient)


def test_get_push_sender_dummy():
    """Test get_push_sender returns DummyPushWithLiveActivity for dummy backend"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.PUSH_BACKEND = "dummy"

        sender = get_push_sender()
        assert isinstance(sender, DummyPushWithLiveActivity)


# ============================================================================
# APNsClient Tests (with mocked HTTP)
# ============================================================================

@pytest.mark.asyncio
async def test_apns_client_send_live_activity_update_success():
    """Test APNsClient.send_live_activity_update with successful response"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.APNS_TEAM_ID = "TEAM123"
        mock_settings.APNS_KEY_ID = "KEY123"
        mock_settings.APNS_BUNDLE_ID = "com.homeboundapp.Homebound"
        mock_settings.APNS_USE_SANDBOX = True
        mock_settings.get_apns_private_key.return_value = "-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg\n-----END PRIVATE KEY-----"

        client = APNsClient()

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"apns-id": "apns-test-id-123"}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_client_ctx", return_value=mock_http_client):
            content_state = {
                "status": "active",
                "eta": "2025-12-21T15:00:00",
                "lastCheckinTime": None,
                "isOverdue": False,
                "checkinCount": 1
            }

            result = await client.send_live_activity_update(
                live_activity_token="test_token_abc",
                content_state=content_state,
                event="update"
            )

            assert result.ok is True
            assert result.status == 200
            assert result.detail == "apns-test-id-123"

            # Verify the request was made with correct parameters
            mock_http_client.post.assert_called_once()
            call_args = mock_http_client.post.call_args

            # Check URL
            assert "test_token_abc" in call_args[0][0]

            # Check headers
            headers = call_args[1]["headers"]
            assert headers["apns-push-type"] == "liveactivity"
            assert "push-type.liveactivity" in headers["apns-topic"]
            assert headers["apns-priority"] == "10"

            # Check payload
            payload = call_args[1]["json"]
            assert "aps" in payload
            assert payload["aps"]["event"] == "update"
            assert "content-state" in payload["aps"]
            assert payload["aps"]["content-state"]["status"] == "active"


@pytest.mark.asyncio
async def test_apns_client_send_live_activity_update_failure():
    """Test APNsClient.send_live_activity_update with failed response"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.APNS_TEAM_ID = "TEAM123"
        mock_settings.APNS_KEY_ID = "KEY123"
        mock_settings.APNS_BUNDLE_ID = "com.homeboundapp.Homebound"
        mock_settings.APNS_USE_SANDBOX = True
        mock_settings.get_apns_private_key.return_value = "-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg\n-----END PRIVATE KEY-----"

        client = APNsClient()

        # Mock the HTTP client with error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"reason": "BadDeviceToken"}
        mock_response.text = "Bad Request"
        mock_response.headers = {}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_client_ctx", return_value=mock_http_client):
            content_state = {
                "status": "active",
                "eta": "2025-12-21T15:00:00",
                "lastCheckinTime": None,
                "isOverdue": False,
                "checkinCount": 0
            }

            result = await client.send_live_activity_update(
                live_activity_token="invalid_token",
                content_state=content_state
            )

            assert result.ok is False
            assert result.status == 400
            assert result.detail == "BadDeviceToken"


@pytest.mark.asyncio
async def test_apns_client_send_live_activity_update_410_gone():
    """Test APNsClient.send_live_activity_update with 410 Gone (unregistered)"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.APNS_TEAM_ID = "TEAM123"
        mock_settings.APNS_KEY_ID = "KEY123"
        mock_settings.APNS_BUNDLE_ID = "com.homeboundapp.Homebound"
        mock_settings.APNS_USE_SANDBOX = True
        mock_settings.get_apns_private_key.return_value = "-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg\n-----END PRIVATE KEY-----"

        client = APNsClient()

        # Mock 410 response (device unregistered)
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_response.json.return_value = {"reason": "Unregistered"}
        mock_response.text = ""
        mock_response.headers = {}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_client_ctx", return_value=mock_http_client):
            content_state = {
                "status": "overdue",
                "eta": "2025-12-21T15:00:00",
                "lastCheckinTime": None,
                "isOverdue": True,
                "checkinCount": 0
            }

            result = await client.send_live_activity_update(
                live_activity_token="expired_token",
                content_state=content_state
            )

            assert result.ok is False
            assert result.status == 410


@pytest.mark.asyncio
async def test_apns_client_send_live_activity_end_event():
    """Test APNsClient.send_live_activity_update with end event"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.APNS_TEAM_ID = "TEAM123"
        mock_settings.APNS_KEY_ID = "KEY123"
        mock_settings.APNS_BUNDLE_ID = "com.homeboundapp.Homebound"
        mock_settings.APNS_USE_SANDBOX = False  # Production
        mock_settings.get_apns_private_key.return_value = "-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg\n-----END PRIVATE KEY-----"

        client = APNsClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"apns-id": "end-event-id"}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_client_ctx", return_value=mock_http_client):
            content_state = {
                "status": "completed",
                "eta": "2025-12-21T15:00:00",
                "lastCheckinTime": None,
                "isOverdue": False,
                "checkinCount": 3
            }

            result = await client.send_live_activity_update(
                live_activity_token="test_token",
                content_state=content_state,
                event="end"
            )

            assert result.ok is True

            # Verify end event was sent
            call_args = mock_http_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["aps"]["event"] == "end"


@pytest.mark.asyncio
async def test_apns_client_send_live_activity_with_custom_timestamp():
    """Test APNsClient.send_live_activity_update with custom timestamp"""
    with patch("src.messaging.apns.settings") as mock_settings:
        mock_settings.APNS_TEAM_ID = "TEAM123"
        mock_settings.APNS_KEY_ID = "KEY123"
        mock_settings.APNS_BUNDLE_ID = "com.homeboundapp.Homebound"
        mock_settings.APNS_USE_SANDBOX = True
        mock_settings.get_apns_private_key.return_value = "-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg\n-----END PRIVATE KEY-----"

        client = APNsClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"apns-id": "custom-ts-id"}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)

        custom_timestamp = 1703160000  # Specific timestamp

        with patch.object(client, "_client_ctx", return_value=mock_http_client):
            content_state = {"status": "active", "eta": "2025-12-21T15:00:00", "lastCheckinTime": None, "isOverdue": False, "checkinCount": 0}

            await client.send_live_activity_update(
                live_activity_token="test_token",
                content_state=content_state,
                timestamp=custom_timestamp
            )

            # Verify custom timestamp was used
            call_args = mock_http_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["aps"]["timestamp"] == custom_timestamp


# ============================================================================
# Content State Format Tests
# ============================================================================

@pytest.mark.asyncio
async def test_apns_content_state_camel_case():
    """Test that content-state keys are camelCase as required by iOS"""
    dummy = DummyPushWithLiveActivity()

    # Content state with proper camelCase keys
    content_state = {
        "status": "active",
        "eta": "2025-12-21T15:00:00Z",
        "lastCheckinTime": "2025-12-21T14:30:00Z",
        "isOverdue": False,
        "checkinCount": 5
    }

    # Should not raise any errors
    result = await dummy.send_live_activity_update(
        live_activity_token="test_token",
        content_state=content_state
    )

    assert result.ok is True


@pytest.mark.asyncio
async def test_apns_content_state_with_null_values():
    """Test content-state with null lastCheckinTime"""
    dummy = DummyPushWithLiveActivity()

    content_state = {
        "status": "active",
        "eta": "2025-12-21T15:00:00Z",
        "lastCheckinTime": None,  # No check-ins yet
        "isOverdue": False,
        "checkinCount": 0
    }

    result = await dummy.send_live_activity_update(
        live_activity_token="test_token",
        content_state=content_state
    )

    assert result.ok is True


@pytest.mark.asyncio
async def test_apns_content_state_overdue():
    """Test content-state with overdue status"""
    dummy = DummyPushWithLiveActivity()

    content_state = {
        "status": "overdue_notified",
        "eta": "2025-12-21T13:00:00Z",
        "lastCheckinTime": "2025-12-21T12:30:00Z",
        "isOverdue": True,
        "checkinCount": 2
    }

    result = await dummy.send_live_activity_update(
        live_activity_token="test_token",
        content_state=content_state
    )

    assert result.ok is True
