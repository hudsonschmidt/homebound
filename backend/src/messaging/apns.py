from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt  # PyJWT

from ..config import settings

log = logging.getLogger(__name__)


class PushResult:
    def __init__(self, ok: bool, status: int, detail: str):
        self.ok = ok
        self.status = status
        self.detail = detail

    def dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status, "detail": self.detail}


class DummyPush:
    async def send(self, device_token: str, title: str, body: str, data: dict | None = None) -> PushResult:
        print(f"[DUMMY PUSH] token={device_token} title={title!r} body={body!r} data={data}")
        return PushResult(ok=True, status=200, detail="dummy")


class APNsClient:
    """
    Token-based APNs using HTTP/2.
    Requires:
      - APNS_TEAM_ID  (Apple Developer Team ID)
      - APNS_KEY_ID  (Key ID of your .p8)
      - APNS_PRIVATE_KEY or APNS_AUTH_KEY_PATH
      - APNS_BUNDLE_ID (topic)
    """

    def __init__(self) -> None:
        self.team_id = settings.APNS_TEAM_ID
        self.key_id = settings.APNS_KEY_ID
        self.bundle_id = settings.APNS_BUNDLE_ID
        self.private_key = settings.get_apns_private_key()
        self.base_url = (
            "https://api.development.push.apple.com"
            if settings.APNS_USE_SANDBOX
            else "https://api.push.apple.com"
        )
        self._client: httpx.AsyncClient | None = None
        # Cache JWT to avoid TooManyProviderTokenUpdates (429) from Apple
        self._cached_jwt: str | None = None
        self._jwt_issued_at: float = 0

        # Log configuration for debugging
        key_len = len(self.private_key) if self.private_key else 0
        key_valid = self.private_key.startswith("-----BEGIN PRIVATE KEY-----") if self.private_key else False
        log.info(f"[APNS] Initialized: team={self.team_id}, key={self.key_id}, "
                 f"bundle={self.bundle_id}, sandbox={settings.APNS_USE_SANDBOX}")
        log.info(f"[APNS] Private key: len={key_len}, valid_format={key_valid}")

    def _provider_jwt(self) -> str:
        now = int(time.time())
        # Reuse cached JWT if less than 50 minutes old (Apple allows 60 min)
        if self._cached_jwt is not None and (now - self._jwt_issued_at) < 3000:
            return self._cached_jwt
        # Note: Apple APNs only requires 'alg' and 'kid' - do NOT include 'typ'
        headers = {"alg": "ES256", "kid": self.key_id}
        payload = {"iss": self.team_id, "iat": now}
        # PyJWT returns str directly (not bytes) in recent versions
        token = jwt.encode(payload, self.private_key, algorithm="ES256", headers=headers)
        self._cached_jwt = token if isinstance(token, str) else token.decode("utf-8")
        self._jwt_issued_at = now
        log.debug("[APNS] Generated new provider JWT")
        return self._cached_jwt

    async def _client_ctx(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(http2=True, timeout=10)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send(self, device_token: str, title: str, body: str, data: dict | None = None) -> PushResult:
        c = await self._client_ctx()
        url = f"{self.base_url}/3/device/{device_token}"
        headers = {
            "authorization": f"bearer {self._provider_jwt()}",
            "apns-topic": self.bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
            }
        }
        if data:
            payload["data"] = data

        r = await c.post(url, headers=headers, json=payload)
        ok = 200 <= r.status_code < 300
        if ok:
            detail = r.headers.get("apns-id", "success")
        else:
            # For errors, the reason is in the response JSON body
            try:
                error_body = r.json()
                detail = error_body.get("reason", r.text)
            except Exception:
                detail = r.text or r.headers.get("apns-id", "unknown error")
        return PushResult(ok=ok, status=r.status_code, detail=detail)


def get_push_sender():
    if settings.PUSH_BACKEND.lower() == "apns":
        return APNsClient()
    return DummyPush()
