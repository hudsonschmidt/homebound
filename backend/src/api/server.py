import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.cors import CORSMiddleware

from src import config
from src.api import activities, auth_endpoints, checkin, contacts, devices, friends, invite_page, live_activity_tokens, participants, profile, stats, subscriptions, trips
from src.services.scheduler import start_scheduler, stop_scheduler
from src.services.app_store import app_store_service

# Configure logging based on environment
settings = config.get_settings()
log_level = logging.INFO if settings.DEV_MODE else logging.WARNING
logging.basicConfig(level=log_level)
log = logging.getLogger(__name__)

# Rate limiter configuration
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start and stop background services."""
    # Startup
    log.info("Starting background scheduler...")
    start_scheduler()

    # SECURITY WARNING: Check Apple App Store Server API configuration
    if not app_store_service.is_configured:
        if settings.DEV_MODE:
            log.warning(
                "⚠️  Apple App Store Server API not configured. "
                "Purchase verification will trust client-provided data. "
                "This is acceptable for development but MUST be configured for production."
            )
        else:
            log.error(
                "🚨 SECURITY WARNING: Apple App Store Server API not configured in PRODUCTION! "
                "Set APP_STORE_KEY_ID, APP_STORE_ISSUER_ID, and APP_STORE_PRIVATE_KEY. "
                "Without these, malicious clients could claim false purchases."
            )
    else:
        log.info("✅ Apple App Store Server API configured for purchase verification")

    yield
    # Shutdown
    log.info("Stopping background scheduler...")
    stop_scheduler()


description = """
Homebound is a personal safety application that helps users create travel plans,
set up check-in schedules, and automatically notify emergency contacts if they don't
check in on time.
"""

tags_metadata = [
    {"name": "auth", "description": "Authentication and user management"},
    {"name": "trips", "description": "Create and manage safety trips"},
    {"name": "participants", "description": "Group trip participant management"},
    {"name": "activities", "description": "Activity types and configurations"},
    {"name": "contacts", "description": "Manage emergency contacts"},
    {"name": "friends", "description": "Friend management and invites"},
    {"name": "devices", "description": "Device registration for push notifications"},
    {"name": "live-activity", "description": "Live Activity push token management"},
    {"name": "checkin", "description": "Check-in and check-out functionality"},
    {"name": "profile", "description": "User profile management"},
    {"name": "stats", "description": "Platform statistics"},
    {"name": "subscriptions", "description": "Subscription management and premium features"},
]

app = FastAPI(
    title="Homebound API",
    description=description,
    version="1.0.0",
    contact={
        "name": "Homebound Team",
        "email": "support@homeboundapp.com",
    },
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# Add rate limiter to app state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS for mobile and web
# Production origins only - localhost/dev origins removed for security
origins = [
    "capacitor://localhost",  # iOS native WebView
    "ionic://localhost",  # Ionic WebView
    "https://api.homeboundapp.com",
    "https://homeboundapp.com",
    "https://www.homeboundapp.com",
]

# Add localhost origins only in DEV_MODE
if config.get_settings().DEV_MODE:
    origins.extend([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "X-Auth-Token", "Content-Type", "Accept"],
)

# Mount static files for Open Graph images and AASA file
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    # Mount .well-known for Apple App Site Association file
    well_known_dir = static_dir / ".well-known"
    if well_known_dir.exists():
        app.mount("/.well-known", StaticFiles(directory=well_known_dir), name="well-known")

# Include routers
app.include_router(auth_endpoints.router)
app.include_router(trips.router)
app.include_router(participants.router)
app.include_router(activities.router)
app.include_router(contacts.router)
app.include_router(friends.router)
app.include_router(devices.router)
app.include_router(live_activity_tokens.router)
app.include_router(checkin.router)
app.include_router(profile.router)
app.include_router(stats.router)
app.include_router(subscriptions.router)
app.include_router(subscriptions.webhook_router)  # Apple webhook (no auth)
app.include_router(invite_page.router)


@app.get("/")
def root():
    return {"message": "Homebound API is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"ok": True}
