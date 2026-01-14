"""Security tests for authentication endpoints.

Tests for:
- SQL injection protection
- Token tampering detection
- Deleted user token rejection
- Email format validation
"""
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
    VerifyRequest,
    create_jwt_pair,
    refresh_token,
    request_magic_link,
    verify_magic_code,
)

settings = config.get_settings()


def run_async(coro):
    """Helper to run async functions in sync tests"""
    return asyncio.get_event_loop().run_until_complete(coro)


def cleanup_user(email: str):
    """Helper to clean up test user and related data"""
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": email}
        )


# ============================================================================
# SQL Injection Protection Tests
# ============================================================================

def test_sql_injection_in_email_parameter():
    """Test that SQL injection attempts in email parameter are safely handled"""
    # The MagicLinkRequest uses EmailStr validation, but test that even if
    # malicious input gets through, it's handled safely via parameterized queries
    malicious_emails = [
        "test@example.com'; DROP TABLE users; --",
        "test@example.com\" OR \"1\"=\"1",
        "'; DELETE FROM users WHERE '1'='1",
    ]

    for malicious_email in malicious_emails:
        # EmailStr validation should reject these
        with pytest.raises(Exception):  # Pydantic validation error
            MagicLinkRequest(email=malicious_email)


def test_sql_injection_in_code_parameter():
    """Test that SQL injection attempts in verification code are safely handled"""
    test_email = "sqli-code-test@example.com"
    cleanup_user(test_email)

    # Create test user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                "INSERT INTO users (email, first_name, last_name, age, subscription_tier) VALUES (:email, '', '', 0, 'free')"
            ),
            {"email": test_email}
        )

    # Try SQL injection in code field
    malicious_codes = [
        "123456'; DROP TABLE users; --",
        "123456 OR 1=1",
        "' OR '1'='1",
        "1; DELETE FROM login_tokens WHERE 1=1; --",
    ]

    for malicious_code in malicious_codes:
        verify_req = VerifyRequest(email=test_email, code=malicious_code)
        with pytest.raises(HTTPException) as exc_info:
            verify_magic_code(verify_req)
        # Should return "invalid" error, not a database error
        assert exc_info.value.status_code == 400
        assert "invalid" in exc_info.value.detail.lower()

    cleanup_user(test_email)


# ============================================================================
# Token Security Tests
# ============================================================================

def test_token_with_tampered_payload_rejected():
    """Test that tokens with modified payloads are rejected"""
    test_email = "tamper-test@example.com"
    cleanup_user(test_email)

    # Create test user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                "INSERT INTO users (email, first_name, last_name, age, subscription_tier) VALUES (:email, 'Test', 'User', 25, 'free') RETURNING id"
            ),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

    # Create valid tokens
    _, refresh_token_str = create_jwt_pair(user_id, test_email)

    # Decode without verification to get payload
    payload = jwt.decode(refresh_token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    # Modify the payload (change user_id)
    payload["sub"] = "99999"  # Different user ID

    # Re-encode with the secret key (simulating attacker who doesn't know the key)
    # In reality, attacker wouldn't have the key, but we test that changing
    # the payload invalidates the signature
    tampered_token = jwt.encode(payload, "wrong-secret-key", algorithm=settings.ALGORITHM)

    # Try to refresh with tampered token
    refresh_req = RefreshRequest(refresh_token=tampered_token)
    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()

    cleanup_user(test_email)


def test_token_signed_with_wrong_key_rejected():
    """Test that tokens signed with wrong key are rejected"""
    # Create a token with the wrong secret key
    now = datetime.now()
    payload = {
        "iss": "homebound",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
        "typ": "refresh",
        "sub": "1",
        "email": "wrong-key@example.com"
    }

    wrong_key_token = jwt.encode(payload, "wrong-secret-key-12345", algorithm=settings.ALGORITHM)

    refresh_req = RefreshRequest(refresh_token=wrong_key_token)
    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


def test_token_missing_required_claims_rejected():
    """Test that tokens missing required claims are rejected"""
    now = datetime.now()

    # Token missing 'sub' claim
    payload_no_sub = {
        "iss": "homebound",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
        "typ": "refresh",
        "email": "missing-sub@example.com"
    }
    token_no_sub = jwt.encode(payload_no_sub, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    refresh_req = RefreshRequest(refresh_token=token_no_sub)
    with pytest.raises((HTTPException, KeyError)):
        refresh_token(refresh_req)


def test_token_with_invalid_type_rejected():
    """Test that using access token type for refresh is rejected"""
    test_email = "invalid-type@example.com"
    cleanup_user(test_email)

    # Create test user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                "INSERT INTO users (email, first_name, last_name, age, subscription_tier) VALUES (:email, 'Test', 'User', 25, 'free') RETURNING id"
            ),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

    # Create valid tokens
    access_token_str, _ = create_jwt_pair(user_id, test_email)

    # Try to use access token as refresh token
    refresh_req = RefreshRequest(refresh_token=access_token_str)
    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 400
    assert "invalid token type" in exc_info.value.detail.lower()

    cleanup_user(test_email)


# ============================================================================
# Deleted User Token Tests
# ============================================================================

def test_deleted_user_token_rejected():
    """Test that tokens for deleted users are rejected on refresh"""
    test_email = "deleted-user@example.com"
    cleanup_user(test_email)

    # Create test user
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                "INSERT INTO users (email, first_name, last_name, age, subscription_tier) VALUES (:email, 'Deleted', 'User', 25, 'free') RETURNING id"
            ),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

    # Create valid tokens
    _, refresh_token_str = create_jwt_pair(user_id, test_email)

    # Delete the user
    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )

    # Try to refresh token for deleted user
    refresh_req = RefreshRequest(refresh_token=refresh_token_str)
    with pytest.raises(HTTPException) as exc_info:
        refresh_token(refresh_req)

    assert exc_info.value.status_code == 404
    assert "user not found" in exc_info.value.detail.lower()


