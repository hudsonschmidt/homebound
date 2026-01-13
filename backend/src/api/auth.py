import logging

from fastapi import HTTPException, Request, status
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from src import config

logger = logging.getLogger(__name__)

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
        logger.debug("Missing bearer token in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token"
        )

    # Split and validate token exists after "Bearer "
    parts = auth.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        logger.debug("Bearer header present but token missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token"
        )
    token = parts[1].strip()

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"leeway": 30}  # Allow 30 seconds clock skew tolerance
        )

        # Verify it's an access token
        if payload.get("typ") != "access":
            logger.debug("Invalid token type: %s", payload.get("typ"))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        sub = payload.get("sub")
        if sub is None:
            logger.debug("No 'sub' claim in token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token (no sub)"
            )

        user_id = int(sub)
        return user_id

    except ExpiredSignatureError:
        logger.debug("Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except (JWTError, ValueError):
        logger.debug("Invalid token")
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

    # Split and validate token exists after "Bearer "
    parts = auth.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        return None
    token = parts[1].strip()

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"leeway": 30}  # Allow 30 seconds clock skew tolerance
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
