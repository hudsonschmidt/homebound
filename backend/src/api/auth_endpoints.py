import secrets
from datetime import UTC, datetime, timedelta

import sqlalchemy
from fastapi import APIRouter, HTTPException, status
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from pydantic import BaseModel, EmailStr

from src import config
from src import database as db
from src.api.apple_auth import validate_apple_identity_token
from src.services.notifications import send_magic_link_email

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"]
)

settings = config.get_settings()

# Apple App Store Review test account
APPLE_REVIEW_EMAIL = "apple-review@homeboundapp.com"
APPLE_REVIEW_CODE = "123456"


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

    print(f"[Auth] ✅ Created JWT pair for user_id={user_id}, email={email}")
    print(f"[Auth] Access token expires in {settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes")
    print(f"[Auth] Using SECRET_KEY: {settings.SECRET_KEY[:5]}...{settings.SECRET_KEY[-5:]}")

    return access, refresh


@router.post("/request-magic-link")
async def request_magic_link(body: MagicLinkRequest):
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
            # Create new user account with default values
            result = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO users (email, first_name, last_name, age)
                    VALUES (:email, :first_name, :last_name, :age)
                    RETURNING id, email
                    """
                ),
                {
                    "email": body.email,
                    "first_name": "",
                    "last_name": "",
                    "age": 0
                }
            )
            user = result.fetchone()
            assert user is not None
        else:
            # Update last login for existing user
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
        expires_at = datetime.now(UTC) + timedelta(minutes=15)

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

        # Send email with magic link code
        await send_magic_link_email(body.email, code)

        return {"ok": True, "message": "Magic link sent to your email"}


@router.post("/verify", response_model=TokenResponse)
def verify_magic_code(body: VerifyRequest):
    """Verify magic link code and return JWT tokens"""
    with db.engine.begin() as connection:
        # Special case: Apple App Store Review test account
        if body.email == APPLE_REVIEW_EMAIL and body.code == APPLE_REVIEW_CODE:

            # Get or create the test user
            user = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id, email, first_name, last_name, age
                    FROM users
                    WHERE email = :email
                    """
                ),
                {"email": APPLE_REVIEW_EMAIL}
            ).fetchone()

            if not user:
                # Create the test user with completed profile
                result = connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO users (email, first_name, last_name, age)
                        VALUES (:email, :first_name, :last_name, :age)
                        RETURNING id, email, first_name, last_name, age
                        """
                    ),
                    {
                        "email": APPLE_REVIEW_EMAIL,
                        "first_name": "Apple",
                        "last_name": "Reviewer",
                        "age": 30
                    }
                )
                user = result.fetchone()

            # Create JWT pair for test user
            access, refresh = create_jwt_pair(user.id, user.email)

            return TokenResponse(
                access=access,
                refresh=refresh,
                user={
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "age": user.age,
                    "profile_completed": True
                }
            )

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
            expires_at = expires_at.replace(tzinfo=UTC)

        if datetime.now(UTC) > expires_at:
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
        assert user is not None

        # Create JWT pair
        access, refresh = create_jwt_pair(user.id, user.email)

        # Determine if profile is completed (has name and valid age)
        profile_completed = (
            bool(user.first_name and user.first_name.strip()) and
            bool(user.last_name and user.last_name.strip()) and
            user.age > 0
        )

        return TokenResponse(
            access=access,
            refresh=refresh,
            user={
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "age": user.age,
                "profile_completed": profile_completed
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

            # Determine if profile is completed (has name and valid age)
            profile_completed = (
                bool(user.first_name and user.first_name.strip()) and
                bool(user.last_name and user.last_name.strip()) and
                user.age > 0
            )

            return TokenResponse(
                access=access,
                refresh=refresh,
                user={
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "age": user.age,
                    "profile_completed": profile_completed
                }
            )

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# MARK: - Sign in with Apple Endpoints

class AppleSignInRequest(BaseModel):
    identity_token: str
    user_id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class AppleSignInResponse(BaseModel):
    account_exists: bool
    email: str
    access: str | None = None
    refresh: str | None = None
    user: dict | None = None


@router.post("/apple", response_model=AppleSignInResponse)
def apple_sign_in(body: AppleSignInRequest):
    """
    Authenticate or create user via Sign in with Apple

    Flow:
    1. Validate identity_token with Apple's public keys
    2. Check if apple_user_id exists in database
    3. If exists: Return JWT tokens for existing user
    4. If not exists + email matches existing user: Return account_exists=True
    5. If not exists + no email match: Create new user and return tokens
    """
    # Validate the Apple identity token
    token_payload = validate_apple_identity_token(
        identity_token=body.identity_token,
        expected_audience=settings.APPLE_BUNDLE_ID,
        expected_user_id=body.user_id
    )

    print(f"[AppleAuth] ✅ Token validated for user: {token_payload.get('sub')}")

    with db.engine.begin() as connection:
        # Check if Apple user ID already exists
        existing_user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age
                FROM users
                WHERE apple_user_id = :apple_user_id
                """
            ),
            {"apple_user_id": body.user_id}
        ).fetchone()

        if existing_user:
            # User exists with this Apple ID - sign them in
            print(f"[AppleAuth] ✅ Existing Apple user found: user_id={existing_user.id}")

            access, refresh = create_jwt_pair(existing_user.id, existing_user.email)

            profile_completed = (
                bool(existing_user.first_name and existing_user.first_name.strip()) and
                bool(existing_user.last_name and existing_user.last_name.strip()) and
                existing_user.age > 0
            )

            return AppleSignInResponse(
                account_exists=False,
                email=existing_user.email,
                access=access,
                refresh=refresh,
                user={
                    "id": existing_user.id,
                    "email": existing_user.email,
                    "first_name": existing_user.first_name,
                    "last_name": existing_user.last_name,
                    "age": existing_user.age,
                    "profile_completed": profile_completed
                }
            )

        # Check if email matches an existing account (without Apple ID)
        if body.email:
            email_match = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id, email
                    FROM users
                    WHERE email = :email AND apple_user_id IS NULL
                    """
                ),
                {"email": body.email}
            ).fetchone()

            if email_match:
                # Account exists with this email - prompt user to link
                print(f"[AppleAuth] ⚠️  Email {body.email} exists - requiring confirmation")
                return AppleSignInResponse(
                    account_exists=True,
                    email=body.email,
                    access=None,
                    refresh=None,
                    user=None
                )

        # No existing account - create new user
        print(f"[AppleAuth] 🆕 Creating new account for Apple user_id={body.user_id}")

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age, apple_user_id)
                VALUES (:email, :first_name, :last_name, :age, :apple_user_id)
                RETURNING id, email, first_name, last_name, age
                """
            ),
            {
                "email": body.email or f"{body.user_id}@appleid.private",
                "first_name": body.first_name or "",
                "last_name": body.last_name or "",
                "age": 0,
                "apple_user_id": body.user_id
            }
        )
        new_user = result.fetchone()
        assert new_user is not None

        access, refresh = create_jwt_pair(new_user.id, new_user.email)

        # New users always need to complete profile (age required)
        profile_completed = False

        return AppleSignInResponse(
            account_exists=False,
            email=new_user.email,
            access=access,
            refresh=refresh,
            user={
                "id": new_user.id,
                "email": new_user.email,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "age": new_user.age,
                "profile_completed": profile_completed
            }
        )


