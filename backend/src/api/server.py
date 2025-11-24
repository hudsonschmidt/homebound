from fastapi import FastAPI
from src.api import auth_endpoints, trips, activities, contacts, devices, checkin, profile
from starlette.middleware.cors import CORSMiddleware

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
    {"name": "devices", "description": "Device registration for push notifications"},
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

# Include routers
app.include_router(auth_endpoints.router)
app.include_router(trips.router)
app.include_router(activities.router)
app.include_router(contacts.router)
app.include_router(devices.router)
app.include_router(checkin.router)
app.include_router(profile.router)


@app.get("/")
def root():
    return {"message": "Homebound API is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"ok": True}
