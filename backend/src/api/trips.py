"""Trip management endpoints"""
import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Optional

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.api.activities import Activity
from src.services.geocoding import reverse_geocode_sync
from src.services.notifications import (
    send_trip_created_emails,
    send_trip_extended_emails,
    send_trip_starting_now_emails,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/trips",
    tags=["trips"],
    dependencies=[Depends(auth.get_current_user_id)]
)


def parse_json_field(value, expected_type):
    """Parse JSON field from database, handling both parsed and string forms."""
    if isinstance(value, expected_type):
        return value
    return json.loads(value)


def to_iso8601(dt: datetime | str | None) -> str | None:
    """Convert datetime to ISO8601 string format, handling both datetime objects and strings"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        # If already a string, try to parse and re-format to ensure ISO8601
        try:
            # Try parsing as datetime string (handles space-separated format)
            parsed = datetime.fromisoformat(dt.replace(' ', 'T').replace('Z', '+00:00'))
            return parsed.isoformat()
        except (ValueError, AttributeError):
            # If parsing fails, return as-is
            return dt
    # Fallback for any other type (unreachable with current type hints but kept for safety)
    return str(dt)  # type: ignore[unreachable]  # pragma: no cover


def to_iso8601_required(dt: datetime | str | None) -> str:
    """Convert datetime to ISO8601 string, raises if None."""
    result = to_iso8601(dt)
    if result is None:
        raise ValueError("Required datetime field is None")
    return result


class TripCreate(BaseModel):
    title: str
    activity: str  # Activity name reference
    start: datetime
    eta: datetime
    grace_min: int
    location_text: str | None = None
    gen_lat: float | None = None
    gen_lon: float | None = None
    start_location_text: str | None = None  # Optional start location for trips with separate start/end
    start_lat: float | None = None
    start_lon: float | None = None
    has_separate_locations: bool = False  # True if trip has separate start and destination
    notes: str | None = None
    contact1: int | None = None  # Contact ID reference
    contact2: int | None = None
    contact3: int | None = None
    timezone: str | None = None  # User's timezone (e.g., "America/New_York") - used for notifications
    start_timezone: str | None = None  # Timezone for start time (e.g., "America/Los_Angeles")
    eta_timezone: str | None = None  # Timezone for return time (e.g., "America/New_York")
    checkin_interval_min: int = 30  # Minutes between check-in reminders
    notify_start_hour: int | None = None  # Hour (0-23) when notifications start
    notify_end_hour: int | None = None  # Hour (0-23) when notifications end


class TripUpdate(BaseModel):
    """Model for updating an existing trip. All fields are optional."""
    title: str | None = None
    activity: str | None = None  # Activity name reference
    start: datetime | None = None
    eta: datetime | None = None
    grace_min: int | None = None
    location_text: str | None = None
    gen_lat: float | None = None
    gen_lon: float | None = None
    start_location_text: str | None = None
    start_lat: float | None = None
    start_lon: float | None = None
    has_separate_locations: bool | None = None
    notes: str | None = None
    contact1: int | None = None  # Contact ID reference
    contact2: int | None = None
    contact3: int | None = None
    timezone: str | None = None
    start_timezone: str | None = None
    eta_timezone: str | None = None
    checkin_interval_min: int | None = None
    notify_start_hour: int | None = None
    notify_end_hour: int | None = None


class TripResponse(BaseModel):
    id: int
    user_id: int
    title: str
    activity: Activity  # Full activity object with safety tips, colors, messages
    start: str
    eta: str
    grace_min: int
    location_text: str | None
    gen_lat: float | None
    gen_lon: float | None
    start_location_text: str | None
    start_lat: float | None
    start_lon: float | None
    has_separate_locations: bool
    notes: str | None
    status: str
    completed_at: str | None
    last_checkin: str | None
    created_at: str
    contact1: int | None
    contact2: int | None
    contact3: int | None
    checkin_token: str | None
    checkout_token: str | None
    checkin_interval_min: int | None
    notify_start_hour: int | None
    notify_end_hour: int | None
    timezone: str | None
    start_timezone: str | None
    eta_timezone: str | None


class TimelineEvent(BaseModel):
    id: int
    kind: str
    at: str
    lat: float | None
    lon: float | None
    extended_by: int | None


@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    body: TripCreate,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Create a new trip"""
    # Log incoming request for debugging
    log.info(f"[Trips] Creating trip for user_id={user_id}")
    log.info(f"[Trips] title={body.title}, activity={body.activity}")
    log.info(f"[Trips] start={body.start}, eta={body.eta}")
    log.info(f"[Trips] Contacts: {body.contact1}, {body.contact2}, {body.contact3}")
    log.info(f"[Trips] Location: {body.location_text}, ({body.gen_lat}, {body.gen_lon})")

    # Validate that at least contact1 is provided (required by database)
    if body.contact1 is None:
        log.warning("[Trips] No contact1 provided")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one emergency contact (contact1) is required"
        )

    with db.engine.begin() as connection:
        # Verify activity exists and get its ID
        # Normalize activity name: convert to lowercase and replace underscores with spaces
        # This allows "scuba_diving" to match "Scuba Diving"
        normalized_activity = body.activity.lower().replace('_', ' ')
        log.info(f"[Trips] Looking up activity: '{body.activity}' -> '{normalized_activity}'")

        activity = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, name
                FROM activities
                WHERE LOWER(REPLACE(name, ' ', '_')) = LOWER(REPLACE(:activity, ' ', '_'))
                """
            ),
            {"activity": body.activity}
        ).fetchone()

        if not activity:
            # List available activities for debugging
            all_activities = connection.execute(
                sqlalchemy.text("SELECT id, name FROM activities")
            ).fetchall()
            log.warning(f"[Trips] Activity '{body.activity}' not found!")
            available = [a.name for a in all_activities]
            log.info(f"[Trips] Available activities: {available}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Activity '{body.activity}' not found. Available: {available}"
            )

        log.info(f"[Trips] Activity found: id={activity.id}, name='{activity.name}'")

        activity_id = activity.id

        # Verify contacts exist if provided
        log.info("[Trips] Verifying contacts...")
        for contact_id in [body.contact1, body.contact2, body.contact3]:
            if contact_id is not None:
                log.info(f"[Trips] Checking contact_id={contact_id}")
                contact = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT id
                        FROM contacts
                        WHERE id = :contact_id AND user_id = :user_id
                        """
                    ),
                    {"contact_id": contact_id, "user_id": user_id}
                ).fetchone()

                if not contact:
                    # List user's contacts for debugging
                    user_contacts = connection.execute(
                        sqlalchemy.text(
                            "SELECT id, name FROM contacts WHERE user_id = :user_id"
                        ),
                        {"user_id": user_id}
                    ).fetchall()
                    log.warning(f"[Trips] Contact {contact_id} not found!")
                    contact_ids_available = [c.id for c in user_contacts]
                    log.info(f"[Trips] User's contacts: {contact_ids_available}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Contact {contact_id} not found. Available: {contact_ids_available}"
                    )

                log.info(f"[Trips] Contact {contact_id} verified")

        # Generate unique tokens for checkin/checkout
        checkin_token = secrets.token_urlsafe(32)
        checkout_token = secrets.token_urlsafe(32)

        # Determine initial status based on start time
        current_time = datetime.now(UTC)
        # Ensure start time is timezone-aware for comparison
        start_time = body.start if body.start.tzinfo else body.start.replace(tzinfo=UTC)
        initial_status = 'planned' if start_time > current_time else 'active'

        # Resolve "Current Location" to a proper place name via reverse geocoding
        location_text = body.location_text
        log.info(f"[Trips] Location: '{location_text}' at ({body.gen_lat}, {body.gen_lon})")
        if location_text and location_text.lower().strip() == "current location":
            log.info("[Trips] Detected 'Current Location', checking coordinates...")
            # Check for valid coordinates (not None and not 0,0)
            has_valid_coords = (
                body.gen_lat is not None and
                body.gen_lon is not None and
                (body.gen_lat != 0.0 or body.gen_lon != 0.0)
            )
            if has_valid_coords:
                log.info(f"[Trips] Reverse geocoding at ({body.gen_lat}, {body.gen_lon})")
                assert body.gen_lat is not None and body.gen_lon is not None
                geocoded = reverse_geocode_sync(body.gen_lat, body.gen_lon)
                if geocoded:
                    location_text = geocoded
                    log.info(f"[Trips] Geocoded to: {location_text}")
                else:
                    log.warning("[Trips] Geocoding failed, keeping 'Current Location'")
            else:
                log.warning(f"[Trips] No valid coords: ({body.gen_lat}, {body.gen_lon})")

        # Resolve "Current Location" for start location if separate locations are used
        start_location_text = body.start_location_text
        if body.has_separate_locations and start_location_text and start_location_text.lower().strip() == "current location":
            log.info("[Trips] Detected 'Current Location' for start, checking coordinates...")
            has_valid_start_coords = (
                body.start_lat is not None and
                body.start_lon is not None and
                (body.start_lat != 0.0 or body.start_lon != 0.0)
            )
            if has_valid_start_coords:
                log.info(f"[Trips] Reverse geocoding start at ({body.start_lat}, {body.start_lon})")
                assert body.start_lat is not None and body.start_lon is not None
                geocoded_start = reverse_geocode_sync(body.start_lat, body.start_lon)
                if geocoded_start:
                    start_location_text = geocoded_start
                    log.info(f"[Trips] Start geocoded to: {start_location_text}")
                else:
                    log.warning("[Trips] Start geocoding failed, keeping 'Current Location'")

        # Insert trip
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon,
                    start_location_text, start_lat, start_lon, has_separate_locations,
                    notes, status,
                    contact1, contact2, contact3, created_at,
                    checkin_token, checkout_token, timezone, start_timezone, eta_timezone,
                    checkin_interval_min, notify_start_hour, notify_end_hour
                ) VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon,
                    :start_location_text, :start_lat, :start_lon, :has_separate_locations,
                    :notes, :status,
                    :contact1, :contact2, :contact3, :created_at,
                    :checkin_token, :checkout_token, :timezone, :start_timezone, :eta_timezone,
                    :checkin_interval_min, :notify_start_hour, :notify_end_hour
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": body.title,
                "activity": activity_id,
                "start": body.start.isoformat(),
                "eta": body.eta.isoformat(),
                "grace_min": body.grace_min,
                "location_text": location_text or "Unknown Location",  # Default if not provided
                "gen_lat": body.gen_lat if body.gen_lat is not None else 0.0,  # Default to 0.0
                "gen_lon": body.gen_lon if body.gen_lon is not None else 0.0,  # Default to 0.0
                "start_location_text": start_location_text if body.has_separate_locations else None,
                "start_lat": body.start_lat if body.has_separate_locations else None,
                "start_lon": body.start_lon if body.has_separate_locations else None,
                "has_separate_locations": body.has_separate_locations,
                "notes": body.notes,
                "status": initial_status,
                "contact1": body.contact1,
                "contact2": body.contact2,
                "contact3": body.contact3,
                "created_at": datetime.now(UTC).isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token,
                "timezone": body.timezone,
                "start_timezone": body.start_timezone,
                "eta_timezone": body.eta_timezone,
                "checkin_interval_min": body.checkin_interval_min,
                "notify_start_hour": body.notify_start_hour,
                "notify_end_hour": body.notify_end_hour
            }
        )
        row = result.fetchone()
        assert row is not None
        trip_id = row[0]

        # Fetch created trip with full activity data
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon,
                       t.start_location_text, t.start_lat, t.start_lon, t.has_separate_locations,
                       t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
                       t.checkin_interval_min, t.notify_start_hour, t.notify_end_hour,
                       t.timezone, t.start_timezone, t.eta_timezone,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).mappings().fetchone()
        assert trip is not None

        # Construct Activity object from trip data
        activity_obj = Activity(
            id=trip["activity_id"],
            name=trip["activity_name"],
            icon=trip["activity_icon"],
            default_grace_minutes=trip["default_grace_minutes"],
            colors=parse_json_field(trip["activity_colors"], dict),
            messages=parse_json_field(trip["activity_messages"], dict),
            safety_tips=parse_json_field(trip["safety_tips"], list),
            order=trip["activity_order"]
        )

        # Fetch user name for email notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"

        # Fetch contacts with email for notification
        all_contact_ids = [body.contact1, body.contact2, body.contact3]
        contact_ids = [cid for cid in all_contact_ids if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            query = f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"
            contacts_result = connection.execute(
                sqlalchemy.text(query),
                params
            ).fetchall()
            contacts_for_email = [dict(c._mapping) for c in contacts_result]

        # Build trip dict for email notification
        trip_data = {
            "title": trip["title"],
            "start": trip["start"],
            "eta": trip["eta"],
            "location_text": trip["location_text"]
        }

        # Capture timezone, status, and start location for closure
        user_timezone = body.timezone
        is_starting_now = initial_status == 'active'
        # Only include start location if trip has separate start/destination
        trip_start_location = trip["start_location_text"] if trip["has_separate_locations"] else None

        # Schedule background task to send emails to contacts
        # Use different email templates based on whether trip is starting now or upcoming
        def send_emails_sync():
            if is_starting_now:
                # Trip is starting immediately - send "starting now" email
                asyncio.run(send_trip_starting_now_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_obj.name,
                    user_timezone=user_timezone,
                    start_location=trip_start_location
                ))
            else:
                # Trip is scheduled for later - send "upcoming trip" email
                asyncio.run(send_trip_created_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_obj.name,
                    user_timezone=user_timezone,
                    start_location=trip_start_location
                ))

        background_tasks.add_task(send_emails_sync)
        email_type = "starting now" if is_starting_now else "upcoming trip"
        num_contacts = len(contacts_for_email)
        log.info(f"[Trips] Scheduled {email_type} emails for {num_contacts} contacts")

        return TripResponse(
            id=trip["id"],
            user_id=trip["user_id"],
            title=trip["title"],
            activity=activity_obj,
            start=to_iso8601_required(trip["start"]),
            eta=to_iso8601_required(trip["eta"]),
            grace_min=trip["grace_min"],
            location_text=trip["location_text"],
            gen_lat=trip["gen_lat"],
            gen_lon=trip["gen_lon"],
            start_location_text=trip["start_location_text"],
            start_lat=trip["start_lat"],
            start_lon=trip["start_lon"],
            has_separate_locations=trip["has_separate_locations"],
            notes=trip["notes"],
            status=trip["status"],
            completed_at=to_iso8601(trip["completed_at"]),
            last_checkin=to_iso8601(trip["last_checkin"]),
            created_at=to_iso8601_required(trip["created_at"]),
            contact1=trip["contact1"],
            contact2=trip["contact2"],
            contact3=trip["contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"],
            checkin_interval_min=trip["checkin_interval_min"],
            notify_start_hour=trip["notify_start_hour"],
            notify_end_hour=trip["notify_end_hour"],
            timezone=trip["timezone"],
            start_timezone=trip["start_timezone"],
            eta_timezone=trip["eta_timezone"]
        )


