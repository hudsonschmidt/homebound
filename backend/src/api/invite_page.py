"""Serve HTML invite page with Open Graph metadata for link previews."""
import logging

import sqlalchemy
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from src import database as db

log = logging.getLogger(__name__)

router = APIRouter(tags=["invite_page"])


@router.get("/f/{token}", response_class=HTMLResponse)
def serve_invite_page(token: str):
    """Serve an HTML page for friend invites with Open Graph metadata.

    This page:
    1. Provides Open Graph meta tags for rich link previews in Messages, etc.
    2. Attempts to open the app via universal link
    3. Falls back to App Store if app is not installed
    """
    # Fetch basic invite info (we don't need much for generic branding)
    with db.engine.begin() as connection:
        invite = connection.execute(
            sqlalchemy.text(
                """
                SELECT fi.id, fi.expires_at,
                       (fi.expires_at > CURRENT_TIMESTAMP AND
                        (fi.max_uses IS NULL OR fi.use_count < fi.max_uses)) as is_valid
                FROM friend_invites fi
                WHERE fi.token = :token
                """
            ),
            {"token": token}
        ).fetchone()

    # Default values for OG tags
    og_title = "You've been invited to Homebound"
    og_description = "Join Homebound - the app that keeps you safe on adventures"
    is_valid = invite.is_valid if invite else False

    if not is_valid:
        og_title = "Invite Expired"
        og_description = "This invite link has expired or is no longer valid"

    # The universal link URL (same as page URL)
    invite_url = f"https://api.homeboundapp.com/f/{token}"

    # Custom URL scheme for opening app from webpage (universal links don't work from same domain)
    app_url = f"homebound://f/{token}"

    # App Store URL for Homebound
    app_store_url = "https://apps.apple.com/app/homebound-safety/id6739498884"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{og_title}</title>

    <!-- Open Graph meta tags for link previews -->
    <meta property="og:title" content="{og_title}">
    <meta property="og:description" content="{og_description}">
    <meta property="og:image" content="https://api.homeboundapp.com/static/og-image.png">
    <meta property="og:url" content="{invite_url}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Homebound">

    <!-- Twitter Card meta tags -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{og_title}">
    <meta name="twitter:description" content="{og_description}">
    <meta name="twitter:image" content="https://api.homeboundapp.com/static/og-image.png">

    <!-- iOS Smart App Banner -->
    <meta name="apple-itunes-app" content="app-id=6739498884, app-argument={invite_url}">

    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            color: white;
        }}
        .container {{
            text-align: center;
            max-width: 400px;
        }}
        .logo {{
            width: 100px;
            height: 100px;
            border-radius: 22px;
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        h1 {{
            font-size: 24px;
            margin-bottom: 12px;
            font-weight: 600;
        }}
        p {{
            font-size: 16px;
            color: rgba(255,255,255,0.7);
            margin-bottom: 32px;
            line-height: 1.5;
        }}
        .button {{
            display: inline-block;
            background: #00C9A7;
            color: white;
            padding: 16px 32px;
            border-radius: 12px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 201, 167, 0.3);
        }}
        .secondary-link {{
            display: block;
            margin-top: 16px;
            color: rgba(255,255,255,0.5);
            font-size: 14px;
            text-decoration: none;
        }}
        .secondary-link:hover {{
            color: rgba(255,255,255,0.8);
        }}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://api.homeboundapp.com/static/og-image.png" alt="Homebound" class="logo">
        <h1>{og_title}</h1>
        <p>{og_description}</p>
        <a href="{app_store_url}" class="button">Get Homebound</a>
        <a href="{app_url}" class="secondary-link">Open in app</a>
    </div>

    <script>
        // Try to open app using custom URL scheme after a short delay
        // This works from JavaScript (unlike universal links which only work from other apps)
        setTimeout(function() {{
            window.location.href = "{app_url}";
        }}, 500);
    </script>
</body>
</html>
"""

    return HTMLResponse(content=html_content)
