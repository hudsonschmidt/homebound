from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.config import settings

router = APIRouter()


@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association() -> JSONResponse:
    """
    iOS fetches this from your HTTPS domain root.
    Keep it JSON (no .json extension) and serve as application/json.
    """
    payload = {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": f"{settings.IOS_TEAM_ID}.{settings.IOS_BUNDLE_ID}",
                    "paths": settings.UNIVERSAL_LINK_PATHS_LIST,
                }
            ],
        }
    }
    return JSONResponse(payload, media_type="application/json")
