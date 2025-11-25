"""Trip management endpoints"""
import asyncio
from datetime import datetime, timezone
import secrets
from typing import Optional, List, Union
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel
from src import database as db
from src.api import auth
from src.api.activities import Activity
from src.services.notifications import send_trip_created_emails
import sqlalchemy
import json
import logging

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/trips",
    tags=["trips"],
    dependencies=[Depends(auth.get_current_user_id)]
)


def to_iso8601(dt: Union[datetime, str, None]) -> Optional[str]:
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
    location_text: Optional[str] = None
    gen_lat: Optional[float] = None
    gen_lon: Optional[float] = None
    notes: Optional[str] = None
    contact1: Optional[int] = None  # Contact ID reference
    contact2: Optional[int] = None
    contact3: Optional[int] = None


class TripResponse(BaseModel):
    id: int
    user_id: int
    title: str
    activity: Activity  # Full activity object with safety tips, colors, messages
    start: str
    eta: str
    grace_min: int
    location_text: Optional[str]
    gen_lat: Optional[float]
    gen_lon: Optional[float]
    notes: Optional[str]
    status: str
    completed_at: Optional[str]
    last_checkin: Optional[str]
    created_at: str
    contact1: Optional[int]
    contact2: Optional[int]
    contact3: Optional[int]
    checkin_token: Optional[str]
    checkout_token: Optional[str]


class TimelineEvent(BaseModel):
    id: int
    what: str
    timestamp: str
    lat: Optional[float]
    lon: Optional[float]
    extended_by: Optional[int]


@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    body: TripCreate,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Create a new trip"""
    # Log incoming request for debugging
    log.info(f"[Trips] Creating trip for user_id={user_id}")
    log.info(f"[Trips] Request body: title={body.title}, activity={body.activity}, start={body.start}, eta={body.eta}")
    log.info(f"[Trips] Contacts: contact1={body.contact1}, contact2={body.contact2}, contact3={body.contact3}")
    log.info(f"[Trips] Location: {body.location_text}, coords=({body.gen_lat}, {body.gen_lon})")

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
        log.info(f"[Trips] Looking up activity: '{body.activity}' (normalized: '{normalized_activity}')")

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
            log.info(f"[Trips] Available activities: {[a.name for a in all_activities]}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Activity '{body.activity}' not found. Available: {[a.name for a in all_activities]}"
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
                        sqlalchemy.text("SELECT id, name FROM contacts WHERE user_id = :user_id"),
                        {"user_id": user_id}
                    ).fetchall()
                    log.warning(f"[Trips] Contact {contact_id} not found for user {user_id}!")
                    log.info(f"[Trips] User's contacts: {[(c.id, c.name) for c in user_contacts]}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Contact {contact_id} not found. Available: {[c.id for c in user_contacts]}"
                    )

                log.info(f"[Trips] Contact {contact_id} verified")

        # Generate unique tokens for checkin/checkout
        checkin_token = secrets.token_urlsafe(32)
        checkout_token = secrets.token_urlsafe(32)

        # Determine initial status based on start time
        current_time = datetime.now(timezone.utc)
        # Ensure start time is timezone-aware for comparison
        start_time = body.start if body.start.tzinfo else body.start.replace(tzinfo=timezone.utc)
        initial_status = 'planned' if start_time > current_time else 'active'

        # Insert trip
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, notes, status,
                    contact1, contact2, contact3, created_at,
                    checkin_token, checkout_token
                ) VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, :notes, :status,
                    :contact1, :contact2, :contact3, :created_at,
                    :checkin_token, :checkout_token
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
                "location_text": body.location_text or "Unknown Location",  # Default if not provided
                "gen_lat": body.gen_lat if body.gen_lat is not None else 0.0,  # Default to 0.0
                "gen_lon": body.gen_lon if body.gen_lon is not None else 0.0,  # Default to 0.0
                "notes": body.notes,
                "status": initial_status,
                "contact1": body.contact1,
                "contact2": body.contact2,
                "contact3": body.contact3,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token
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
            colors=trip["activity_colors"] if isinstance(trip["activity_colors"], dict) else json.loads(trip["activity_colors"]),
            messages=trip["activity_messages"] if isinstance(trip["activity_messages"], dict) else json.loads(trip["activity_messages"]),
            safety_tips=trip["safety_tips"] if isinstance(trip["safety_tips"], list) else json.loads(trip["safety_tips"]),
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
        contact_ids = [cid for cid in [body.contact1, body.contact2, body.contact3] if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            contacts_result = connection.execute(
                sqlalchemy.text(f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"),
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

        # Schedule background task to send emails to contacts
        def send_emails_sync():
            asyncio.run(send_trip_created_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_obj.name
            ))

        background_tasks.add_task(send_emails_sync)
        log.info(f"[Trips] Scheduled email notifications for {len(contacts_for_email)} contacts")

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


@router.get("/", response_model=List[TripResponse])
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
                colors=trip["activity_colors"] if isinstance(trip["activity_colors"], dict) else json.loads(trip["activity_colors"]),
                messages=trip["activity_messages"] if isinstance(trip["activity_messages"], dict) else json.loads(trip["activity_messages"]),
                safety_tips=trip["safety_tips"] if isinstance(trip["safety_tips"], list) else json.loads(trip["safety_tips"]),
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
    """Get the current active trip with full activity data including safety tips"""
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
                WHERE t.user_id = :user_id AND t.status = 'active'
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
            colors=trip["activity_colors"] if isinstance(trip["activity_colors"], dict) else json.loads(trip["activity_colors"]),
            messages=trip["activity_messages"] if isinstance(trip["activity_messages"], dict) else json.loads(trip["activity_messages"]),
            safety_tips=trip["safety_tips"] if isinstance(trip["safety_tips"], list) else json.loads(trip["safety_tips"]),
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
            colors=trip["activity_colors"] if isinstance(trip["activity_colors"], dict) else json.loads(trip["activity_colors"]),
            messages=trip["activity_messages"] if isinstance(trip["activity_messages"], dict) else json.loads(trip["activity_messages"]),
            safety_tips=trip["safety_tips"] if isinstance(trip["safety_tips"], list) else json.loads(trip["safety_tips"]),
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

        if trip.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not active"
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
            {"trip_id": trip_id, "completed_at": datetime.now(timezone.utc).isoformat()}
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
def extend_trip(trip_id: int, minutes: int, user_id: int = Depends(auth.get_current_user_id)):
    """Extend the ETA of an active trip by the specified number of minutes"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, eta
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

        if trip.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only extend active trips"
            )

        # Parse current ETA and add minutes
        from datetime import timedelta
        # trip.eta is already a datetime object from the database
        current_eta = trip.eta if isinstance(trip.eta, datetime) else datetime.fromisoformat(trip.eta)
        new_eta = current_eta + timedelta(minutes=minutes)

        # Update trip ETA
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET eta = :new_eta
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id, "new_eta": new_eta.isoformat()}
        )

        # Log timeline event
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "extended_by": minutes
            }
        )

        return {"ok": True, "message": f"Trip extended by {minutes} minutes", "new_eta": new_eta.isoformat()}


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

        # Delete trip (events will cascade)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )

        return {"ok": True, "message": "Trip deleted successfully"}


@router.get("/{trip_id}/timeline", response_model=List[TimelineEvent])
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
