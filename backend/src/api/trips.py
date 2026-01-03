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
    send_friend_trip_completed_push,
    send_friend_trip_created_push,
    send_friend_trip_extended_push,
    send_friend_trip_starting_push,
    send_trip_completed_emails,
    send_trip_created_emails,
    send_trip_extended_emails,
    send_trip_starting_now_emails,
)

log = logging.getLogger(__name__)


def _is_friend(connection, user_id: int, friend_user_id: int) -> bool:
    """Check if two users are friends."""
    id1, id2 = min(user_id, friend_user_id), max(user_id, friend_user_id)
    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT id FROM friendships
            WHERE user_id_1 = :id1 AND user_id_2 = :id2
            """
        ),
        {"id1": id1, "id2": id2}
    ).fetchone()
    return result is not None


def _save_trip_safety_contacts(
    connection,
    trip_id: int,
    contact_ids: list[int | None],
    friend_user_ids: list[int | None]
) -> None:
    """Save trip safety contacts to the junction table.

    This stores both email contacts and friend contacts in trip_safety_contacts.
    """
    log.info(f"[Trips] _save_trip_safety_contacts called: trip_id={trip_id}, contact_ids={contact_ids}, friend_user_ids={friend_user_ids}")

    # Clear existing entries for this trip
    connection.execute(
        sqlalchemy.text("DELETE FROM trip_safety_contacts WHERE trip_id = :trip_id"),
        {"trip_id": trip_id}
    )

    position = 1

    # Add email contacts (contact1, contact2, contact3)
    for contact_id in contact_ids:
        if contact_id is not None:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_safety_contacts (trip_id, contact_id, position)
                    VALUES (:trip_id, :contact_id, :position)
                    """
                ),
                {"trip_id": trip_id, "contact_id": contact_id, "position": position}
            )
            position += 1

    # Add friend contacts (friend_contact1, friend_contact2, friend_contact3)
    for friend_user_id in friend_user_ids:
        if friend_user_id is not None:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_safety_contacts (trip_id, friend_user_id, position)
                    VALUES (:trip_id, :friend_user_id, :position)
                    """
                ),
                {"trip_id": trip_id, "friend_user_id": friend_user_id, "position": position}
            )
            position += 1


def _get_friend_contacts_for_trip(connection, trip_id: int) -> dict[str, int | None]:
    """Get friend contacts from the junction table for a trip.

    Returns a dict with friend_contact1, friend_contact2, friend_contact3.
    """
    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT friend_user_id, position
            FROM trip_safety_contacts
            WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
            ORDER BY position
            """
        ),
        {"trip_id": trip_id}
    ).fetchall()

    # Map positions to friend_contact fields
    friend_contacts: dict[str, int | None] = {
        "friend_contact1": None,
        "friend_contact2": None,
        "friend_contact3": None
    }

    for i, row in enumerate(result):
        if i == 0:
            friend_contacts["friend_contact1"] = row.friend_user_id
        elif i == 1:
            friend_contacts["friend_contact2"] = row.friend_user_id
        elif i == 2:
            friend_contacts["friend_contact3"] = row.friend_user_id

    return friend_contacts


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


class GroupSettings(BaseModel):
    """Settings for group trip behavior, configurable by trip owner."""
    checkout_mode: str = "anyone"  # "anyone" | "vote" | "owner_only"
    vote_threshold: float = 0.5  # For vote mode: percentage needed (0.0-1.0)
    allow_participant_invites: bool = False  # Can participants invite others?
    share_locations_between_participants: bool = True  # Can participants see each other's locations?


