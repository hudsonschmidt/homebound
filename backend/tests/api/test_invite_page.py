"""Tests for friend invite page endpoint."""
from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from src import database as db
from src.api.server import app


client = TestClient(app)


def cleanup_invite(token: str):
    """Clean up test invite."""
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM friend_invites WHERE token = :token"),
            {"token": token}
        )


def create_test_invite(token: str, inviter_id: int, expires_at: datetime, max_uses: int = 1, use_count: int = 0):
    """Create a test friend invite."""
    with db.engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO friend_invites (token, inviter_id, expires_at, max_uses, use_count, created_at)
                VALUES (:token, :inviter_id, :expires_at, :max_uses, :use_count, NOW())
            """),
            {
                "token": token,
                "inviter_id": inviter_id,
                "expires_at": expires_at.isoformat(),
                "max_uses": max_uses,
                "use_count": use_count
            }
        )


def get_test_user_id() -> int:
    """Get or create a test user ID."""
    with db.engine.begin() as conn:
        result = conn.execute(
            sqlalchemy.text("SELECT id FROM users LIMIT 1")
        ).fetchone()
        if result:
            return result.id

        # Create a test user if none exists
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age)
                VALUES ('invite-test@example.com', 'Test', 'User', 25)
                RETURNING id
            """)
        )
        return result.fetchone()[0]


class TestServeInvitePage:
    """Tests for the invite page endpoint."""

    def test_valid_invite_returns_html(self):
        """Test that a valid invite returns an HTML page."""
        token = "test-valid-invite-123"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Check HTML content
            html = response.text
            assert "<!DOCTYPE html>" in html
            assert "You've been invited to Homebound" in html
            assert "Join Homebound" in html
        finally:
            cleanup_invite(token)

    def test_valid_invite_contains_og_tags(self):
        """Test that valid invite page has Open Graph meta tags."""
        token = "test-og-invite-456"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            # Check for OG meta tags
            assert 'og:title' in html
            assert 'og:description' in html
            assert 'og:image' in html
            assert 'og:url' in html
        finally:
            cleanup_invite(token)

    def test_valid_invite_contains_app_store_link(self):
        """Test that page includes App Store link."""
        token = "test-appstore-789"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            # Check for App Store URL
            assert "apps.apple.com" in html
            assert "Get Homebound" in html
        finally:
            cleanup_invite(token)

    def test_valid_invite_contains_app_deep_link(self):
        """Test that page includes app deep link."""
        token = "test-deeplink-abc"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            # Check for custom URL scheme
            assert f"homebound://f/{token}" in html
            assert "Open in app" in html
        finally:
            cleanup_invite(token)

    def test_expired_invite_shows_expired_message(self):
        """Test that expired invite shows appropriate message."""
        token = "test-expired-def"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) - timedelta(days=1)  # Already expired

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            assert response.status_code == 200
            assert "Invite Expired" in html
            assert "expired or is no longer valid" in html
        finally:
            cleanup_invite(token)

    def test_max_uses_exceeded_shows_expired(self):
        """Test that invite with max uses exceeded shows expired."""
        token = "test-maxuses-ghi"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at, max_uses=5, use_count=5)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            assert response.status_code == 200
            assert "Invite Expired" in html
        finally:
            cleanup_invite(token)

    def test_nonexistent_invite_shows_expired(self):
        """Test that nonexistent invite token shows expired message."""
        response = client.get("/f/nonexistent-token-12345")
        html = response.text

        assert response.status_code == 200
        assert "Invite Expired" in html

    def test_invite_has_smart_app_banner(self):
        """Test that page includes iOS Smart App Banner meta tag."""
        token = "test-banner-jkl"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            # Check for Smart App Banner
            assert 'apple-itunes-app' in html
            assert 'app-id=' in html
        finally:
            cleanup_invite(token)

    def test_invite_has_twitter_card_meta(self):
        """Test that page includes Twitter Card meta tags."""
        token = "test-twitter-mno"
        user_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        create_test_invite(token, user_id, expires_at)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            assert 'twitter:card' in html
            assert 'twitter:title' in html
            assert 'twitter:description' in html
        finally:
            cleanup_invite(token)

    def test_invite_page_valid_with_high_max_uses(self):
        """Test that invite with high max_uses limit works even with many uses."""
        token = "test-highuses-pqr"
        inviter_id = get_test_user_id()
        expires_at = datetime.now(UTC) + timedelta(days=7)

        cleanup_invite(token)
        # Set max_uses very high so use_count of 100 is still under limit
        create_test_invite(token, inviter_id, expires_at, max_uses=1000, use_count=100)

        try:
            response = client.get(f"/f/{token}")
            html = response.text

            assert response.status_code == 200
            # Should still be valid since use_count < max_uses
            assert "You've been invited to Homebound" in html
        finally:
            cleanup_invite(token)
