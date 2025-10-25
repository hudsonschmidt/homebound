from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import jwt
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

from ..core.config import settings

router = APIRouter()

# In-memory dev store for magic codes (OK for local dev only)
_MAGIC: dict[str, tuple[str, datetime]] = {}


class MagicReq(BaseModel):
    email: EmailStr


class VerifyReq(BaseModel):
    email: EmailStr
    code: str


def _canon_email(email: str) -> str:
    # be forgiving: strip spaces and lowercase
    return email.strip().lower()


def _issue_code(email: str) -> str:
    email_key = _canon_email(email)
    code = f"{__import__('secrets').randbelow(1_000_000):06d}"
    _MAGIC[email_key] = (code, datetime.utcnow() + timedelta(minutes=10))
    print(f"[DEV MAGIC LINK] email={email_key} code={code}")
    return code


def _verify_code(email: str, code: str) -> SimpleNamespace:
    email_key = _canon_email(email)
    code = code.strip()
    item = _MAGIC.get(email_key)
    if not item:
        raise HTTPException(status_code=400, detail="no code for email")
    saved, exp = item
    if datetime.utcnow() > exp:
        raise HTTPException(status_code=400, detail="code expired")
    if code != saved:
        raise HTTPException(status_code=400, detail="invalid code")
    # Stable pseudo user id derived from email (dev-only)
    uid = int.from_bytes(__import__("hashlib").sha256(email_key.encode()).digest()[:6], "big")
    return SimpleNamespace(id=uid, email=email_key)


def _jwt(payload: dict, seconds: int) -> str:
    payload = dict(payload)
    payload["exp"] = datetime.utcnow() + timedelta(seconds=seconds)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


@router.post("/auth/request-magic-link")
async def request_magic_link(body: MagicReq):
    _issue_code(body.email)
    # In prod you’d email a link; for dev we just log the code.
    return {"ok": True}


@router.post("/auth/verify")
async def verify(body: VerifyReq):
    user = _verify_code(body.email, body.code)
    access = _jwt(
        {"sub": str(user.id), "email": user.email},
        getattr(settings, "JWT_ACCESS_EXPIRES_SECONDS", 3600),
    )
    refresh = _jwt(
        {"sub": str(user.id), "type": "refresh"},
        getattr(settings, "JWT_REFRESH_EXPIRES_SECONDS", 30 * 24 * 3600),
    )
    return {"access": access, "refresh": refresh}


# ---- DEV ONLY helper: peek current code for an email ----
@router.get("/auth/_dev/peek-code")
async def dev_peek_code(email: str = Query(..., description="email to look up")):
    if settings.APP_ENV != "dev":
        raise HTTPException(status_code=404, detail="not found")
    key = _canon_email(email)
    item = _MAGIC.get(key)
    if not item:
        return {"email": key, "code": None}
    code, exp = item
    return {"email": key, "code": code, "expires_at": exp.isoformat()}
