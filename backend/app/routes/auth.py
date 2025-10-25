from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..services.auth import create_jwt_pair, create_magic_link, verify_jwt, verify_magic_code

router = APIRouter()


class RequestMagicLinkIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    email: EmailStr
    code: str


class TokenOut(BaseModel):
    token_type: str = "bearer"
    access_token: str
    refresh_token: str
    expires_in: int  # seconds


@router.post("/auth/request-magic-link")
async def request_magic_link(
    payload: RequestMagicLinkIn, session: AsyncSession = Depends(get_session)
):
    link = await create_magic_link(session, payload.email)
    return {"ok": True, "dev_link": link}


@router.post("/auth/verify", response_model=TokenOut)
async def verify(
    payload: VerifyIn, session: AsyncSession = Depends(get_session)
):
    try:
        user = await verify_magic_code(session, payload.email, payload.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    access, refresh = create_jwt_pair(user)
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=3600)


@router.get("/auth/verify", response_model=TokenOut)
async def verify_get(
    email: EmailStr = Query(...),
    code: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    # Dev convenience GET (same as POST)
    try:
        user = await verify_magic_code(session, email, code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    access, refresh = create_jwt_pair(user)
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=3600)


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/auth/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn):
    try:
        _ = verify_jwt(payload.refresh_token, expected_type="refresh")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    # Issue a new access, keep/cycle refresh as-is (simple variant)
    # For stricter control, validate jti/rotation server-side.
    decoded = verify_jwt(payload.refresh_token, expected_type="refresh")
    access = create_jwt_pair(type("User", (), {"id": int(decoded["sub"]), "email": decoded["email"]}))[
        0
    ]
    return TokenOut(access_token=access, refresh_token=payload.refresh_token, expires_in=3600)
