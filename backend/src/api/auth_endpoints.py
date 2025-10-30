"""Authentication endpoints using magic link and JWT"""
from datetime import datetime, timedelta
import secrets
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from src import database as db
from src import config
import sqlalchemy

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = config.get_settings()


def parse_datetime(dt):
    """Parse datetime from SQLite string or return datetime object"""
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace(' ', 'T'))
    return dt


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
    now = datetime.utcnow()

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
    with db.engine.begin() as conn:
        # Get or create user
        user = conn.execute(
            sqlalchemy.text("""
                SELECT id, email FROM users WHERE email = :email
            """),
            {"email": body.email}
        ).fetchone()

        if not user:
            # Create new user
            result = conn.execute(
                sqlalchemy.text("""
                    INSERT INTO users (email, created_at, is_active, saved_contacts)
                    VALUES (:email, :now, 1, '{}')
                    RETURNING id, email
                """),
                {"email": body.email, "now": datetime.utcnow()}
            )
            user = result.fetchone()
        else:
            # Update last login
            conn.execute(
                sqlalchemy.text("""
                    UPDATE users SET last_login_at = :now WHERE id = :user_id
                """),
                {"now": datetime.utcnow(), "user_id": user.id}
            )

        # Generate 6-digit code
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        # Store the token
        conn.execute(
            sqlalchemy.text("""
                INSERT INTO login_tokens (user_id, email, token, created_at, expires_at)
                VALUES (:user_id, :email, :token, :created_at, :expires_at)
            """),
            {
                "user_id": user.id,
                "email": body.email,
                "token": code,
                "created_at": datetime.utcnow(),
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
    with db.engine.begin() as conn:
        # Find valid token
        token = conn.execute(
            sqlalchemy.text("""
                SELECT id, user_id, token, expires_at, used_at
                FROM login_tokens
                WHERE email = :email
                AND token = :code
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"email": body.email, "code": body.code}
        ).fetchone()

        if not token:
            raise HTTPException(status_code=400, detail="Invalid or expired code")

        if token.used_at:
            raise HTTPException(status_code=400, detail="Code already used")

        if datetime.utcnow() > parse_datetime(token.expires_at):
            raise HTTPException(status_code=400, detail="Code expired")

        # Mark token as used
        conn.execute(
            sqlalchemy.text("""
                UPDATE login_tokens SET used_at = :now WHERE id = :token_id
            """),
            {"now": datetime.utcnow(), "token_id": token.id}
        )

        # Get user info
        user = conn.execute(
            sqlalchemy.text("""
                SELECT id, email, name, phone, age
                FROM users
                WHERE id = :user_id
            """),
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
                "name": user.name,
                "phone": user.phone,
                "age": user.age,
                "profile_completed": bool(user.name)
            }
        )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest):
    """Exchange refresh token for new access and refresh tokens"""
    try:
        payload = jwt.decode(body.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        if payload.get("typ") != "refresh":
            raise HTTPException(status_code=400, detail="Invalid token type")

        user_id = int(payload["sub"])

        # Verify user still exists
        with db.engine.begin() as conn:
            user = conn.execute(
                sqlalchemy.text("SELECT id, email, name, phone, age FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()

            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Create new JWT pair
            access, refresh = create_jwt_pair(user.id, user.email)

            return TokenResponse(
                access=access,
                refresh=refresh,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "phone": user.phone,
                    "age": user.age,
                    "profile_completed": bool(user.name)
                }
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/_dev/peek-code")
def dev_peek_code(email: str):
    """Development endpoint to peek at latest magic code for an email"""
    if not settings.DEV_MODE:
        raise HTTPException(status_code=404, detail="Not found")

    with db.engine.begin() as conn:
        token = conn.execute(
            sqlalchemy.text("""
                SELECT token, created_at, expires_at, used_at
                FROM login_tokens
                WHERE email = :email
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"email": email}
        ).fetchone()

        if not token:
            return {"error": "No code found for this email"}

        return {
            "email": email,
            "code": token.token,
            "created_at": str(token.created_at),
            "expires_at": str(token.expires_at),
            "used": token.used_at is not None
        }
