from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import User
from ..services.auth import create_magic_link, verify_magic_code, create_jwt_pair, get_current_user_id

router = APIRouter()


class MagicReq(BaseModel):
    email: EmailStr


class VerifyReq(BaseModel):
    email: EmailStr
    code: str


api_key_header = APIKeyHeader(name="access_token", auto_error=False)


async def get_api_key(request: Request, api_key_header: str = Security(api_key_header)):
    print(f"api_key_header: {api_key_header}, api_key: {api_key}")
    if api_key_header == api_key:
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Forbidden"
        )


@router.post("/auth/request-magic-link")
async def request_magic_link(
    body: MagicReq,
    session: AsyncSession = Depends(get_db)
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
    session: AsyncSession = Depends(get_db)
):
    try:
        user = await verify_magic_code(session, body.email, body.code)
        access, refresh = create_jwt_pair(user)
        return {
            "access": access,
            "refresh": refresh,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "age": getattr(user, 'age', None),
                "phone": user.phone,
                "profile_completed": bool(user.name)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RefreshReq(BaseModel):
    refresh_token: str


@router.post("/auth/refresh")
async def refresh_token(
    body: RefreshReq,
    session: AsyncSession = Depends(get_db)
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
    session: AsyncSession = Depends(get_db)
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


class ProfileUpdateReq(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None


@router.get("/auth/profile")
async def get_profile(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """Get current user profile."""
    user_id = get_current_user_id(request)

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "age": getattr(user, 'age', None),
        "phone": user.phone,
        "profile_completed": bool(user.name)
    }


@router.put("/auth/profile")
async def update_profile(
    request: Request,
    body: ProfileUpdateReq,
    session: AsyncSession = Depends(get_db),
):
    """Update user profile information."""
    user_id = get_current_user_id(request)

    # Build update values
    update_values = {}
    if body.name is not None:
        update_values["name"] = body.name
    if body.age is not None:
        update_values["age"] = body.age
    if body.phone is not None:
        update_values["phone"] = body.phone

    if not update_values:
        return {"ok": False, "message": "No fields to update"}

    # Update user
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(**update_values)
    )
    await session.commit()

    # Get updated user
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one()

    return {
        "ok": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "age": getattr(user, 'age', None),
            "phone": user.phone,
            "profile_completed": bool(user.name)
        }
    }


@router.patch("/auth/profile")
async def patch_profile(
    request: Request,
    body: ProfileUpdateReq,
    session: AsyncSession = Depends(get_db),
):
    """Partially update user profile information (same as PUT but for PATCH compatibility)."""
    return await update_profile(request, body, session)


@router.delete("/auth/account")
async def delete_account(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Delete user account and all associated data."""
    user_id = get_current_user_id(request)

    # Delete the user (cascading will handle related data)
    await session.execute(
        delete(User).where(User.id == user_id)
    )
    await session.commit()

    return {"ok": True, "message": "Account deleted successfully"}