def parse_group_settings(settings_json) -> GroupSettings | None:
    """Parse group settings from JSON.

    Args:
        settings_json: Either None, a dict, or a JSON string

    Returns:
        GroupSettings object with parsed settings, or None if input was None
    """
    if settings_json is None:
        return None
    try:
        if isinstance(settings_json, dict):
            return GroupSettings(**settings_json)
        return GroupSettings(**json.loads(settings_json))
    except Exception as e:
        log.warning(f"Failed to parse group_settings: {e}")
        return None


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
    contact1: int | None = None  # Contact ID reference (email contact)
    contact2: int | None = None
    contact3: int | None = None
    friend_contact1: int | None = None  # Friend user ID reference (gets push notifications)
    friend_contact2: int | None = None
    friend_contact3: int | None = None
    timezone: str | None = None  # User's timezone (e.g., "America/New_York") - used for notifications
    start_timezone: str | None = None  # Timezone for start time (e.g., "America/Los_Angeles")
    eta_timezone: str | None = None  # Timezone for return time (e.g., "America/New_York")
    checkin_interval_min: int = 30  # Minutes between check-in reminders
    notify_start_hour: int | None = None  # Hour (0-23) when notifications start
    notify_end_hour: int | None = None  # Hour (0-23) when notifications end
    notify_self: bool = False  # Send copy of all emails to trip owner
    share_live_location: bool = False  # Share live location with friends during trip
    # Group trip fields
    is_group_trip: bool = False  # Is this a group trip?
    group_settings: GroupSettings | None = None  # Settings for group trip behavior
    participant_ids: list[int] | None = None  # Friend user IDs to invite as participants


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
    contact1: int | None = None  # Contact ID reference (email contact)
    contact2: int | None = None
    contact3: int | None = None
    friend_contact1: int | None = None  # Friend user ID reference (gets push notifications)
    friend_contact2: int | None = None
    friend_contact3: int | None = None
    timezone: str | None = None
    start_timezone: str | None = None
    eta_timezone: str | None = None
    checkin_interval_min: int | None = None
    notify_start_hour: int | None = None
    notify_end_hour: int | None = None
    notify_self: bool | None = None  # Send copy of all emails to trip owner
    share_live_location: bool | None = None  # Share live location with friends during trip


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
    contact1: int | None  # Email contact ID
    contact2: int | None
    contact3: int | None
    friend_contact1: int | None = None  # Friend user ID
    friend_contact2: int | None = None
    friend_contact3: int | None = None
    checkin_token: str | None
    checkout_token: str | None
    checkin_interval_min: int | None
    notify_start_hour: int | None
    notify_end_hour: int | None
    timezone: str | None
    start_timezone: str | None
    eta_timezone: str | None
    notify_self: bool
    share_live_location: bool
    # Group trip fields
    is_group_trip: bool = False
    group_settings: GroupSettings | None = None
    participant_count: int = 0  # Number of accepted participants


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
    log.info(f"[Trips] Friend contacts: {body.friend_contact1}, {body.friend_contact2}, {body.friend_contact3}")
    log.info(f"[Trips] Location: {body.location_text}, ({body.gen_lat}, {body.gen_lon})")

    # Validate that at least one safety contact is provided (email contact OR friend)
    has_any_contact = (
        body.contact1 is not None or
        body.friend_contact1 is not None
    )
    if not has_any_contact:
        log.warning("[Trips] No safety contact provided")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one emergency contact (contact1 or friend_contact1) is required"
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

        # Verify friend contacts are actually friends with the user
        log.info("[Trips] Verifying friend contacts...")
        for friend_id in [body.friend_contact1, body.friend_contact2, body.friend_contact3]:
            if friend_id is not None:
                log.info(f"[Trips] Checking friend_id={friend_id}")
                if not _is_friend(connection, user_id, friend_id):
                    log.warning(f"[Trips] User {friend_id} is not a friend!")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User {friend_id} is not in your friends list"
                    )
                log.info(f"[Trips] Friend {friend_id} verified")

        # Validate that coordinates are provided (iOS should always send these)
        if body.gen_lat is None or body.gen_lon is None:
            log.warning(f"[Trips] Missing destination coordinates: lat={body.gen_lat}, lon={body.gen_lon}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location coordinates are required"
            )

        # Validate start location coordinates if separate locations enabled
        if body.has_separate_locations and (body.start_lat is None or body.start_lon is None):
            log.warning(f"[Trips] Missing start coordinates: lat={body.start_lat}, lon={body.start_lon}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start location coordinates are required when using separate locations"
            )

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

        # Prepare group settings JSON if group trip
        group_settings_json = None
        if body.is_group_trip and body.group_settings:
            group_settings_json = json.dumps(body.group_settings.model_dump())
        elif body.is_group_trip:
            # Use default group settings
            group_settings_json = json.dumps(GroupSettings().model_dump())

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
                    checkin_interval_min, notify_start_hour, notify_end_hour, notify_self,
                    share_live_location, is_group_trip, group_settings
                ) VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon,
                    :start_location_text, :start_lat, :start_lon, :has_separate_locations,
                    :notes, :status,
                    :contact1, :contact2, :contact3, :created_at,
                    :checkin_token, :checkout_token, :timezone, :start_timezone, :eta_timezone,
                    :checkin_interval_min, :notify_start_hour, :notify_end_hour, :notify_self,
                    :share_live_location, :is_group_trip, :group_settings
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
                "gen_lat": body.gen_lat,  # Already validated as not None
                "gen_lon": body.gen_lon,  # Already validated as not None
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
                "notify_end_hour": body.notify_end_hour,
                "notify_self": body.notify_self,
                "share_live_location": body.share_live_location,
                "is_group_trip": body.is_group_trip,
                "group_settings": group_settings_json
            }
        )
        row = result.fetchone()
        assert row is not None
        trip_id = row[0]

        # If group trip, add owner and invited participants
        participant_count = 0
        if body.is_group_trip:
            now = datetime.now(UTC).isoformat()

            # Add owner as participant
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id, "now": now}
            )
            participant_count = 1

            # Add invited participants
            if body.participant_ids:
                for participant_id in body.participant_ids:
                    # Verify they're friends
                    if _is_friend(connection, user_id, participant_id):
                        connection.execute(
                            sqlalchemy.text(
                                """
                                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                                VALUES (:trip_id, :participant_id, 'participant', 'invited', :now, :user_id)
                                """
                            ),
                            {"trip_id": trip_id, "participant_id": participant_id, "now": now, "user_id": user_id}
                        )
                    else:
                        log.warning(f"[Trips] User {participant_id} is not a friend, skipping invitation")

        # Save to trip_safety_contacts junction table (supports both email contacts and friends)
        _save_trip_safety_contacts(
            connection,
            trip_id,
            contact_ids=[body.contact1, body.contact2, body.contact3],
            friend_user_ids=[body.friend_contact1, body.friend_contact2, body.friend_contact3]
        )

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
                       t.timezone, t.start_timezone, t.eta_timezone, t.notify_self, t.share_live_location,
                       t.is_group_trip, t.group_settings,
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

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"
        user_email = user.email if user else None
        # Only include owner email if notify_self is enabled
        owner_email = user_email if body.notify_self else None

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
                    start_location=trip_start_location,
                    owner_email=owner_email
                ))
            else:
                # Trip is scheduled for later - send "upcoming trip" email
                asyncio.run(send_trip_created_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_obj.name,
                    user_timezone=user_timezone,
                    start_location=trip_start_location,
                    owner_email=owner_email
                ))

        background_tasks.add_task(send_emails_sync)
        email_type = "starting now" if is_starting_now else "upcoming trip"
        num_contacts = len(contacts_for_email)
        log.info(f"[Trips] Scheduled {email_type} emails for {num_contacts} contacts")

        # Get friend contacts from junction table
        friend_contacts = _get_friend_contacts_for_trip(connection, trip_id)
        log.info(f"[Trips] create_trip: Retrieved friend contacts for trip {trip_id}: {friend_contacts}")

        # Send push notifications to friend safety contacts
        friend_user_ids = [
            friend_contacts["friend_contact1"],
            friend_contacts["friend_contact2"],
            friend_contacts["friend_contact3"]
        ]
        friend_user_ids = [f for f in friend_user_ids if f is not None]
        log.info(f"[Trips] create_trip: Friend user IDs to notify: {friend_user_ids}")

        if friend_user_ids:
            trip_title_for_push = trip["title"]
            def send_friend_push_sync():
                for friend_id in friend_user_ids:
                    log.info(f"[Trips] Sending {email_type} push to friend {friend_id}")
                    if is_starting_now:
                        asyncio.run(send_friend_trip_starting_push(
                            friend_user_id=friend_id,
                            user_name=user_name,
                            trip_title=trip_title_for_push
                        ))
                    else:
                        asyncio.run(send_friend_trip_created_push(
                            friend_user_id=friend_id,
                            user_name=user_name,
                            trip_title=trip_title_for_push
                        ))

            background_tasks.add_task(send_friend_push_sync)
            log.info(f"[Trips] Scheduled {email_type} push notifications for {len(friend_user_ids)} friend contacts")
        else:
            log.info(f"[Trips] create_trip: No friend contacts to notify for trip {trip_id}")

        # Parse group settings if present
        trip_group_settings = None
        if trip.get("group_settings"):
            gs = trip["group_settings"]
            if isinstance(gs, dict):
                trip_group_settings = GroupSettings(**gs)
            elif isinstance(gs, str):
                trip_group_settings = GroupSettings(**json.loads(gs))

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
            friend_contact1=friend_contacts["friend_contact1"],
            friend_contact2=friend_contacts["friend_contact2"],
            friend_contact3=friend_contacts["friend_contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"],
            checkin_interval_min=trip["checkin_interval_min"],
            notify_start_hour=trip["notify_start_hour"],
            notify_end_hour=trip["notify_end_hour"],
            timezone=trip["timezone"],
            start_timezone=trip["start_timezone"],
            eta_timezone=trip["eta_timezone"],
            notify_self=trip["notify_self"],
            share_live_location=trip.get("share_live_location", False),
            is_group_trip=trip.get("is_group_trip", False),
            group_settings=trip_group_settings,
            participant_count=participant_count
        )


