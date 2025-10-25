from __future__ import annotations

from fastapi import APIRouter, Response
from ..core.config import settings

router = APIRouter()

@router.get("/.well-known/apple-app-site-association")
async def aasa() -> Response:
    """
    Apple requires this JSON over HTTPS, no redirects, `Content-Type: application/json`.
    """
    payload = {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": f"{settings.IOS_TEAM_ID}.{settings.IOS_BUNDLE_ID}",
                    "paths": settings.UNIVERSAL_LINK_PATHS_LIST,  # e.g., ["/t/*"]
                }
            ],
        }
    }
    return Response(
        content=__import__("json").dumps(payload, separators=(",", ":")),
        media_type="application/json",
    )
