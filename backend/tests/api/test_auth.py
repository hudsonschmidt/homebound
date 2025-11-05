from datetime import datetime, timedelta, timezone
import pytest
import jwt
from src import database as db
from src import config
import sqlalchemy
from src.api.auth_endpoints import (
    MagicLinkRequest,
    VerifyRequest,
    RefreshRequest,
    TokenResponse,
    create_jwt_pair,
    request_magic_link,
    verify_magic_code,
    refresh_token
)
from fastapi import HTTPException

settings = config.get_settings()


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
                    INSERT INTO users (email, first_name, last_name, age)
                    VALUES (:email, :first_name, :last_name, :age)
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
    result = request_magic_link(request)

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
    """Test requesting magic link for non-existent user"""
    request = MagicLinkRequest(email="nonexistent@example.com")

    with pytest.raises(HTTPException) as exc_info:
        request_magic_link(request)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
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

        # Create a magic token
        test_code = "123456"
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
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15)
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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
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
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15)
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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
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
                "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)  # Expired 1 minute ago
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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
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
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, :first_name, :last_name, :age)
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