@router.get("/", response_model=list[TripResponse])
def get_trips(user_id: int = Depends(auth.get_current_user_id)):
    """Get all trips for the current user with full activity data.

    Returns trips where user is either:
    - The owner (t.user_id = user_id)
    - An accepted participant (trip_participants.user_id = user_id AND status = 'accepted')
    """
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
                       t.timezone, t.start_timezone, t.eta_timezone, t.notify_self, t.share_live_location,
                       t.is_group_trip, t.group_settings,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order,
                       (SELECT COUNT(*) FROM trip_participants WHERE trip_id = t.id AND status = 'accepted') as participant_count
                FROM trips t
                JOIN activities a ON t.activity = a.id
                LEFT JOIN trip_participants tp ON t.id = tp.trip_id AND tp.user_id = :user_id AND tp.status = 'accepted'
                WHERE t.user_id = :user_id OR tp.user_id IS NOT NULL
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

            # Get friend contacts from junction table
            friend_contacts = _get_friend_contacts_for_trip(connection, trip["id"])

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
                    friend_contact1=friend_contacts["friend_contact1"],
                    friend_contact2=friend_contacts["friend_contact2"],
                    friend_contact3=friend_contacts["friend_contact3"],
                    checkin_token=trip["checkin_token"],
                    checkout_token=trip["checkout_token"],
                    checkin_interval_min=trip["checkin_interval_min"],
                    notify_start_hour=trip["notify_start_hour"],
                    notify_end_hour=trip["notify_end_hour"],
                    timezone=trip["timezone"],
                    start_timezone=trip["start_timezone"],
                    eta_timezone=trip["eta_timezone"],
                    notify_self=trip["notify_self"],
                    share_live_location=trip.get("share_live_location", False),
                    is_group_trip=trip.get("is_group_trip", False),
                    group_settings=parse_group_settings(trip.get("group_settings")),
                    participant_count=trip.get("participant_count", 0)
                )
            )

        return result


