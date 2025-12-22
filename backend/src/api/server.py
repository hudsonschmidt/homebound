import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from src.api import activities, auth_endpoints, checkin, contacts, devices, friends, invite_page, live_activity_tokens, profile, trips
from src.services.scheduler import start_scheduler, stop_scheduler

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start and stop background services."""
    # Startup
    log.info("Starting background scheduler...")
    start_scheduler()
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
    {"name": "activities", "description": "Activity types and configurations"},
    {"name": "contacts", "description": "Manage emergency contacts"},
    {"name": "friends", "description": "Friend management and invites"},
    {"name": "devices", "description": "Device registration for push notifications"},
    {"name": "live-activity", "description": "Live Activity push token management"},
    {"name": "checkin", "description": "Check-in and check-out functionality"},
    {"name": "profile", "description": "User profile management"},
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

# Configure CORS for mobile and web
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "capacitor://localhost",
    "ionic://localhost",
    "https://api.homeboundapp.com",
    "https://homeboundapp.com",
    "https://www.homeboundapp.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(activities.router)
app.include_router(contacts.router)
app.include_router(friends.router)
app.include_router(devices.router)
app.include_router(live_activity_tokens.router)
app.include_router(checkin.router)
app.include_router(profile.router)
app.include_router(invite_page.router)


@app.get("/")
def root():
    return {"message": "Homebound API is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"ok": True}