@router.get("/", response_model=list[TripResponse])
def get_trips(user_id: int = Depends(auth.get_current_user_id)):
    """Get all trips for the current user with full activity data"""
    with db.engine.begin() as connection:
        trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon,
                       t.start_location_text, t.start_lat, t.start_lon, t.has_separate_locations,
                       t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
                       t.checkin_interval_min, t.notify_start_hour, t.notify_end_hour,
                       t.timezone, t.start_timezone, t.eta_timezone,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.user_id = :user_id
                ORDER BY t.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).mappings().fetchall()

        result = []
        for trip in trips:
            # Construct Activity object for each trip
            activity = Activity(
                id=trip["activity_id"],
                name=trip["activity_name"],
                icon=trip["activity_icon"],
                default_grace_minutes=trip["default_grace_minutes"],
                colors=parse_json_field(trip["activity_colors"], dict),
                messages=parse_json_field(trip["activity_messages"], dict),
                safety_tips=parse_json_field(trip["safety_tips"], list),
                order=trip["activity_order"]
            )

            result.append(
                TripResponse(
                    id=trip["id"],
                    user_id=trip["user_id"],
                    title=trip["title"],
                    activity=activity,
                    start=to_iso8601_required(trip["start"]),
                    eta=to_iso8601_required(trip["eta"]),
                    grace_min=trip["grace_min"],
                    location_text=trip["location_text"],
                    gen_lat=trip["gen_lat"],
                    gen_lon=trip["gen_lon"],
                    start_location_text=trip["start_location_text"],
                    start_lat=trip["start_lat"],
                    start_lon=trip["start_lon"],
                    has_separate_locations=trip["has_separate_locations"],
                    notes=trip["notes"],
                    status=trip["status"],
                    completed_at=to_iso8601(trip["completed_at"]),
                    last_checkin=to_iso8601(trip["last_checkin"]),
                    created_at=to_iso8601_required(trip["created_at"]),
                    contact1=trip["contact1"],
                    contact2=trip["contact2"],
                    contact3=trip["contact3"],
                    checkin_token=trip["checkin_token"],
                    checkout_token=trip["checkout_token"],
                    checkin_interval_min=trip["checkin_interval_min"],
                    notify_start_hour=trip["notify_start_hour"],
                    notify_end_hour=trip["notify_end_hour"],
                    timezone=trip["timezone"],
                    start_timezone=trip["start_timezone"],
                    eta_timezone=trip["eta_timezone"]
                )
            )

        return result


