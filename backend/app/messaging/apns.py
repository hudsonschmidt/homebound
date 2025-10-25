from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
import jwt

from ..core.config import settings


class PushResult:
    def __init__(self, ok: bool, status: int, detail: str):
        self.ok = ok
        self.status = status
        self.detail = detail

    def dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status, "detail": self.detail}


class DummyPush:
    async def send(self, device_token: str, title: str, body: str, data: Optional[dict] = None) -> PushResult:
        print(f"[DUMMY PUSH] token={device_token} title={title!r} body={body!r} data={data}")
        return PushResult(ok=True, status=200, detail="dummy")


class APNsClient:
    """
    Token-based APNs using HTTP/2.
    Requires:
      - IOS_TEAM_ID  (Apple Developer Team ID)
      - APNS_KEY_ID  (Key ID of your .p8)
      - APNS_PRIVATE_KEY or APNS_PRIVATE_KEY_PATH
      - IOS_BUNDLE_ID (topic)
    """

    def __init__(self) -> None:
        self.team_id = settings.IOS_TEAM_ID
        self.key_id = settings.APNS_KEY_ID
        self.bundle_id = settings.IOS_BUNDLE_ID
        self.private_key = settings.get_apns_private_key()
        self.base_url = (
            "https://api.development.push.apple.com"
            if settings.APNS_USE_SANDBOX
            else "https://api.push.apple.com"
        )
        self._client: Optional[httpx.AsyncClient] = None

    def _provider_jwt(self) -> str:
        now = int(time.time())
        headers = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}
        payload = {"iss": self.team_id, "iat": now}
        return jwt.encode(payload, self.private_key, algorithm="ES256", headers=headers)

    async def _client_ctx(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(http2=True, timeout=10)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send(self, device_token: str, title: str, body: str, data: Optional[dict] = None) -> PushResult:
        c = await self._client_ctx()
        url = f"{self.base_url}/3/device/{device_token}"
        headers = {
            "authorization": f"bearer {self._provider_jwt()}",
            "apns-topic": self.bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "content-type": "application/json",
        }
        payload: Dict[str, Any] = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
            }
        }
        if data:
            payload["data"] = data

        r = await c.post(url, headers=headers, json=payload)
        ok = 200 <= r.status_code < 300
        detail = r.headers.get("apns-id", r.text)
        return PushResult(ok=ok, status=r.status_code, detail=detail)


def get_push_sender():
    if settings.PUSH_BACKEND.lower() == "apns":
        return APNsClient()
    return DummyPush()