@router.get("/active", response_model=Optional[TripResponse])
def get_active_trip(user_id: int = Depends(auth.get_current_user_id)):
    """Get the current active trip with full activity data including safety tips.

    Returns trips that are active, overdue, or overdue_notified - all require user action.
    Includes trips where user is owner OR an accepted participant.
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
                       t.timezone, t.start_timezone, t.eta_timezone, t.notify_self, t.share_live_location,
                       t.is_group_trip, t.group_settings,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order,
                       (SELECT COUNT(*) FROM trip_participants WHERE trip_id = t.id AND status = 'accepted') as participant_count
                FROM trips t
                JOIN activities a ON t.activity = a.id
                LEFT JOIN trip_participants tp ON t.id = tp.trip_id AND tp.user_id = :user_id AND tp.status = 'accepted'
                WHERE (t.user_id = :user_id OR tp.user_id IS NOT NULL)
                  AND t.status IN ('active', 'overdue', 'overdue_notified')
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

        # Get friend contacts from junction table
        friend_contacts = _get_friend_contacts_for_trip(connection, trip["id"])

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
            friend_contact1=friend_contacts["friend_contact1"],
            friend_contact2=friend_contacts["friend_contact2"],
            friend_contact3=friend_contacts["friend_contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"],
            checkin_interval_min=trip["checkin_interval_min"],
            notify_start_hour=trip["notify_start_hour"],
            notify_end_hour=trip["notify_end_hour"],
            timezone=trip["timezone"],
            start_timezone=trip["start_timezone"],
            eta_timezone=trip["eta_timezone"],
            notify_self=trip["notify_self"],
            share_live_location=trip.get("share_live_location", False),
            is_group_trip=trip.get("is_group_trip", False),
            group_settings=parse_group_settings(trip.get("group_settings")),
            participant_count=trip.get("participant_count", 0)
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
                       t.timezone, t.start_timezone, t.eta_timezone, t.notify_self, t.share_live_location,
                       t.is_group_trip, t.group_settings,
                       a.id as activity_id, a.name as activity_name, a.icon as activity_icon,
                       a.default_grace_minutes, a.colors as activity_colors,
                       a.messages as activity_messages, a.safety_tips, a."order" as activity_order,
                       (SELECT COUNT(*) FROM trip_participants WHERE trip_id = t.id AND status = 'accepted') as participant_count
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

        # Get friend contacts from junction table
        friend_contacts = _get_friend_contacts_for_trip(connection, trip["id"])

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
            friend_contact1=friend_contacts["friend_contact1"],
            friend_contact2=friend_contacts["friend_contact2"],
            friend_contact3=friend_contacts["friend_contact3"],
            checkin_token=trip["checkin_token"],
            checkout_token=trip["checkout_token"],
            checkin_interval_min=trip["checkin_interval_min"],
            notify_start_hour=trip["notify_start_hour"],
            notify_end_hour=trip["notify_end_hour"],
            timezone=trip["timezone"],
            start_timezone=trip["start_timezone"],
            eta_timezone=trip["eta_timezone"],
            notify_self=trip["notify_self"],
            share_live_location=trip.get("share_live_location", False),
            is_group_trip=trip.get("is_group_trip", False),
            group_settings=parse_group_settings(trip.get("group_settings")),
            participant_count=trip.get("participant_count", 0)
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

        # Handle friend contact validation if any friend contacts are being updated
        for friend_field in ["friend_contact1", "friend_contact2", "friend_contact3"]:
            friend_id = getattr(body, friend_field)
            if friend_id is not None:
                if not _is_friend(connection, user_id, friend_id):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User {friend_id} is not in your friends list"
                    )

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
            "notify_self": body.notify_self,
            "share_live_location": body.share_live_location,
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

        # Update trip_safety_contacts junction table if contacts changed
        any_contact_changed = any([
            body.contact1 is not None,
            body.contact2 is not None,
            body.contact3 is not None,
            body.friend_contact1 is not None,
            body.friend_contact2 is not None,
            body.friend_contact3 is not None,
        ])
        if any_contact_changed:
            # Get current contact values from DB (for unchanged fields)
            current = connection.execute(
                sqlalchemy.text("SELECT contact1, contact2, contact3 FROM trips WHERE id = :trip_id"),
                {"trip_id": trip_id}
            ).fetchone()

            # Use new value if provided, else keep current
            contact1 = body.contact1 if body.contact1 is not None else current.contact1
            contact2 = body.contact2 if body.contact2 is not None else current.contact2
            contact3 = body.contact3 if body.contact3 is not None else current.contact3

            # Get current friend contacts from junction table
            current_friends = _get_friend_contacts_for_trip(connection, trip_id)
            friend1 = body.friend_contact1 if body.friend_contact1 is not None else current_friends["friend_contact1"]
            friend2 = body.friend_contact2 if body.friend_contact2 is not None else current_friends["friend_contact2"]
            friend3 = body.friend_contact3 if body.friend_contact3 is not None else current_friends["friend_contact3"]

            # Save updated contacts to junction table
            _save_trip_safety_contacts(
                connection,
                trip_id,
                contact_ids=[contact1, contact2, contact3],
                friend_user_ids=[friend1, friend2, friend3]
            )

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
                       t.timezone, t.start_timezone, t.eta_timezone, t.notify_self, t.share_live_location,
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

        # Get friend contacts from junction table
        friend_contacts = _get_friend_contacts_for_trip(connection, trip_id)

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
            friend_contact1=friend_contacts["friend_contact1"],
            friend_contact2=friend_contacts["friend_contact2"],
            friend_contact3=friend_contacts["friend_contact3"],
            checkin_token=updated_trip["checkin_token"],
            checkout_token=updated_trip["checkout_token"],
            checkin_interval_min=updated_trip["checkin_interval_min"],
            notify_start_hour=updated_trip["notify_start_hour"],
            notify_end_hour=updated_trip["notify_end_hour"],
            timezone=updated_trip["timezone"],
            start_timezone=updated_trip["start_timezone"],
            eta_timezone=updated_trip["eta_timezone"],
            notify_self=updated_trip["notify_self"],
            share_live_location=updated_trip.get("share_live_location", False)
        )


@router.post("/{trip_id}/complete")
def complete_trip(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Mark a trip as completed"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status, fetch details needed for email
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.status, t.title, t.location_text,
                       t.contact1, t.contact2, t.contact3, t.timezone, t.notify_self,
                       a.name as activity_name
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

        # Allow completing active, overdue, or overdue_notified trips
        if trip.status not in ("active", "overdue", "overdue_notified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not active or overdue"
            )

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "User"
        owner_email = user.email if user and trip.notify_self else None

        # Fetch contact emails
        contact_ids = [trip.contact1, trip.contact2, trip.contact3]
        contact_ids = [c for c in contact_ids if c is not None]
        contacts_for_email = []
        if contact_ids:
            contacts = connection.execute(
                sqlalchemy.text(
                    "SELECT id, name, email FROM contacts WHERE id = ANY(:ids)"
                ),
                {"ids": contact_ids}
            ).fetchall()
            contacts_for_email = [{"email": c.email, "name": c.name} for c in contacts]

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

        # Prepare data for email
        trip_data = {
            "title": trip.title,
            "location_text": trip.location_text
        }
        user_timezone = trip.timezone
        activity_name = trip.activity_name

        # Schedule background task to send emails to contacts
        def send_emails_sync():
            asyncio.run(send_trip_completed_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name,
                user_timezone=user_timezone,
                owner_email=owner_email
            ))

        if contacts_for_email or owner_email:
            background_tasks.add_task(send_emails_sync)

        # Send push notifications to friend safety contacts
        friend_contacts = _get_friend_contacts_for_trip(connection, trip_id)
        friend_user_ids = [
            friend_contacts["friend_contact1"],
            friend_contacts["friend_contact2"],
            friend_contacts["friend_contact3"]
        ]
        friend_user_ids = [f for f in friend_user_ids if f is not None]

        if friend_user_ids:
            trip_title_for_push = trip.title
            user_name_for_push = user_name
            def send_friend_completed_push_sync():
                for friend_id in friend_user_ids:
                    asyncio.run(send_friend_trip_completed_push(
                        friend_user_id=friend_id,
                        user_name=user_name_for_push,
                        trip_title=trip_title_for_push
                    ))

            background_tasks.add_task(send_friend_completed_push_sync)
            log.info(f"[Trips] Scheduled completed push notifications for {len(friend_user_ids)} friend contacts")

        return {"ok": True, "message": "Trip completed successfully"}


@router.post("/{trip_id}/start")
def start_trip(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Start a planned trip (change status from 'planned' to 'active')"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status, fetch details needed for email
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.status, t.start, t.title, t.eta, t.location_text,
                       t.start_location_text, t.has_separate_locations,
                       t.contact1, t.contact2, t.contact3, t.timezone,
                       a.name as activity_name
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

        if trip.status != "planned":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not in planned status"
            )

        # Fetch user name for email
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "User"

        # Fetch contact emails
        contact_ids = [trip.contact1, trip.contact2, trip.contact3]
        contact_ids = [c for c in contact_ids if c is not None]
        contacts_for_email = []
        if contact_ids:
            contacts = connection.execute(
                sqlalchemy.text(
                    "SELECT id, name, email FROM contacts WHERE id = ANY(:ids)"
                ),
                {"ids": contact_ids}
            ).fetchall()
            contacts_for_email = [{"email": c.email, "name": c.name} for c in contacts]

        # Update trip status to active and set start time to now (for early starts)
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET status = 'active',
                    start = now()
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        )

        # Prepare data for email
        trip_data = {
            "title": trip.title,
            "eta": trip.eta,
            "location_text": trip.location_text
        }
        trip_start_location = trip.start_location_text if trip.has_separate_locations else None
        user_timezone = trip.timezone
        activity_name = trip.activity_name

        # Schedule background task to send emails to contacts
        def send_emails_sync():
            asyncio.run(send_trip_starting_now_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name,
                user_timezone=user_timezone,
                start_location=trip_start_location
            ))

        if contacts_for_email:
            background_tasks.add_task(send_emails_sync)

        # Send push notifications to friend safety contacts
        friend_contacts = _get_friend_contacts_for_trip(connection, trip_id)
        log.info(f"[Trips] start_trip: Retrieved friend contacts for trip {trip_id}: {friend_contacts}")
        friend_user_ids = [
            friend_contacts["friend_contact1"],
            friend_contacts["friend_contact2"],
            friend_contacts["friend_contact3"]
        ]
        friend_user_ids = [f for f in friend_user_ids if f is not None]
        log.info(f"[Trips] start_trip: Friend user IDs to notify: {friend_user_ids}")

        if friend_user_ids:
            trip_title_for_push = trip.title
            user_name_for_push = user_name
            def send_friend_starting_push_sync():
                for friend_id in friend_user_ids:
                    log.info(f"[Trips] Sending trip starting push to friend {friend_id}")
                    asyncio.run(send_friend_trip_starting_push(
                        friend_user_id=friend_id,
                        user_name=user_name_for_push,
                        trip_title=trip_title_for_push
                    ))

            background_tasks.add_task(send_friend_starting_push_sync)
            log.info(f"[Trips] Scheduled starting push notifications for {len(friend_user_ids)} friend contacts")
        else:
            log.info(f"[Trips] start_trip: No friend contacts to notify for trip {trip_id}")

        return {"ok": True, "message": "Trip started successfully"}


@router.post("/{trip_id}/extend")
def extend_trip(
    trip_id: int,
    minutes: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id),
    lat: float | None = None,
    lon: float | None = None
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
                       t.timezone, t.notify_self, a.name as activity_name
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

        now = datetime.now(UTC)
        # If currently past ETA (overdue), extend from now instead of original ETA
        if now > current_eta:
            new_eta = now + timedelta(minutes=minutes)
        else:
            new_eta = current_eta + timedelta(minutes=minutes)

        # Log checkin event first (extending is also a check-in) and get the event ID
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp, :lat, :lon)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": now.isoformat(),
                "lat": lat,
                "lon": lon
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

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"
        owner_email = user.email if user and trip.notify_self else None

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
                user_timezone=user_timezone,
                owner_email=owner_email
            ))

        if contacts_for_email or owner_email:
            background_tasks.add_task(send_emails_sync)
        num_contacts = len(contacts_for_email)
        log.info(f"[Trips] Scheduled extended trip emails for {num_contacts} contacts")

        # Send push notifications to friend safety contacts
        friend_contacts = _get_friend_contacts_for_trip(connection, trip_id)
        friend_user_ids = [
            friend_contacts["friend_contact1"],
            friend_contacts["friend_contact2"],
            friend_contacts["friend_contact3"]
        ]
        friend_user_ids = [f for f in friend_user_ids if f is not None]

        if friend_user_ids:
            trip_title_for_push = trip.title
            user_name_for_push = user_name
            extended_by_for_push = minutes

            def send_friend_extended_push_sync():
                for friend_id in friend_user_ids:
                    asyncio.run(send_friend_trip_extended_push(
                        friend_user_id=friend_id,
                        user_name=user_name_for_push,
                        trip_title=trip_title_for_push,
                        extended_by_minutes=extended_by_for_push
                    ))

            background_tasks.add_task(send_friend_extended_push_sync)
            log.info(f"[Trips] Scheduled extended push notifications for {len(friend_user_ids)} friend contacts")

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


# ==================== Live Location Sharing ====================

class LiveLocationUpdate(BaseModel):
    """Request body for updating live location during a trip."""
    latitude: float
    longitude: float
    altitude: float | None = None
    horizontal_accuracy: float | None = None
    speed: float | None = None


class LiveLocationResponse(BaseModel):
    ok: bool
    message: str


@router.post("/{trip_id}/live-location", response_model=LiveLocationResponse)
def update_live_location(
    trip_id: int,
    body: LiveLocationUpdate,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Update live location during an active trip.

    This endpoint is called periodically by the iOS app when live location
    sharing is enabled for a trip. Friends who are safety contacts can see
    the latest location on their map view.

    For group trips, accepted participants can also update their live location.

    Requirements:
    - Trip must belong to the user OR user must be an accepted participant
    - Trip must be active (active, overdue, or overdue_notified status)
    - Trip must have share_live_location enabled
    """
    with db.engine.begin() as connection:
        # Get trip details
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, share_live_location, status, is_group_trip
                FROM trips
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Check if user has access (owner or accepted participant)
        is_owner = trip.user_id == user_id
        is_accepted_participant = False

        if not is_owner and trip.is_group_trip:
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()
            is_accepted_participant = participant is not None

        if not is_owner and not is_accepted_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to update location for this trip"
            )

        # Check if trip is in an active state
        active_statuses = ('active', 'overdue', 'overdue_notified')
        if trip.status not in active_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Trip is not active (status: {trip.status})"
            )

        # Check if live location sharing is enabled for this trip
        if not trip.share_live_location:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Live location sharing is not enabled for this trip"
            )

        now = datetime.now(UTC)

        # Insert the new location
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO live_locations
                (trip_id, user_id, latitude, longitude, altitude, horizontal_accuracy, speed, timestamp)
                VALUES (:trip_id, :user_id, :lat, :lon, :alt, :acc, :speed, :ts)
                """
            ),
            {
                "trip_id": trip_id,
                "user_id": user_id,
                "lat": body.latitude,
                "lon": body.longitude,
                "alt": body.altitude,
                "acc": body.horizontal_accuracy,
                "speed": body.speed,
                "ts": now.isoformat()
            }
        )

        # Clean up old locations (keep last 100 per trip)
        connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM live_locations
                WHERE trip_id = :trip_id AND id NOT IN (
                    SELECT id FROM live_locations
                    WHERE trip_id = :trip_id
                    ORDER BY timestamp DESC
                    LIMIT 100
                )
                """
            ),
            {"trip_id": trip_id}
        )

        log.info(f"[LiveLocation] Updated location for trip {trip_id}: {body.latitude}, {body.longitude}")

        return LiveLocationResponse(ok=True, message="Location updated")


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
