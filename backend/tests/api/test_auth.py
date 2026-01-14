import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy
from fastapi import HTTPException
from jose import jwt

from src import config
from src import database as db
from src.api.auth_endpoints import (
    MagicLinkRequest,
    RefreshRequest,
    TokenResponse,
    VerifyRequest,
    create_jwt_pair,
    refresh_token,
    request_magic_link,
    verify_magic_code,
)
from src.api.auth import get_current_user_id

settings = config.get_settings()


def run_async(coro):
    """Helper to run async functions in sync tests"""
    return asyncio.get_event_loop().run_until_complete(coro)


def test_create_jwt_pair():
    """Test JWT token pair creation"""
    user_id = 1
    email = "test@example.com"

    access, refresh = create_jwt_pair(user_id, email)

    # Verify both tokens are strings
    assert isinstance(access, str)
    assert isinstance(refresh, str)

    # Decode and verify access token
    access_payload = jwt.decode(access, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert access_payload["typ"] == "access"
    assert access_payload["sub"] == str(user_id)
    assert access_payload["email"] == email
    assert access_payload["iss"] == "homebound"

    # Decode and verify refresh token
    refresh_payload = jwt.decode(refresh, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert refresh_payload["typ"] == "refresh"
    assert refresh_payload["sub"] == str(user_id)
    assert refresh_payload["email"] == email
    assert refresh_payload["iss"] == "homebound"


def test_request_magic_link_existing_user():
    """Test requesting magic link for existing user"""
    # First, create a test user if not exists
    with db.engine.begin() as connection:
        # Check if user exists
        existing = connection.execute(
            sqlalchemy.text("SELECT id FROM users WHERE email = :email"),
            {"email": "test@homeboundapp.com"}
        ).fetchone()

        if not existing:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                    VALUES (:email, :first_name, :last_name, :age, 'free')
                    """
                ),
                {
                    "email": "test@homeboundapp.com",
                    "first_name": "Test",
                    "last_name": "User",
                    "age": 25
                }
            )

    request = MagicLinkRequest(email="test@homeboundapp.com")
    result = run_async(request_magic_link(request))

    assert result["ok"] is True
    assert "message" in result

    # Verify token was created
    with db.engine.begin() as connection:
        token = connection.execute(
            sqlalchemy.text(
                """
                SELECT token, email, expires_at
                FROM login_tokens
                WHERE email = :email
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": "test@homeboundapp.com"}
        ).fetchone()

        assert token is not None
        assert token.email == "test@homeboundapp.com"
        assert len(token.token) == 6
        assert token.token.isdigit()


def test_request_magic_link_nonexistent_user():
    """Test requesting magic link for non-existent user (should auto-create account)"""
    test_email = "autocreate@example.com"

    # Clean up first
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    request = MagicLinkRequest(email=test_email)
    result = run_async(request_magic_link(request))

    assert result["ok"] is True
    assert "message" in result

    # Verify user was created
    with db.engine.begin() as connection:
        user = connection.execute(
            sqlalchemy.text("SELECT id, email FROM users WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert user is not None
        assert user.email == test_email

        # Verify token was created
        token = connection.execute(
            sqlalchemy.text(
                """
                SELECT token, email
                FROM login_tokens
                WHERE email = :email
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": test_email}
        ).fetchone()

        assert token is not None
        assert len(token.token) == 6
        assert token.token.isdigit()


def test_auto_create_account_full_flow():
    """Test complete flow: auto-create account -> request magic link -> verify -> get tokens"""
    test_email = "fullflow@newuser.com"

    # Clean up first
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Step 1: Request magic link (should auto-create account)
    request = MagicLinkRequest(email=test_email)
    result = run_async(request_magic_link(request))
    assert result["ok"] is True

    # Step 2: Get the magic code from database
    with db.engine.begin() as connection:
        token_record = connection.execute(
            sqlalchemy.text(
                """
                SELECT token, user_id
                FROM login_tokens
                WHERE email = :email
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": test_email}
        ).fetchone()

        assert token_record is not None
        magic_code = token_record.token
        user_id = token_record.user_id

        # Verify user was created
        user = connection.execute(
            sqlalchemy.text("SELECT id, email, first_name, last_name, age FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()

        assert user is not None
        assert user.email == test_email
        # New users should have default empty values
        assert user.first_name == ""
        assert user.last_name == ""
        assert user.age == 0

    # Step 3: Verify the magic code
    verify_req = VerifyRequest(email=test_email, code=magic_code)
    token_response = verify_magic_code(verify_req)

    assert isinstance(token_response, TokenResponse)
    assert isinstance(token_response.access, str)
    assert isinstance(token_response.refresh, str)
    assert token_response.user["email"] == test_email
    assert token_response.user["id"] == user_id


def test_last_login_at_updated_on_verify():
    """Test that last_login_at is updated when user verifies (logs in), not when requesting magic link"""
    test_email = "lastlogin@test.com"

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Request magic link (auto-create user)
    run_async(request_magic_link(MagicLinkRequest(email=test_email)))

    # After requesting magic link, last_login_at should still be NULL
    with db.engine.begin() as connection:
        user_before = connection.execute(
            sqlalchemy.text("SELECT email, last_login_at FROM users WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert user_before is not None
        assert user_before.last_login_at is None  # Not set until actual login

        # Get the magic code
        token_record = connection.execute(
            sqlalchemy.text(
                """
                SELECT token FROM login_tokens
                WHERE email = :email
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": test_email}
        ).fetchone()
        magic_code = token_record.token

    # Verify the magic code (actual login)
    verify_req = VerifyRequest(email=test_email, code=magic_code)
    verify_magic_code(verify_req)

    # After verifying, last_login_at should be set
    with db.engine.begin() as connection:
        user_after = connection.execute(
            sqlalchemy.text("SELECT email, last_login_at FROM users WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert user_after is not None
        assert user_after.last_login_at is not None  # Now set after actual login


def test_auto_create_multiple_requests_same_email():
    """Test that requesting magic link multiple times doesn't create duplicate users"""
    test_email = "duplicate@test.com"

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

    # Request magic link 3 times
    for _ in range(3):
        result = run_async(request_magic_link(MagicLinkRequest(email=test_email)))
        assert result["ok"] is True

    # Verify only one user was created
    with db.engine.begin() as connection:
        user_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) as count FROM users WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert user_count.count == 1

        # Verify multiple tokens were created
        token_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) as count FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert token_count.count == 3


def test_verify_magic_code_success():
    """Test successful magic code verification"""
    test_email = "verify-test@homeboundapp.com"

    # Create test user
    with db.engine.begin() as connection:
        # Delete old tokens first (due to foreign key constraint)
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )

        # Delete existing user if exists
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Verify",
                "last_name": "Test",
                "age": 30
            }
        )
        user_id = result.fetchone()[0]

        # Create a magic token (store as ISO string to match production code)
        test_code = "123456"
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO login_tokens (user_id, email, token, expires_at)
                VALUES (:user_id, :email, :token, :expires_at)
                """
            ),
            {
                "user_id": user_id,
                "email": test_email,
                "token": test_code,
                "expires_at": expires_at.isoformat()
            }
        )

    # Verify the code
    verify_req = VerifyRequest(email=test_email, code=test_code)
    result = verify_magic_code(verify_req)

    assert isinstance(result, TokenResponse)
    assert isinstance(result.access, str)
    assert isinstance(result.refresh, str)
    assert result.user["email"] == test_email
    assert result.user["first_name"] == "Verify"
    assert result.user["last_name"] == "Test"
    assert result.user["age"] == 30


def test_verify_magic_code_invalid():
    """Test verification with invalid code"""
    verify_req = VerifyRequest(email="test@example.com", code="000000")

    with pytest.raises(HTTPException) as exc_info:
        verify_magic_code(verify_req)

    assert exc_info.value.status_code == 400
    assert "invalid" in exc_info.value.detail.lower()


def test_verify_magic_code_already_used():
    """Test verification with already used code"""
    test_email = "used-code@homeboundapp.com"

    # Create test user and used token
    with db.engine.begin() as connection:
        # Delete old tokens first (due to foreign key constraint)
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )

        # Delete existing user if exists
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Used",
                "last_name": "Code",
                "age": 28
            }
        )
        user_id = result.fetchone()[0]

        test_code = "999999"
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO login_tokens (user_id, email, token, expires_at, used_at)
                VALUES (:user_id, :email, :token, :expires_at, CURRENT_TIMESTAMP)
                """
            ),
            {
                "user_id": user_id,
                "email": test_email,
                "token": test_code,
                "expires_at": datetime.now(UTC) + timedelta(minutes=15)
            }
        )

    verify_req = VerifyRequest(email=test_email, code=test_code)

    with pytest.raises(HTTPException) as exc_info:
        verify_magic_code(verify_req)

    assert exc_info.value.status_code == 400
    assert "already used" in exc_info.value.detail.lower()


def test_verify_magic_code_expired():
    """Test verification with expired code"""
    test_email = "expired@homeboundapp.com"

    # Create test user and expired token
    with db.engine.begin() as connection:
        # Delete old tokens first (due to foreign key constraint)
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        )

        # Delete existing user if exists
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Expired",
                "last_name": "Token",
                "age": 35
            }
        )
        user_id = result.fetchone()[0]

        test_code = "777777"
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO login_tokens (user_id, email, token, expires_at)
                VALUES (:user_id, :email, :token, :expires_at)
                """
            ),
            {
                "user_id": user_id,
                "email": test_email,
                "token": test_code,
                "expires_at": datetime.now(UTC) - timedelta(minutes=1)  # Expired 1 minute ago
            }
        )

    verify_req = VerifyRequest(email=test_email, code=test_code)

    with pytest.raises(HTTPException) as exc_info:
        verify_magic_code(verify_req)

    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()


def test_refresh_token_success():
    """Test successful token refresh"""
    test_email = "refresh@homeboundapp.com"

    # Create test user
    with db.engine.begin() as connection:
        # Delete existing user if exists
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Refresh",
                "last_name": "Test",
                "age": 27
            }
        )
        user_id = result.fetchone()[0]

    # Create a valid refresh token
    _, refresh_token_str = create_jwt_pair(user_id, test_email)

    # Refresh the token
    refresh_req = RefreshRequest(refresh_token=refresh_token_str)
    result = refresh_token(refresh_req)

    assert isinstance(result, TokenResponse)
    assert isinstance(result.access, str)
    assert isinstance(result.refresh, str)
    assert result.user["email"] == test_email
    assert result.user["id"] == user_id


def test_refresh_token_invalid_type():
    """Test refresh with access token instead of refresh token"""
    test_email = "wrongtype@homeboundapp.com"

    # Create test user
    with db.engine.begin() as connection:
        # Delete existing user if exists
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": test_email}
        )

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, :first_name, :last_name, :age, 'free')
                RETURNING id
                """
            ),
            {
                "email": test_email,
                "first_name": "Wrong",
                "last_name": "Type",
                "age": 32
            }
        )
        user_id = result.fetchone()[0]

    # Create an access token (not refresh)
    access_token_str, _ = create_jwt_pair(user_id, test_email)

    # Try to refresh with access token
    refresh_req = RefreshRequest(refresh_token=access_token_str)

    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 400
    assert "invalid token type" in exc_info.value.detail.lower()


