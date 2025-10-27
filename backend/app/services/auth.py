from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import jwt
from pydantic import EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import LoginToken, User

log = logging.getLogger("auth")


def _now() -> datetime:
    return datetime.utcnow()


def _jwt(payload: Dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    to_encode = {
        "iss": settings.JWT_ISSUER,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + expires_delta).timestamp()),
        "typ": token_type,
        **payload,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_jwt_pair(user: User) -> Tuple[str, str]:
    access = _jwt({"sub": str(user.id), "email": user.email}, timedelta(seconds=settings.JWT_ACCESS_EXPIRES_SECONDS), "access")
    refresh = _jwt({"sub": str(user.id), "email": user.email}, timedelta(days=settings.JWT_REFRESH_EXPIRES_DAYS), "refresh")
    return access, refresh


async def upsert_user_by_email(session: AsyncSession, email: EmailStr) -> User:
    res = await session.execute(select(User).where(User.email == str(email)))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(email=str(email), last_login_at=_now())
        session.add(user)
        await session.flush()
    else:
        await session.execute(
            update(User).where(User.id == user.id).values(last_login_at=_now())
        )
    await session.commit()
    await session.refresh(user)
    return user


async def create_magic_link(session: AsyncSession, email: EmailStr) -> str:
    # Get or create user
    user = await upsert_user_by_email(session, email)

    # Generate 6-digit code
    code = f"{secrets.randbelow(1_000_000):06d}"

    expires = _now() + timedelta(minutes=settings.MAGIC_LINK_EXPIRES_MINUTES)
    token = LoginToken(
        user_id=user.id,
        email=str(email),
        token=code,
        expires_at=expires
    )
    session.add(token)
    await session.commit()

    # Link (use POST /verify in production; GET here is for dev convenience)
    verify_qs = f"email={email}&code={code}"
    link_get = f"{settings.PUBLIC_BASE_URL}/api/v1/auth/verify?{verify_qs}"

    log.info("Magic link (dev): %s", link_get)
    log.info("Or POST JSON: {\"email\":\"%s\",\"code\":\"%s\"} to /api/v1/auth/verify", email, code)
    return code  # Return the code for dev purposes


async def verify_magic_code(session: AsyncSession, email: EmailStr, code: str) -> User:
    res = await session.execute(
        select(LoginToken)
        .where(LoginToken.email == str(email))
        .where(LoginToken.token == code)
        .order_by(LoginToken.created_at.desc())
        .limit(1)
    )
    lt = res.scalar_one_or_none()
    if lt is None or lt.used_at is not None or lt.expires_at < _now():
        raise ValueError("invalid or expired code")

    lt.used_at = _now()
    await session.commit()

    # Get the user from the token relationship
    await session.refresh(lt, ["user"])
    user = lt.user

    # Update user's last login
    user.last_login_at = _now()
    await session.commit()

    return user


def verify_jwt(token: str, expected_type: str = "access") -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], options={"require": ["exp", "iss"]})
    except jwt.PyJWTError as e:  # noqa: PERF203
        raise ValueError(str(e)) from e
    if payload.get("typ") != expected_type:
        raise ValueError("wrong token type")
    return payload


async def clean_expired_tokens(session: AsyncSession) -> int:
    """Clean up expired login tokens."""
    from sqlalchemy import delete

    result = await session.execute(
        delete(LoginToken).where(
            (LoginToken.expires_at < _now()) |
            (LoginToken.used_at.isnot(None))
        )
    )
    await session.commit()
    return result.rowcount