@router.get("/active", response_model=Optional[TripResponse])
def get_active_trip(user_id: int = Depends(auth.get_current_user_id)):
    """Get the current active trip with full activity data including safety tips.

    Returns trips that are active, overdue, or overdue_notified - all require user action.
    """
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon,
                       t.start_location_text, t.start_lat, t.start_lon, t.has_separate_locations,
                       t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
                       t.checkin_interval_min, t.notify_start_hour, t.notify_end_hour,
                       t.timezone, t.start_timezone, t.eta_timezone,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.user_id = :user_id AND t.status IN ('active', 'overdue', 'overdue_notified')
                ORDER BY t.created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id}
        ).mappings().fetchone()

        if not trip:
            return None

        # Construct Activity object from trip data
        activity = Activity(
            id=trip["activity_id"],
            name=trip["activity_name"],
            icon=trip["activity_icon"],
            default_grace_minutes=trip["default_grace_minutes"],
            colors=parse_json_field(trip["activity_colors"], dict),
            messages=parse_json_field(trip["activity_messages"], dict),
            safety_tips=parse_json_field(trip["safety_tips"], list),
            order=trip["activity_order"]
        )

        return TripResponse(
            id=trip["id"],
            user_id=trip["user_id"],
            title=trip["title"],
            activity=activity,
            start=to_iso8601_required(trip["start"]),
            eta=to_iso8601_required(trip["eta"]),
            grace_min=trip["grace_min"],
            location_text=trip["location_text"],
            gen_lat=trip["gen_lat"],
            gen_lon=trip["gen_lon"],
            start_location_text=trip["start_location_text"],
            start_lat=trip["start_lat"],
            start_lon=trip["start_lon"],
            has_separate_locations=trip["has_separate_locations"],
            notes=trip["notes"],
            status=trip["status"],
            completed_at=to_iso8601(trip["completed_at"]),
            last_checkin=to_iso8601(trip["last_checkin"]),
            created_at=to_iso8601_required(trip["created_at"]),
            contact1=trip["contact1"],
            contact2=trip["contact2"],
            contact3=trip["contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"],
            checkin_interval_min=trip["checkin_interval_min"],
            notify_start_hour=trip["notify_start_hour"],
            notify_end_hour=trip["notify_end_hour"],
            timezone=trip["timezone"],
            start_timezone=trip["start_timezone"],
            eta_timezone=trip["eta_timezone"]
        )


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific trip with full activity data"""
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon,
                       t.start_location_text, t.start_lat, t.start_lon, t.has_separate_locations,
                       t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
                       t.checkin_interval_min, t.notify_start_hour, t.notify_end_hour,
                       t.timezone, t.start_timezone, t.eta_timezone,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id AND t.user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).mappings().fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Construct Activity object from trip data
        activity = Activity(
            id=trip["activity_id"],
            name=trip["activity_name"],
            icon=trip["activity_icon"],
            default_grace_minutes=trip["default_grace_minutes"],
            colors=parse_json_field(trip["activity_colors"], dict),
            messages=parse_json_field(trip["activity_messages"], dict),
            safety_tips=parse_json_field(trip["safety_tips"], list),
            order=trip["activity_order"]
        )

        return TripResponse(
            id=trip["id"],
            user_id=trip["user_id"],
            title=trip["title"],
            activity=activity,
            start=to_iso8601_required(trip["start"]),
            eta=to_iso8601_required(trip["eta"]),
            grace_min=trip["grace_min"],
            location_text=trip["location_text"],
            gen_lat=trip["gen_lat"],
            gen_lon=trip["gen_lon"],
            start_location_text=trip["start_location_text"],
            start_lat=trip["start_lat"],
            start_lon=trip["start_lon"],
            has_separate_locations=trip["has_separate_locations"],
            notes=trip["notes"],
            status=trip["status"],
            completed_at=to_iso8601(trip["completed_at"]),
            last_checkin=to_iso8601(trip["last_checkin"]),
            created_at=to_iso8601_required(trip["created_at"]),
            contact1=trip["contact1"],
            contact2=trip["contact2"],
            contact3=trip["contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"],
            checkin_interval_min=trip["checkin_interval_min"],
            notify_start_hour=trip["notify_start_hour"],
            notify_end_hour=trip["notify_end_hour"],
            timezone=trip["timezone"],
            start_timezone=trip["start_timezone"],
            eta_timezone=trip["eta_timezone"]
        )


@router.put("/{trip_id}", response_model=TripResponse)
def update_trip(
    trip_id: int,
    body: TripUpdate,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Update a planned trip. Only trips with status 'planned' can be edited."""
    log.info(f"[Trips] Updating trip {trip_id} for user_id={user_id}")

    with db.engine.begin() as connection:
        # Verify trip ownership and status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, activity
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        if trip.status != "planned":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only planned trips can be edited"
            )

        # Build update fields dynamically based on what's provided
        update_fields = []
        params = {"trip_id": trip_id, "user_id": user_id}

        # Handle activity update (need to look up activity ID)
        if body.activity is not None:
            activity = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id, name
                    FROM activities
                    WHERE LOWER(REPLACE(name, ' ', '_')) = LOWER(REPLACE(:activity, ' ', '_'))
                    """
                ),
                {"activity": body.activity}
            ).fetchone()

            if not activity:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Activity '{body.activity}' not found"
                )
            update_fields.append("activity = :activity_id")
            params["activity_id"] = activity.id

        # Handle contact validation if any contacts are being updated
        for contact_field in ["contact1", "contact2", "contact3"]:
            contact_id = getattr(body, contact_field)
            if contact_id is not None:
                contact = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT id
                        FROM contacts
                        WHERE id = :contact_id AND user_id = :user_id
                        """
                    ),
                    {"contact_id": contact_id, "user_id": user_id}
                ).fetchone()

                if not contact:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Contact {contact_id} not found"
                    )
                update_fields.append(f"{contact_field} = :{contact_field}")
                params[contact_field] = contact_id

        # Handle simple field updates
        simple_fields = {
            "title": body.title,
            "grace_min": body.grace_min,
            "location_text": body.location_text,
            "gen_lat": body.gen_lat,
            "gen_lon": body.gen_lon,
            "start_location_text": body.start_location_text,
            "start_lat": body.start_lat,
            "start_lon": body.start_lon,
            "has_separate_locations": body.has_separate_locations,
            "notes": body.notes,
            "timezone": body.timezone,
            "start_timezone": body.start_timezone,
            "eta_timezone": body.eta_timezone,
            "checkin_interval_min": body.checkin_interval_min,
            "notify_start_hour": body.notify_start_hour,
            "notify_end_hour": body.notify_end_hour,
        }

        for field, value in simple_fields.items():
            if value is not None:
                update_fields.append(f"{field} = :{field}")
                params[field] = value

        # Handle datetime fields
        if body.start is not None:
            update_fields.append("start = :start")
            params["start"] = body.start.isoformat()

        if body.eta is not None:
            update_fields.append("eta = :eta")
            params["eta"] = body.eta.isoformat()

        # Execute update if there are fields to update
        if update_fields:
            update_sql = f"""
                UPDATE trips
                SET {", ".join(update_fields)}
                WHERE id = :trip_id
            """
            connection.execute(sqlalchemy.text(update_sql), params)
            log.info(f"[Trips] Updated trip {trip_id}: {update_fields}")

        # Fetch updated trip with full activity data
        updated_trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon,
                       t.start_location_text, t.start_lat, t.start_lon, t.has_separate_locations,
                       t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
                       t.checkin_interval_min, t.notify_start_hour, t.notify_end_hour,
                       t.timezone, t.start_timezone, t.eta_timezone,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).mappings().fetchone()
        assert updated_trip is not None

        # Construct Activity object
        activity_obj = Activity(
            id=updated_trip["activity_id"],
            name=updated_trip["activity_name"],
            icon=updated_trip["activity_icon"],
            default_grace_minutes=updated_trip["default_grace_minutes"],
            colors=parse_json_field(updated_trip["activity_colors"], dict),
            messages=parse_json_field(updated_trip["activity_messages"], dict),
            safety_tips=parse_json_field(updated_trip["safety_tips"], list),
            order=updated_trip["activity_order"]
        )

        return TripResponse(
            id=updated_trip["id"],
            user_id=updated_trip["user_id"],
            title=updated_trip["title"],
            activity=activity_obj,
            start=to_iso8601_required(updated_trip["start"]),
            eta=to_iso8601_required(updated_trip["eta"]),
            grace_min=updated_trip["grace_min"],
            location_text=updated_trip["location_text"],
            gen_lat=updated_trip["gen_lat"],
            gen_lon=updated_trip["gen_lon"],
            start_location_text=updated_trip["start_location_text"],
            start_lat=updated_trip["start_lat"],
            start_lon=updated_trip["start_lon"],
            has_separate_locations=updated_trip["has_separate_locations"],
            notes=updated_trip["notes"],
            status=updated_trip["status"],
            completed_at=to_iso8601(updated_trip["completed_at"]),
            last_checkin=to_iso8601(updated_trip["last_checkin"]),
            created_at=to_iso8601_required(updated_trip["created_at"]),
            contact1=updated_trip["contact1"],
            contact2=updated_trip["contact2"],
            contact3=updated_trip["contact3"],
            checkin_token=updated_trip["checkin_token"],
            checkout_token=updated_trip["checkout_token"],
            checkin_interval_min=updated_trip["checkin_interval_min"],
            notify_start_hour=updated_trip["notify_start_hour"],
            notify_end_hour=updated_trip["notify_end_hour"],
            timezone=updated_trip["timezone"],
            start_timezone=updated_trip["start_timezone"],
            eta_timezone=updated_trip["eta_timezone"]
        )