class AppleLinkRequest(BaseModel):
    identity_token: str
    user_id: str
    email: str


@router.post("/apple/link")
def link_apple_account(body: AppleLinkRequest):
    """
    Link Apple ID to existing account (user must first authenticate with magic link)

    This endpoint is called after user confirms they want to link their Apple ID
    to an existing email-based account.
    """
    # Validate the Apple identity token
    token_payload = validate_apple_identity_token(
        identity_token=body.identity_token,
        expected_audience=settings.APPLE_BUNDLE_ID,
        expected_user_id=body.user_id
    )

    print(f"[AppleAuth] ✅ Linking validated token for user: {token_payload.get('sub')}")

    with db.engine.begin() as connection:
        # Find user by email (they should have authenticated via magic link first)
        user = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, email, first_name, last_name, age, apple_user_id
                FROM users
                WHERE email = :email
                """
            ),
            {"email": body.email}
        ).fetchone()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if user.apple_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This account is already linked to an Apple ID"
            )

        # Link the Apple ID to this account
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE users
                SET apple_user_id = :apple_user_id
                WHERE id = :user_id
                """
            ),
            {"apple_user_id": body.user_id, "user_id": user.id}
        )

        print(f"[AppleAuth] 🔗 Linked Apple ID to user_id={user.id}, email={user.email}")

        # Generate new tokens
        access, refresh = create_jwt_pair(user.id, user.email)

        profile_completed = (
            bool(user.first_name and user.first_name.strip()) and
            bool(user.last_name and user.last_name.strip()) and
            user.age > 0
        )

        return TokenResponse(
            access=access,
            refresh=refresh,
            user={
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "age": user.age,
                "profile_completed": profile_completed
            }
        )