def test_refresh_token_expired():
    """Test refresh with expired token"""
    # Create an expired refresh token
    now = datetime.now()
    expired_payload = {
        "iss": "homebound",
        "iat": int((now - timedelta(days=8)).timestamp()),
        "exp": int((now - timedelta(days=1)).timestamp()),  # Expired 1 day ago
        "typ": "refresh",
        "sub": "999",
        "email": "expired@example.com"
    }

    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    refresh_req = RefreshRequest(refresh_token=expired_token)

    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_refresh_token_invalid():
    """Test refresh with malformed token"""
    refresh_req = RefreshRequest(refresh_token="invalid.token.here")

    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


def test_apple_review_test_account_new_user(monkeypatch):
    """Test Apple App Store Review test account creates user"""
    apple_review_email = "apple-review@homeboundapp.com"
    apple_review_code = "123456"

    # Set environment variables for the test
    monkeypatch.setenv("APPLE_REVIEW_EMAIL", apple_review_email)
    monkeypatch.setenv("APPLE_REVIEW_CODE", apple_review_code)

    # Reload the module to pick up the new env vars
    import importlib
    from src.api import auth_endpoints
    importlib.reload(auth_endpoints)
    from src.api.auth_endpoints import verify_magic_code

    # Clean up any existing test user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": apple_review_email}
        )

    # Verify with special test account credentials
    verify_req = VerifyRequest(email=apple_review_email, code=apple_review_code)
    token_response = verify_magic_code(verify_req)

    # Check response has expected attributes (don't use isinstance due to module reload)
    assert hasattr(token_response, 'access')
    assert hasattr(token_response, 'refresh')
    assert hasattr(token_response, 'user')
    assert token_response.user["email"] == apple_review_email
    assert token_response.user["first_name"] == "Apple"
    assert token_response.user["last_name"] == "Reviewer"
    assert token_response.user["profile_completed"] is True

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": apple_review_email}
        )


