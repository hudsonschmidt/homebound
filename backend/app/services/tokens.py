from __future__ import annotations

import base64
import hmac
import secrets
from datetime import datetime
from hashlib import sha256
from typing import Tuple

from ..core.config import settings  # ← go up one level (app/core/config.py)


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64u_dec(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_token(plan_id: int, purpose: str, exp: datetime) -> str:
    """
    Create a compact token: b64(payload) + "." + b64(sig)
    payload = plan_id|purpose|exp_unix|nonce
    """
    nonce = secrets.token_hex(8)
    payload = f"{plan_id}|{purpose}|{int(exp.timestamp())}|{nonce}".encode()
    sig = hmac.new(settings.SECRET_KEY.encode(), payload, sha256).digest()
    return f"{_b64u(payload)}.{_b64u(sig)}"


def verify_token(token: str, expected_purpose: str) -> Tuple[int, str]:
    """
    Verify HMAC and expiry.
    Returns (plan_id, purpose) if valid, else raises ValueError.
    """
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        raise ValueError("invalid token format")

    payload = _b64u_dec(payload_b64)
    sig = _b64u_dec(sig_b64)
    good = hmac.compare_digest(
        hmac.new(settings.SECRET_KEY.encode(), payload, sha256).digest(), sig
    )
    if not good:
        raise ValueError("bad signature")

    try:
        plan_id_s, purpose, exp_s, _nonce = payload.decode().split("|", 3)
        plan_id = int(plan_id_s)
        exp = int(exp_s)
    except Exception as e:  # noqa: BLE001
        raise ValueError("malformed payload") from e

    if purpose != expected_purpose:
        raise ValueError("wrong purpose")
    if exp < int(datetime.utcnow().timestamp()):
        raise ValueError("expired")

    return plan_id, purpose
