from fastapi import HTTPException, Request, status
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from src import config

settings = config.get_settings()

async def get_current_user_id(request: Request) -> int:
    """
    Extract and validate JWT token from Authorization or X-Auth-Token header.
    Returns the user ID from the token's 'sub' claim.

    This is used as a dependency in protected routes.
    """
    # Try X-Auth-Token first (Cloudflare-safe), then fall back to Authorization
    auth = (request.headers.get("x-auth-token") or
            request.headers.get("X-Auth-Token") or
            request.headers.get("authorization") or
            request.headers.get("Authorization"))

    if not auth or not auth.lower().startswith("bearer "):
        print(f"[Auth] ❌ Missing bearer token - headers: {dict(request.headers)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token"
        )

    token = auth.split(" ", 1)[1].strip()
    # Log first/last few chars of token for debugging (not the full token for security)
    token_preview = f"{token[:10]}...{token[-10:]}" if len(token) > 20 else "***"
    print(f"[Auth] 🔍 Validating token: {token_preview}")

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_iat": False}  # Disable iat validation to avoid clock skew issues
        )

        print(f"[Auth] ✅ Token decoded successfully - payload: {payload}")

        # Verify it's an access token
        if payload.get("typ") != "access":
            print(f"[Auth] ❌ Invalid token type: {payload.get('typ')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        sub = payload.get("sub")
        if sub is None:
            print("[Auth] ❌ No 'sub' claim in token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token (no sub)"
            )

        user_id = int(sub)
        print(f"[Auth] ✅ Token valid for user_id: {user_id}")
        return user_id

    except ExpiredSignatureError as e:
        print(f"[Auth] ❌ Token expired: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except (JWTError, ValueError) as e:
        print(f"[Auth] ❌ Invalid token - error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def get_optional_user_id(request: Request) -> int | None:
    """
    Extract and validate JWT token from Authorization or X-Auth-Token header.
    Returns the user ID if valid, or None if no token/invalid token.

    Use this for endpoints that work both authenticated and unauthenticated.
    """
    # Try X-Auth-Token first (Cloudflare-safe), then fall back to Authorization
    auth = (request.headers.get("x-auth-token") or
            request.headers.get("X-Auth-Token") or
            request.headers.get("authorization") or
            request.headers.get("Authorization"))

    if not auth or not auth.lower().startswith("bearer "):
        return None

    token = auth.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_iat": False}
        )

        # Verify it's an access token
        if payload.get("typ") != "access":
            return None

        sub = payload.get("sub")
        if sub is None:
            return None

        return int(sub)

    except (ExpiredSignatureError, JWTError, ValueError):
        return None
