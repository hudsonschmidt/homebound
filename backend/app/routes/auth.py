from __future__ import annotations

from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_session
from ..services.auth import create_magic_link, verify_magic_code, create_jwt_pair

router = APIRouter()


class MagicReq(BaseModel):
    email: EmailStr


class VerifyReq(BaseModel):
    email: EmailStr
    code: str




@router.post("/auth/request-magic-link")
async def request_magic_link(
    body: MagicReq,
    session: AsyncSession = Depends(get_session)
):
    try:
        code = await create_magic_link(session, body.email)

        # Send email with the code
        from ..services.notifications import send_magic_link_email
        await send_magic_link_email(body.email, code)

        # Also log for dev
        print(f"[DEV MAGIC CODE] email={body.email} code={code}")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/verify")
async def verify(
    body: VerifyReq,
    session: AsyncSession = Depends(get_session)
):
    try:
        user = await verify_magic_code(session, body.email, body.code)
        access, refresh = create_jwt_pair(user)
        return {"access": access, "refresh": refresh}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RefreshReq(BaseModel):
    refresh_token: str


@router.post("/auth/refresh")
async def refresh_token(
    body: RefreshReq,
    session: AsyncSession = Depends(get_session)
):
    """Exchange a valid refresh token for new access and refresh tokens."""
    try:
        from ..services.auth import verify_jwt
        payload = verify_jwt(body.refresh_token, expected_type="refresh")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=400, detail="invalid token")

        # Get the user
        from ..models import User
        user = await session.get(User, int(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="user not found or inactive")

        # Issue new tokens
        access, refresh = create_jwt_pair(user)
        return {"access": access, "refresh": refresh}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid refresh token")


# ---- DEV ONLY helper: peek current code for an email ----
@router.get("/auth/_dev/peek-code")
async def dev_peek_code(
    email: str = Query(..., description="email to look up"),
    session: AsyncSession = Depends(get_session)
):
    if settings.APP_ENV != "dev":
        raise HTTPException(status_code=404, detail="not found")

    from sqlalchemy import select
    from ..models import LoginToken

    # Find the most recent unexpired, unused code for this email
    result = await session.execute(
        select(LoginToken)
        .filter_by(email=email.strip().lower())
        .filter(LoginToken.used_at.is_(None))
        .filter(LoginToken.expires_at > datetime.utcnow())
        .order_by(LoginToken.created_at.desc())
        .limit(1)
    )
    token = result.scalar_one_or_none()

    if not token:
        return {"email": email, "code": None}

    return {"email": email, "code": token.token, "expires_at": token.expires_at.isoformat()}