def test_apple_review_test_account_existing_user(monkeypatch):
    """Test Apple App Store Review test account with existing user"""
    apple_review_email = "apple-review@homeboundapp.com"
    apple_review_code = "123456"

    # Set environment variables for the test
    monkeypatch.setenv("APPLE_REVIEW_EMAIL", apple_review_email)
    monkeypatch.setenv("APPLE_REVIEW_CODE", apple_review_code)

    # Reload the module to pick up the new env vars
    import importlib
    from src.api import auth_endpoints
    importlib.reload(auth_endpoints)
    from src.api.auth_endpoints import verify_magic_code

    # Ensure test user exists
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": apple_review_email}
        )
        connection.execute(
            sqlalchemy.text("""
                INSERT INTO users (email, first_name, last_name, age, subscription_tier)
                VALUES (:email, 'Apple', 'Reviewer', 30, 'free')
            """),
            {"email": apple_review_email}
        )

    # Verify with special test account credentials
    verify_req = VerifyRequest(email=apple_review_email, code=apple_review_code)
    token_response = verify_magic_code(verify_req)

    # Check response has expected attributes (don't use isinstance due to module reload)
    assert hasattr(token_response, 'access')
    assert hasattr(token_response, 'refresh')
    assert hasattr(token_response, 'user')
    assert token_response.user["email"] == apple_review_email

    # Clean up
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": apple_review_email}
        )


