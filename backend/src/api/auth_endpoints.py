from datetime import datetime, timedelta, timezone
import secrets
import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from src import database as db
from src import config
import sqlalchemy

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

settings = config.get_settings()


class MagicLinkRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access: str
    refresh: str
    user: dict


def create_jwt_pair(user_id: int, email: str) -> tuple[str, str]:
    """Create access and refresh JWT tokens"""
    now = datetime.now()

    access_payload = {
        "iss": "homebound",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "typ": "access",
        "sub": str(user_id),
        "email": email
    }

    refresh_payload = {
        "iss": "homebound",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        "typ": "refresh",
        "sub": str(user_id),
        "email": email
    }

    access = jwt.encode(access_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    refresh = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return access, refresh


@router.post("/request-magic-link")
def request_magic_link(body: MagicLinkRequest):
    """Request a magic link code to be sent to email"""
    with db.engine.begin() as connection:
        # Check if user exists
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email
                FROM users
                WHERE email = :email
                """
            ),
            {"email": body.email}
        ).fetchone()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Create new user."
            )

        # Update last login
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE users
                SET last_login_at = CURRENT_TIMESTAMP
                WHERE id = :user_id
                """
            ),
            {"user_id": user.id}
        )

        # Generate 6-digit code
        code = f"{secrets.randbelow(1000000):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        # Store the token
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO login_tokens (user_id, email, token, expires_at)
                VALUES (:user_id, :email, :token, :expires_at)
                """
            ),
            {
                "user_id": user.id,
                "email": body.email,
                "token": code,
                "expires_at": expires_at
            }
        )

        # In dev mode, print the code
        if settings.DEV_MODE:
            print(f"[DEV MAGIC CODE] email={body.email} code={code}")

        return {"ok": True, "message": "Magic link sent to your email"}


@router.post("/verify", response_model=TokenResponse)
def verify_magic_code(body: VerifyRequest):
    """Verify magic link code and return JWT tokens"""
    with db.engine.begin() as connection:
        # Find valid token
        token = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, token, expires_at, used_at
                FROM login_tokens
                WHERE email = :email
                AND token = :code
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"email": body.email, "code": body.code}
        ).fetchone()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired code"
            )

        if token.used_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code already used"
            )

        expires_at = token.expires_at
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace(' ', 'T'))

        # Ensure expires_at is timezone-aware
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code expired"
            )

        # Mark token as used
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE login_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE id = :token_id
                """
            ),
            {"token_id": token.id}
        )

        # Get user info
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": token.user_id}
        ).fetchone()

        # Create JWT pair
        access, refresh = create_jwt_pair(user.id, user.email)

        return TokenResponse(
            access=access,
            refresh=refresh,
            user={
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "age": user.age
            }
        )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest):
    """Exchange refresh token for new access and refresh tokens"""
    try:
        payload = jwt.decode(
            body.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        if payload.get("typ") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )

        user_id = int(payload["sub"])

        # Verify user still exists
        with db.engine.begin() as connection:
            user = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id, email, first_name, last_name, age
                    FROM users
                    WHERE id = :user_id
                    """
                ),
                {"user_id": user_id}
            ).fetchone()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            # Create new JWT pair
            access, refresh = create_jwt_pair(user.id, user.email)

            return TokenResponse(
                access=access,
                refresh=refresh,
                user={
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "age": user.age
                }
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