@router.post("/{trip_id}/complete")
def complete_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Mark a trip as completed"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Allow completing active, overdue, or overdue_notified trips
        if trip.status not in ("active", "overdue", "overdue_notified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not active or overdue"
            )

        # Update trip status
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET status = 'completed', completed_at = :completed_at
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id, "completed_at": datetime.now(UTC).isoformat()}
        )

        return {"ok": True, "message": "Trip completed successfully"}


@router.post("/{trip_id}/start")
def start_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Start a planned trip (change status from 'planned' to 'active')"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, start
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        if trip.status != "planned":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not in planned status"
            )

        # Update trip status to active
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET status = 'active'
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        )

        return {"ok": True, "message": "Trip started successfully"}


@router.post("/{trip_id}/extend")
def extend_trip(
    trip_id: int,
    minutes: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Extend the ETA of an active or overdue trip by the specified number of minutes.

    This also acts as a check-in, confirming the user is okay and resetting overdue status.
    """
    with db.engine.begin() as connection:
        # Verify trip ownership and status - also fetch title, activity, and timezone for emails
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.status, t.eta, t.title, t.contact1, t.contact2, t.contact3,
                       t.timezone, a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id AND t.user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Allow extending active, overdue, or overdue_notified trips
        if trip.status not in ("active", "overdue", "overdue_notified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only extend active or overdue trips"
            )

        # Parse current ETA and add minutes
        from datetime import timedelta
        if isinstance(trip.eta, datetime):
            current_eta = trip.eta
        else:
            current_eta = datetime.fromisoformat(trip.eta)
        new_eta = current_eta + timedelta(minutes=minutes)

        now = datetime.now(UTC)

        # Log checkin event first (extending is also a check-in) and get the event ID
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": now.isoformat()
            }
        )
        row = result.fetchone()
        assert row is not None
        checkin_event_id = row[0]

        # Update trip ETA and reset status to active (user is checking in)
        # last_checkin stores the event ID, not a timestamp
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET eta = :new_eta, status = 'active', last_checkin = :last_checkin
                WHERE id = :trip_id
                """
            ),
            {
                "trip_id": trip_id,
                "new_eta": new_eta.isoformat(),
                "last_checkin": checkin_event_id
            }
        )

        # Log extend event
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp, extended_by)
                VALUES (:user_id, :trip_id, 'extended', :timestamp, :extended_by)
                """
            ),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": now.isoformat(),
                "extended_by": minutes
            }
        )

        # Fetch user name for email notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"

        # Fetch contacts with email for notification
        all_contact_ids = [trip.contact1, trip.contact2, trip.contact3]
        contact_ids = [cid for cid in all_contact_ids if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            query = f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"
            contacts_result = connection.execute(
                sqlalchemy.text(query),
                params
            ).fetchall()
            contacts_for_email = [dict(c._mapping) for c in contacts_result]

        # Build trip dict for email notification (with new ETA)
        trip_data = {
            "title": trip.title,
            "eta": new_eta.isoformat()
        }
        activity_name = trip.activity_name
        extended_by = minutes
        user_timezone = trip.timezone

        # Schedule background task to send extended trip emails to contacts
        def send_emails_sync():
            asyncio.run(send_trip_extended_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name,
                extended_by_minutes=extended_by,
                user_timezone=user_timezone
            ))

        background_tasks.add_task(send_emails_sync)
        num_contacts = len(contacts_for_email)
        log.info(f"[Trips] Scheduled extended trip emails for {num_contacts} contacts")

        new_eta_iso = new_eta.isoformat()
        return {
            "ok": True,
            "message": f"Trip extended by {minutes} minutes",
            "new_eta": new_eta_iso
        }


@router.delete("/{trip_id}")
def delete_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Delete a trip"""
    with db.engine.begin() as connection:
        # Verify trip ownership
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Clear the last_checkin reference first (foreign key constraint)
        connection.execute(
            sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )

        # Delete events
        connection.execute(
            sqlalchemy.text("DELETE FROM events WHERE trip_id = :trip_id"),
            {"trip_id": trip_id}
        )

        # Now delete the trip
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )

        return {"ok": True, "message": "Trip deleted successfully"}


@router.get("/{trip_id}/timeline", response_model=list[TimelineEvent])
def get_trip_timeline(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get timeline events for a specific trip"""
    with db.engine.begin() as connection:
        # Verify trip ownership
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Fetch timeline events
        events = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, what AS kind, timestamp AS at, lat, lon, extended_by
                FROM events
                WHERE trip_id = :trip_id
                ORDER BY timestamp DESC
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        return [
            TimelineEvent(
                id=e.id,
                kind=e.kind,
                at=e.at.isoformat() if e.at else "",
                lat=e.lat,
                lon=e.lon,
                extended_by=e.extended_by
            )
            for e in events
        ]


@router.post("/debug/check-overdue")
async def debug_check_overdue(user_id: int = Depends(auth.get_current_user_id)):
    """Debug endpoint to manually trigger overdue check.

    This is useful for testing the overdue notification system without waiting
    for the scheduler to run.
    """
    from src.services.scheduler import check_overdue_trips

    log.info(f"[Debug] User {user_id} manually triggered overdue check")
    await check_overdue_trips()

    return {"ok": True, "message": "Overdue check completed - see server logs for details"}