# ============================================================================
# get_current_user_id Tests (auth middleware)
# ============================================================================

class MockRequest:
    """Mock FastAPI Request for auth testing"""
    def __init__(self, headers: dict):
        self.headers = headers


@pytest.mark.asyncio
async def test_get_current_user_id_valid_token():
    """Test get_current_user_id with valid token"""
    user_id = 123
    email = "test@example.com"
    access_token, _ = create_jwt_pair(user_id, email)

    request = MockRequest({"authorization": f"Bearer {access_token}"})
    result = await get_current_user_id(request)

    assert result == user_id


@pytest.mark.asyncio
async def test_get_current_user_id_x_auth_token_header():
    """Test get_current_user_id with X-Auth-Token header"""
    user_id = 456
    email = "test2@example.com"
    access_token, _ = create_jwt_pair(user_id, email)

    request = MockRequest({"x-auth-token": f"Bearer {access_token}"})
    result = await get_current_user_id(request)

    assert result == user_id


@pytest.mark.asyncio
async def test_get_current_user_id_missing_token():
    """Test get_current_user_id with missing token"""
    request = MockRequest({})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert "Missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_id_invalid_bearer_format():
    """Test get_current_user_id with non-bearer token"""
    request = MockRequest({"authorization": "Basic sometoken"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_wrong_token_type():
    """Test get_current_user_id with refresh token instead of access"""
    user_id = 789
    email = "test3@example.com"
    _, refresh_token_str = create_jwt_pair(user_id, email)

    request = MockRequest({"authorization": f"Bearer {refresh_token_str}"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert "Invalid token type" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_id_expired_token():
    """Test get_current_user_id with expired token"""
    user_id = 101
    email = "expired@example.com"

    # Create expired token
    expired_payload = {
        "sub": str(user_id),
        "email": email,
        "typ": "access",
        "iss": "homebound",
        "exp": datetime.now(UTC) - timedelta(hours=1)  # Already expired
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    request = MockRequest({"authorization": f"Bearer {expired_token}"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_id_invalid_token():
    """Test get_current_user_id with malformed token"""
    request = MockRequest({"authorization": "Bearer invalid.token.here"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_id_missing_sub():
    """Test get_current_user_id with token missing sub claim"""
    # Create token without sub claim
    payload = {
        "email": "test@example.com",
        "typ": "access",
        "iss": "homebound",
        "exp": datetime.now(UTC) + timedelta(hours=1)
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    request = MockRequest({"authorization": f"Bearer {token}"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert "no sub" in exc_info.value.detail.lower()
