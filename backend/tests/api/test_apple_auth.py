"""Tests for Apple Sign In JWT validation."""
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError

from src.api.apple_auth import (
    _fetch_apple_public_keys,
    _get_apple_public_key,
    clear_apple_keys_cache,
    validate_apple_identity_token,
)


# Sample JWKS response structure (simplified for testing)
MOCK_APPLE_JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-id-1",
            "use": "sig",
            "alg": "RS256",
            "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
            "e": "AQAB"
        },
        {
            "kty": "RSA",
            "kid": "test-key-id-2",
            "use": "sig",
            "alg": "RS256",
            "n": "2a2B_NFDG4rUJsYE7d_7TqTbgPg1PWf1P_7_zVDm1Dp1k7kVNS_Q1eTUQAQ8iQ3Qk1_XVUJz3VPD1q1Hc3DhKVy2y_qVH3YqMBLHJ3y2V0P3h0l_TxNHJ-2vXvBl-_J-",
            "e": "AQAB"
        }
    ]
}


class TestFetchApplePublicKeys:
    """Tests for _fetch_apple_public_keys function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_apple_keys_cache()

    def test_fetch_keys_success(self):
        """Test successful fetch of Apple public keys."""
        with patch("src.api.apple_auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_APPLE_JWKS
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            keys = _fetch_apple_public_keys()

            assert keys == MOCK_APPLE_JWKS
            mock_get.assert_called_once()

    def test_fetch_keys_uses_cache(self):
        """Test that subsequent calls use cached keys."""
        with patch("src.api.apple_auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_APPLE_JWKS
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # First call fetches
            keys1 = _fetch_apple_public_keys()
            # Second call should use cache
            keys2 = _fetch_apple_public_keys()

            assert keys1 == keys2
            # Only one HTTP call should be made
            assert mock_get.call_count == 1

    def test_fetch_keys_network_error(self):
        """Test handling of network errors when fetching keys."""
        import requests

        with patch("src.api.apple_auth.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")

            with pytest.raises(HTTPException) as exc_info:
                _fetch_apple_public_keys()

            assert exc_info.value.status_code == 503
            assert "Unable to verify Apple credentials" in exc_info.value.detail

    def test_fetch_keys_http_error(self):
        """Test handling of HTTP errors when fetching keys."""
        import requests

        with patch("src.api.apple_auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
            mock_get.return_value = mock_response

            with pytest.raises(HTTPException) as exc_info:
                _fetch_apple_public_keys()

            assert exc_info.value.status_code == 503


class TestGetApplePublicKey:
    """Tests for _get_apple_public_key function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_apple_keys_cache()

    def test_get_key_matching_kid(self):
        """Test finding a key with matching kid."""
        mock_token = "some.jwt.token"

        with patch("src.api.apple_auth.jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"alg": "RS256", "kid": "test-key-id-1"}

            with patch("src.api.apple_auth._fetch_apple_public_keys") as mock_fetch:
                mock_fetch.return_value = MOCK_APPLE_JWKS

                key = _get_apple_public_key(mock_token)

                assert key is not None
                assert key["kid"] == "test-key-id-1"

    def test_get_key_no_matching_kid(self):
        """Test when no key matches the token's kid."""
        mock_token = "some.jwt.token"

        with patch("src.api.apple_auth.jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"alg": "RS256", "kid": "unknown-kid"}

            with patch("src.api.apple_auth._fetch_apple_public_keys") as mock_fetch:
                mock_fetch.return_value = MOCK_APPLE_JWKS

                key = _get_apple_public_key(mock_token)

                assert key is None

    def test_get_key_no_kid_in_token(self):
        """Test when token header has no kid."""
        mock_token = "some.jwt.token"

        with patch("src.api.apple_auth.jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"alg": "RS256"}  # No kid

            key = _get_apple_public_key(mock_token)

            assert key is None

    def test_get_key_invalid_token(self):
        """Test handling of invalid token format."""
        key = _get_apple_public_key("not-a-valid-jwt")
        assert key is None


class TestValidateAppleIdentityToken:
    """Tests for validate_apple_identity_token function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_apple_keys_cache()

    def test_validate_no_matching_key(self):
        """Test validation fails when no matching public key found."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InVua25vd24ifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                validate_apple_identity_token(mock_token, "com.test.app")

            assert exc_info.value.status_code == 401
            assert "Could not find matching Apple public key" in exc_info.value.detail

    def test_validate_key_construction_error(self):
        """Test handling of key construction errors."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = {"invalid": "key"}

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with pytest.raises(HTTPException) as exc_info:
                validate_apple_identity_token(mock_token, "com.test.app")

            assert exc_info.value.status_code == 500
            assert "Failed to verify Apple credentials" in exc_info.value.detail

    def test_validate_expired_token(self):
        """Test that expired tokens are rejected."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_pem = MagicMock()
                mock_pem.to_pem.return_value = b"mock-pem"
                mock_construct.return_value = mock_pem

                with patch("src.api.apple_auth.jwt.decode") as mock_decode:
                    mock_decode.side_effect = ExpiredSignatureError("Token expired")

                    with pytest.raises(HTTPException) as exc_info:
                        validate_apple_identity_token(mock_token, "com.test.app")

                    assert exc_info.value.status_code == 401
                    assert "expired" in exc_info.value.detail

    def test_validate_invalid_claims(self):
        """Test that tokens with invalid claims are rejected."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_pem = MagicMock()
                mock_pem.to_pem.return_value = b"mock-pem"
                mock_construct.return_value = mock_pem

                with patch("src.api.apple_auth.jwt.decode") as mock_decode:
                    mock_decode.side_effect = JWTClaimsError("Invalid audience")

                    with pytest.raises(HTTPException) as exc_info:
                        validate_apple_identity_token(mock_token, "com.test.app")

                    assert exc_info.value.status_code == 401
                    assert "Invalid Apple credentials" in exc_info.value.detail

    def test_validate_jwt_error(self):
        """Test handling of general JWT errors."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_pem = MagicMock()
                mock_pem.to_pem.return_value = b"mock-pem"
                mock_construct.return_value = mock_pem

                with patch("src.api.apple_auth.jwt.decode") as mock_decode:
                    mock_decode.side_effect = JWTError("Invalid signature")

                    with pytest.raises(HTTPException) as exc_info:
                        validate_apple_identity_token(mock_token, "com.test.app")

                    assert exc_info.value.status_code == 401
                    assert "Invalid Apple credentials" in exc_info.value.detail

    def test_validate_success(self):
        """Test successful token validation."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]
        expected_payload = {
            "sub": "apple-user-123",
            "email": "user@example.com",
            "email_verified": True
        }

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_pem = MagicMock()
                mock_pem.to_pem.return_value = b"mock-pem"
                mock_construct.return_value = mock_pem

                with patch("src.api.apple_auth.jwt.decode") as mock_decode:
                    mock_decode.return_value = expected_payload

                    result = validate_apple_identity_token(mock_token, "com.test.app")

                    assert result == expected_payload

    def test_validate_user_id_mismatch(self):
        """Test that mismatched user ID is rejected."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]
        payload = {"sub": "apple-user-123"}

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_pem = MagicMock()
                mock_pem.to_pem.return_value = b"mock-pem"
                mock_construct.return_value = mock_pem

                with patch("src.api.apple_auth.jwt.decode") as mock_decode:
                    mock_decode.return_value = payload

                    with pytest.raises(HTTPException) as exc_info:
                        validate_apple_identity_token(
                            mock_token,
                            "com.test.app",
                            expected_user_id="different-user"
                        )

                    assert exc_info.value.status_code == 401
                    assert "user ID does not match" in exc_info.value.detail

    def test_validate_user_id_match(self):
        """Test that matching user ID succeeds."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]
        expected_user_id = "apple-user-123"
        payload = {"sub": expected_user_id}

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_pem = MagicMock()
                mock_pem.to_pem.return_value = b"mock-pem"
                mock_construct.return_value = mock_pem

                with patch("src.api.apple_auth.jwt.decode") as mock_decode:
                    mock_decode.return_value = payload

                    result = validate_apple_identity_token(
                        mock_token,
                        "com.test.app",
                        expected_user_id=expected_user_id
                    )

                    assert result["sub"] == expected_user_id

    def test_validate_unexpected_error(self):
        """Test handling of unexpected errors during validation."""
        mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        mock_key = MOCK_APPLE_JWKS["keys"][0]

        with patch("src.api.apple_auth._get_apple_public_key") as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch("src.api.apple_auth.jwk.construct") as mock_construct:
                mock_construct.side_effect = RuntimeError("Unexpected error")

                with pytest.raises(HTTPException) as exc_info:
                    validate_apple_identity_token(mock_token, "com.test.app")

                # Should be caught and wrapped in 500 error
                assert exc_info.value.status_code == 500


class TestClearAppleKeysCache:
    """Tests for clear_apple_keys_cache function."""

    def test_clear_cache(self):
        """Test that cache is properly cleared."""
        # First, populate the cache
        with patch("src.api.apple_auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_APPLE_JWKS
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            _fetch_apple_public_keys()
            assert mock_get.call_count == 1

            # Clear cache
            clear_apple_keys_cache()

            # Next fetch should make a new HTTP call
            _fetch_apple_public_keys()
            assert mock_get.call_count == 2