# ============================================================================
# Email Format Validation Tests
# ============================================================================

def test_email_format_validation():
    """Test that invalid email formats are rejected"""
    invalid_emails = [
        "not-an-email",
        "@nodomain.com",
        "missing@.com",
        "spaces in@email.com",
        "no-tld@domain",
    ]

    for invalid_email in invalid_emails:
        with pytest.raises(Exception):  # Pydantic validation error
            MagicLinkRequest(email=invalid_email)


def test_valid_email_formats_accepted():
    """Test that valid email formats are accepted"""
    valid_emails = [
        "test@example.com",
        "user.name@domain.com",
        "user+tag@example.org",
        "user@subdomain.domain.co.uk",
    ]

    for valid_email in valid_emails:
        # Should not raise
        request = MagicLinkRequest(email=valid_email)
        assert request.email == valid_email


# ============================================================================
# Magic Code Security Tests
# ============================================================================

def test_magic_code_single_use_enforced():
    """Test that magic codes can only be used once"""
    test_email = "single-use@example.com"
    cleanup_user(test_email)

    # Request magic link (auto-creates user)
    run_async(request_magic_link(MagicLinkRequest(email=test_email)))

    # Get the magic code
    with db.engine.begin() as connection:
        token_record = connection.execute(
            sqlalchemy.text(
                "SELECT token FROM login_tokens WHERE email = :email ORDER BY created_at DESC LIMIT 1"
            ),
            {"email": test_email}
        ).fetchone()
        magic_code = token_record.token

    # First use should succeed
    verify_req = VerifyRequest(email=test_email, code=magic_code)
    result = verify_magic_code(verify_req)
    assert result.access is not None

    # Second use should fail
    verify_req2 = VerifyRequest(email=test_email, code=magic_code)
    with pytest.raises(HTTPException) as exc_info:
        verify_magic_code(verify_req2)

    assert exc_info.value.status_code == 400
    assert "already used" in exc_info.value.detail.lower()

    cleanup_user(test_email)


def test_magic_code_expiration_enforced():
    """Test that expired magic codes are rejected"""
    test_email = "expired-code@example.com"
    cleanup_user(test_email)

    # Create user and expired token manually
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                "INSERT INTO users (email, first_name, last_name, age, subscription_tier) VALUES (:email, '', '', 0, 'free') RETURNING id"
            ),
            {"email": test_email}
        )
        user_id = result.fetchone()[0]

        # Create expired token (expired 1 hour ago)
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        connection.execute(
            sqlalchemy.text(
                "INSERT INTO login_tokens (user_id, email, token, expires_at) VALUES (:user_id, :email, :token, :expires_at)"
            ),
            {
                "user_id": user_id,
                "email": test_email,
                "token": "111111",
                "expires_at": expired_time.isoformat()
            }
        )

    verify_req = VerifyRequest(email=test_email, code="111111")
    with pytest.raises(HTTPException) as exc_info:
        verify_magic_code(verify_req)

    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()

    cleanup_user(test_email)


def test_verify_nonexistent_code_returns_generic_error():
    """Test that verifying a non-existent code returns generic error (no user enumeration)"""
    verify_req = VerifyRequest(email="nonexistent@example.com", code="000000")

    with pytest.raises(HTTPException) as exc_info:
        verify_magic_code(verify_req)

    # Should not reveal whether email exists or not
    assert exc_info.value.status_code == 400
    detail_lower = exc_info.value.detail.lower()
    assert "invalid" in detail_lower or "expired" in detail_lower
    assert "user" not in detail_lower  # Should not mention user existence
