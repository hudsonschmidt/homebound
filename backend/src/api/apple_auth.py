"""Apple Sign In JWT validation utilities."""
import time

import requests
from fastapi import HTTPException, status
from jose import jwk, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError

# Apple's public keys endpoint
APPLE_PUBLIC_KEYS_URL = "https://appleid.apple.com/auth/keys"

# Cache for Apple's public keys (prevents fetching on every request)
_apple_keys_cache: dict | None = None
_apple_keys_cache_time: float = 0
_apple_keys_cache_ttl: int = 3600  # Cache for 1 hour


def _fetch_apple_public_keys() -> dict:
    """
    Fetch Apple's public keys from their JWKS endpoint.

    Returns:
        Dict containing the JWKS (JSON Web Key Set)
    """
    global _apple_keys_cache, _apple_keys_cache_time

    # Check cache first
    current_time = time.time()
    if _apple_keys_cache and (current_time - _apple_keys_cache_time) < _apple_keys_cache_ttl:
        return _apple_keys_cache

    # Fetch fresh keys
    try:
        response = requests.get(APPLE_PUBLIC_KEYS_URL, timeout=10)
        response.raise_for_status()
        keys = response.json()

        # Update cache
        _apple_keys_cache = keys
        _apple_keys_cache_time = current_time

        return keys
    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch Apple public keys: {str(e)}"
        )


def _get_apple_public_key(token: str) -> dict | None:
    """
    Get the specific public key from Apple's JWKS that matches the token's key ID.

    Args:
        token: The JWT token to decode the header from

    Returns:
        The matching public key dictionary, or None if not found
    """
    try:
        # Decode token header without verification to get the key ID (kid)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            return None

        # Fetch Apple's public keys
        keys_data = _fetch_apple_public_keys()

        # Find the key with matching kid
        for key in keys_data.get("keys", []):
            if key.get("kid") == kid:
                return key

        return None
    except JWTError:
        return None


def validate_apple_identity_token(
    identity_token: str,
    expected_audience: str,
    expected_user_id: str | None = None
) -> dict:
    """
    Validate an Apple Sign In identity token.

    This function:
    1. Fetches Apple's public keys
    2. Verifies the JWT signature using the appropriate public key
    3. Validates the token claims (issuer, audience, expiration)
    4. Optionally validates the user ID matches

    Args:
        identity_token: The identity token from Apple Sign In
        expected_audience: Your app's bundle ID (e.g., "com.hudsonschmidt.Homebound")
        expected_user_id: Optional user ID to validate against the token's subject

    Returns:
        Dict containing the validated token payload

    Raises:
        HTTPException: If validation fails
    """
    try:
        # Get the public key for this token
        apple_public_key = _get_apple_public_key(identity_token)

        if not apple_public_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: Could not find matching Apple public key"
            )

        # Convert JWK to PEM format for python-jose
        try:
            public_key_pem = jwk.construct(apple_public_key).to_pem()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to construct public key: {str(e)}"
            )

        # Decode and validate the token
        try:
            payload = jwt.decode(
                identity_token,
                public_key_pem,
                algorithms=["RS256"],
                issuer="https://appleid.apple.com",
                audience=expected_audience,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                }
            )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Apple identity token has expired"
            )
        except JWTClaimsError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token claims: {str(e)}"
            )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )

        # Validate user ID if provided
        if expected_user_id:
            token_user_id = payload.get("sub")
            if token_user_id != expected_user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token user ID does not match expected user ID"
                )

        user_id = payload.get('sub')
        print(f"[AppleAuth] ✅ Validated Apple identity token for user: {user_id}")
        return payload

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any unexpected errors
        print(f"[AppleAuth] ❌ Unexpected error validating Apple token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate Apple identity token"
        )


def clear_apple_keys_cache():
    """Clear the Apple public keys cache. Useful for testing or forcing a refresh."""
    global _apple_keys_cache, _apple_keys_cache_time
    _apple_keys_cache = None
    _apple_keys_cache_time = 0
