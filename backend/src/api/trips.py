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
    return str(dt)


class TripCreate(BaseModel):
    title: str
    activity: str  # Activity name reference
    start: datetime
    eta: datetime
    grace_min: int
    location_text: str | None = None
    gen_lat: float | None = None
    gen_lon: float | None = None
    notes: str | None = None
    contact1: int | None = None  # Contact ID reference
    contact2: int | None = None
    contact3: int | None = None
    timezone: str | None = None  # User's timezone (e.g., "America/New_York")


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


class TimelineEvent(BaseModel):
    id: int
    what: str
    timestamp: str
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
                geocoded = reverse_geocode_sync(body.gen_lat, body.gen_lon)
                if geocoded:
                    location_text = geocoded
                    log.info(f"[Trips] Geocoded to: {location_text}")
                else:
                    log.warning("[Trips] Geocoding failed, keeping 'Current Location'")
            else:
                log.warning(f"[Trips] No valid coords: ({body.gen_lat}, {body.gen_lon})")

        # Insert trip
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, notes, status,
                    contact1, contact2, contact3, created_at,
                    checkin_token, checkout_token, timezone
                ) VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, :notes, :status,
                    :contact1, :contact2, :contact3, :created_at,
                    :checkin_token, :checkout_token, :timezone
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
                "notes": body.notes,
                "status": initial_status,
                "contact1": body.contact1,
                "contact2": body.contact2,
                "contact3": body.contact3,
                "created_at": datetime.now(UTC).isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token,
                "timezone": body.timezone
            }
        )
        trip_id = result.fetchone()[0]

        # Fetch created trip with full activity data
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
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

        # Capture timezone and status for closure
        user_timezone = body.timezone
        is_starting_now = initial_status == 'active'

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
                    user_timezone=user_timezone
                ))
            else:
                # Trip is scheduled for later - send "upcoming trip" email
                asyncio.run(send_trip_created_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_obj.name,
                    user_timezone=user_timezone
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
            start=to_iso8601(trip["start"]),
            eta=to_iso8601(trip["eta"]),
            grace_min=trip["grace_min"],
            location_text=trip["location_text"],
            gen_lat=trip["gen_lat"],
            gen_lon=trip["gen_lon"],
            notes=trip["notes"],
            status=trip["status"],
            completed_at=to_iso8601(trip["completed_at"]),
            last_checkin=to_iso8601(trip["last_checkin"]),
            created_at=to_iso8601(trip["created_at"]),
            contact1=trip["contact1"],
            contact2=trip["contact2"],
            contact3=trip["contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"]
        )


@router.get("/", response_model=list[TripResponse])
def get_trips(user_id: int = Depends(auth.get_current_user_id)):
    """Get all trips for the current user with full activity data"""
    with db.engine.begin() as connection:
        trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
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
                    start=to_iso8601(trip["start"]),
                    eta=to_iso8601(trip["eta"]),
                    grace_min=trip["grace_min"],
                    location_text=trip["location_text"],
                    gen_lat=trip["gen_lat"],
                    gen_lon=trip["gen_lon"],
                    notes=trip["notes"],
                    status=trip["status"],
                    completed_at=to_iso8601(trip["completed_at"]),
                    last_checkin=to_iso8601(trip["last_checkin"]),
                    created_at=to_iso8601(trip["created_at"]),
                    contact1=trip["contact1"],
                    contact2=trip["contact2"],
                    contact3=trip["contact3"],
                    checkin_token=trip["checkin_token"],
                    checkout_token=trip["checkout_token"]
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
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
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
            start=to_iso8601(trip["start"]),
            eta=to_iso8601(trip["eta"]),
            grace_min=trip["grace_min"],
            location_text=trip["location_text"],
            gen_lat=trip["gen_lat"],
            gen_lon=trip["gen_lon"],
            notes=trip["notes"],
            status=trip["status"],
            completed_at=to_iso8601(trip["completed_at"]),
            last_checkin=to_iso8601(trip["last_checkin"]),
            created_at=to_iso8601(trip["created_at"]),
            contact1=trip["contact1"],
            contact2=trip["contact2"],
            contact3=trip["contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"]
        )


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific trip with full activity data"""
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token,
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
            start=to_iso8601(trip["start"]),
            eta=to_iso8601(trip["eta"]),
            grace_min=trip["grace_min"],
            location_text=trip["location_text"],
            gen_lat=trip["gen_lat"],
            gen_lon=trip["gen_lon"],
            notes=trip["notes"],
            status=trip["status"],
            completed_at=to_iso8601(trip["completed_at"]),
            last_checkin=to_iso8601(trip["last_checkin"]),
            created_at=to_iso8601(trip["created_at"]),
            contact1=trip["contact1"],
            contact2=trip["contact2"],
            contact3=trip["contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"]
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
        checkin_event_id = result.fetchone()[0]

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

        # Delete events first (foreign key constraint)
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
                SELECT id, what, timestamp, lat, lon, extended_by
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
                what=e.what,
                timestamp=str(e.timestamp),
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
