"""Trip management endpoints"""
import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Optional

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src import database as db
from src.api import auth
from src.api.activities import Activity
from src.services.geocoding import reverse_geocode_sync
from src.services.notifications import (
    send_data_refresh_push,
    send_friend_trip_completed_push,
    send_friend_trip_created_push,
    send_friend_trip_extended_push,
    send_friend_trip_starting_push,
    send_trip_cancelled_push,
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

    log.info(f"[Trips] _get_friend_contacts_for_trip: trip_id={trip_id}, found {len(result)} friend contacts: {[(r.friend_user_id, r.position) for r in result]}")

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

    log.info(f"[Trips] _get_friend_contacts_for_trip: returning {friend_contacts}")
    return friend_contacts


def _get_friend_contacts_for_trips_batch(connection, trip_ids: list[int]) -> dict[int, dict[str, int | None]]:
    """Get friend contacts for multiple trips in a single query.

    Returns a dict mapping trip_id -> {friend_contact1, friend_contact2, friend_contact3}
    """
    if not trip_ids:
        return {}

    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT trip_id, friend_user_id, position
            FROM trip_safety_contacts
            WHERE trip_id = ANY(:trip_ids) AND friend_user_id IS NOT NULL
            ORDER BY trip_id, position
            """
        ),
        {"trip_ids": trip_ids}
    ).fetchall()

    # Initialize all trips with empty contacts
    contacts_map: dict[int, dict[str, int | None]] = {
        tid: {"friend_contact1": None, "friend_contact2": None, "friend_contact3": None}
        for tid in trip_ids
    }

    # Group results by trip_id first, then assign by order (not raw position)
    # Position values are continuous across email and friend contacts, so we use
    # enumeration within each trip's friend contacts to map to friend_contact1/2/3
    from itertools import groupby
    for tid, group in groupby(result, key=lambda r: r.trip_id):
        for i, row in enumerate(group):
            if i == 0:
                contacts_map[tid]["friend_contact1"] = row.friend_user_id
            elif i == 1:
                contacts_map[tid]["friend_contact2"] = row.friend_user_id
            elif i == 2:
                contacts_map[tid]["friend_contact3"] = row.friend_user_id

    return contacts_map


def _get_all_trip_email_contacts(connection, trip) -> list[dict]:
    """Get all email contacts for a trip (owner + participants for group trips).

    For group trips, this includes both the owner's contacts AND participant contacts
    from the participant_trip_contacts table, deduplicated by email.

    Each contact includes a 'watched_user_name' field indicating whose trip they are watching.
    This allows personalized notifications (e.g., "Update on John's trip").
    """
    # Get owner's name for watched_user_name
    owner_id = getattr(trip, 'user_id', None)
    owner_name = "Trip owner"
    if owner_id:
        owner = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :id"),
            {"id": owner_id}
        ).fetchone()
        if owner:
            owner_name = f"{owner.first_name} {owner.last_name}".strip() or "Trip owner"

    # Owner's contacts - they are watching the owner
    contact_ids = [trip.contact1, trip.contact2, trip.contact3]
    contact_ids = [c for c in contact_ids if c is not None]

    contacts = []
    if contact_ids:
        result = connection.execute(
            sqlalchemy.text("SELECT id, name, email FROM contacts WHERE id = ANY(:ids)"),
            {"ids": contact_ids}
        ).fetchall()
        contacts = [{"id": c.id, "name": c.name, "email": c.email, "watched_user_name": owner_name} for c in result]

    # For group trips, also get participant contacts
    # Note: Use direct attribute access instead of getattr() to avoid silent failures with SQLAlchemy Row objects
    is_group = trip.is_group_trip if hasattr(trip, 'is_group_trip') else False
    trip_id = trip.id if hasattr(trip, 'id') else None
    log.info(f"[Trips] _get_all_trip_email_contacts: is_group={is_group}, trip_id={trip_id}")

    if is_group and trip_id:
        log.info(f"[Trips] _get_all_trip_email_contacts: Group trip {trip_id}, fetching participant contacts")

        # Query 1: Email contacts (contact_id is set) - from contacts table
        email_contacts = connection.execute(
            sqlalchemy.text("""
                SELECT DISTINCT c.id, c.name, c.email,
                       COALESCE(TRIM(u.first_name || ' ' || u.last_name), 'Participant') as participant_name
                FROM participant_trip_contacts ptc
                JOIN contacts c ON ptc.contact_id = c.id
                JOIN users u ON ptc.participant_user_id = u.id
                WHERE ptc.trip_id = :trip_id
                  AND ptc.contact_id IS NOT NULL
                  AND c.email IS NOT NULL
            """),
            {"trip_id": trip_id}
        ).fetchall()

        # Query 2: Friend contacts (friend_user_id is set) - get email from users table
        friend_contacts = connection.execute(
            sqlalchemy.text("""
                SELECT DISTINCT
                       friend.id as id,
                       TRIM(friend.first_name || ' ' || friend.last_name) as name,
                       friend.email as email,
                       COALESCE(TRIM(participant.first_name || ' ' || participant.last_name), 'Participant') as participant_name
                FROM participant_trip_contacts ptc
                JOIN users friend ON ptc.friend_user_id = friend.id
                JOIN users participant ON ptc.participant_user_id = participant.id
                WHERE ptc.trip_id = :trip_id
                  AND ptc.friend_user_id IS NOT NULL
                  AND friend.email IS NOT NULL
            """),
            {"trip_id": trip_id}
        ).fetchall()

        log.info(f"[Trips] _get_all_trip_email_contacts: Found {len(email_contacts)} participant email contacts, {len(friend_contacts)} participant friend contacts")

        # No cross-user dedup - each notification is personalized with watched_user_name
        # so the same contact should receive separate emails for each person they watch

        # Add email contacts (from contacts table)
        for pc in email_contacts:
            if pc.email:
                watched_name = pc.participant_name.strip() if pc.participant_name else "Participant"
                contacts.append({
                    "id": pc.id,
                    "name": pc.name,
                    "email": pc.email,
                    "watched_user_name": watched_name
                })

        # Add friend contacts (from users table via friend_user_id)
        for fc in friend_contacts:
            if fc.email:
                watched_name = fc.participant_name.strip() if fc.participant_name else "Participant"
                contacts.append({
                    "id": -fc.id,  # Negative to indicate it's a user, not a contact
                    "name": fc.name or "Friend",
                    "email": fc.email,
                    "watched_user_name": watched_name
                })

    log.info(f"[Trips] _get_all_trip_email_contacts: Returning {len(contacts)} total contacts")
    return contacts


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
    vote_threshold: float = Field(default=0.5, ge=0.0, le=1.0)  # For vote mode: percentage needed (0.0-1.0)
    allow_participant_invites: bool = False  # Can participants invite others?
    share_locations_between_participants: bool = True  # Can participants see each other's locations?

    @field_validator("checkout_mode")
    @classmethod
    def validate_checkout_mode(cls, v: str) -> str:
        valid_modes = {"anyone", "vote", "owner_only"}
        if v not in valid_modes:
            raise ValueError(f"checkout_mode must be one of: {valid_modes}")
        return v


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
    grace_min: int = Field(gt=0, le=1440)  # 1 minute to 24 hours
    location_text: str | None = None
    gen_lat: float | None = Field(default=None, ge=-90, le=90)
    gen_lon: float | None = Field(default=None, ge=-180, le=180)
    start_location_text: str | None = None  # Optional start location for trips with separate start/end
    start_lat: float | None = Field(default=None, ge=-90, le=90)
    start_lon: float | None = Field(default=None, ge=-180, le=180)
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
    checkin_interval_min: int = Field(default=30, gt=0, le=1440)  # Minutes between check-in reminders
    notify_start_hour: int | None = Field(default=None, ge=0, le=23)  # Hour (0-23) when notifications start
    notify_end_hour: int | None = Field(default=None, ge=0, le=23)  # Hour (0-23) when notifications end
    notify_self: bool = False  # Send copy of all emails to trip owner
    share_live_location: bool = False  # Share live location with friends during trip
    # Group trip fields
    is_group_trip: bool = False  # Is this a group trip?
    group_settings: GroupSettings | None = None  # Settings for group trip behavior
    participant_ids: list[int] | None = None  # Friend user IDs to invite as participants
    # Custom messages (Premium feature)
    custom_start_message: str | None = None  # Custom message for trip start notification
    custom_overdue_message: str | None = None  # Custom message for overdue notification

    @field_validator("eta")
    @classmethod
    def validate_eta_after_start(cls, v: datetime, info) -> datetime:
        """Ensure ETA is after start time"""
        start = info.data.get("start")
        if start and v <= start:
            raise ValueError("ETA must be after start time")
        return v

    @field_validator("contact2")
    @classmethod
    def validate_contact2_unique(cls, v: int | None, info) -> int | None:
        """Ensure contact2 is different from contact1"""
        if v is not None:
            contact1 = info.data.get("contact1")
            if contact1 is not None and v == contact1:
                raise ValueError("contact2 must be different from contact1")
        return v

    @field_validator("contact3")
    @classmethod
    def validate_contact3_unique(cls, v: int | None, info) -> int | None:
        """Ensure contact3 is different from contact1 and contact2"""
        if v is not None:
            contact1 = info.data.get("contact1")
            contact2 = info.data.get("contact2")
            if contact1 is not None and v == contact1:
                raise ValueError("contact3 must be different from contact1")
            if contact2 is not None and v == contact2:
                raise ValueError("contact3 must be different from contact2")
        return v


class TripUpdate(BaseModel):
    """Model for updating an existing trip. All fields are optional."""
    title: str | None = None
    activity: str | None = None  # Activity name reference
    start: datetime | None = None
    eta: datetime | None = None
    grace_min: int | None = Field(default=None, gt=0, le=1440)
    location_text: str | None = None
    gen_lat: float | None = Field(default=None, ge=-90, le=90)
    gen_lon: float | None = Field(default=None, ge=-180, le=180)
    start_location_text: str | None = None
    start_lat: float | None = Field(default=None, ge=-90, le=90)
    start_lon: float | None = Field(default=None, ge=-180, le=180)
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
    checkin_interval_min: int | None = Field(default=None, gt=0, le=1440)
    notify_start_hour: int | None = Field(default=None, ge=0, le=23)
    notify_end_hour: int | None = Field(default=None, ge=0, le=23)
    notify_self: bool | None = None  # Send copy of all emails to trip owner
    share_live_location: bool | None = None  # Share live location with friends during trip
    # Custom messages (Premium feature)
    custom_start_message: str | None = None
    custom_overdue_message: str | None = None


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
    # Custom messages (Premium feature)
    custom_start_message: str | None = None
    custom_overdue_message: str | None = None
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
    user_id: int | None = None
    user_name: str | None = None


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

    # Count total contacts and check against subscription limit
    contact_count = sum(1 for c in [
        body.contact1, body.contact2, body.contact3,
        body.friend_contact1, body.friend_contact2, body.friend_contact3
    ] if c is not None)

    from src.services.subscription_check import (
        check_contact_limit,
        check_custom_intervals_allowed,
        check_custom_messages_allowed
    )
    check_contact_limit(user_id, contact_count)

    # Check if user can set custom check-in intervals (premium feature)
    check_custom_intervals_allowed(user_id, body.checkin_interval_min)

    # Check if user can set custom messages (premium feature)
    if body.custom_start_message or body.custom_overdue_message:
        check_custom_messages_allowed(user_id)

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
            if has_valid_coords and body.gen_lat is not None and body.gen_lon is not None:
                log.info(f"[Trips] Reverse geocoding at ({body.gen_lat}, {body.gen_lon})")
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
            if has_valid_start_coords and body.start_lat is not None and body.start_lon is not None:
                log.info(f"[Trips] Reverse geocoding start at ({body.start_lat}, {body.start_lon})")
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
        # If starting immediately (is_starting_now), set notified_trip_started = true to prevent
        # scheduler from sending duplicate trip start emails
        is_starting_now = initial_status == 'active'
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
                    share_live_location, is_group_trip, group_settings, notified_trip_started,
                    custom_start_message, custom_overdue_message
                ) VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon,
                    :start_location_text, :start_lat, :start_lon, :has_separate_locations,
                    :notes, :status,
                    :contact1, :contact2, :contact3, :created_at,
                    :checkin_token, :checkout_token, :timezone, :start_timezone, :eta_timezone,
                    :checkin_interval_min, :notify_start_hour, :notify_end_hour, :notify_self,
                    :share_live_location, :is_group_trip, :group_settings, :notified_trip_started,
                    :custom_start_message, :custom_overdue_message
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
                "group_settings": group_settings_json,
                "notified_trip_started": is_starting_now,  # Prevent duplicate scheduler notifications
                "custom_start_message": body.custom_start_message,
                "custom_overdue_message": body.custom_overdue_message
            }
        )
        row = result.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create trip"
            )
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
                       t.custom_start_message, t.custom_overdue_message,
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
        if trip is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created trip"
            )

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
        # Use _get_all_trip_email_contacts() for consistency with start_trip and checkin
        # This includes participant contacts for group trips (though unlikely to exist at creation time)
        trip_for_contacts = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()
        contacts_for_email = _get_all_trip_email_contacts(connection, trip_for_contacts)

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
        # Capture custom start message for immediate trips
        custom_start_msg = body.custom_start_message

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
                    owner_email=owner_email,
                    custom_message=custom_start_msg
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
                            trip_title=trip_title_for_push,
                            custom_message=custom_start_msg
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
            custom_start_message=trip.get("custom_start_message"),
            custom_overdue_message=trip.get("custom_overdue_message"),
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
                       t.custom_start_message, t.custom_overdue_message,
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

        # Batch load friend contacts for all trips (reduces N+1 queries)
        trip_ids = [trip["id"] for trip in trips]
        friend_contacts_map = _get_friend_contacts_for_trips_batch(connection, trip_ids)

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

            # Get friend contacts from pre-loaded batch
            friend_contacts = friend_contacts_map.get(trip["id"], {
                "friend_contact1": None, "friend_contact2": None, "friend_contact3": None
            })

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
                    custom_start_message=trip.get("custom_start_message"),
                    custom_overdue_message=trip.get("custom_overdue_message"),
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
                       t.custom_start_message, t.custom_overdue_message,
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
            custom_start_message=trip.get("custom_start_message"),
            custom_overdue_message=trip.get("custom_overdue_message"),
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
                       t.custom_start_message, t.custom_overdue_message,
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
            custom_start_message=trip.get("custom_start_message"),
            custom_overdue_message=trip.get("custom_overdue_message"),
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
        # Verify trip ownership and status, also get current contacts for limit check
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, activity,
                       contact1, contact2, contact3
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

        # Get friend contacts from junction table
        current_friends = _get_friend_contacts_for_trip(connection, trip_id)

        # Check contact limit: merge current contacts with updates and count
        # Use body value if provided, otherwise keep existing
        final_contacts = [
            body.contact1 if body.contact1 is not None else trip.contact1,
            body.contact2 if body.contact2 is not None else trip.contact2,
            body.contact3 if body.contact3 is not None else trip.contact3,
            body.friend_contact1 if body.friend_contact1 is not None else current_friends["friend_contact1"],
            body.friend_contact2 if body.friend_contact2 is not None else current_friends["friend_contact2"],
            body.friend_contact3 if body.friend_contact3 is not None else current_friends["friend_contact3"],
        ]
        contact_count = sum(1 for c in final_contacts if c is not None)
        from src.services.subscription_check import (
            check_contact_limit,
            check_custom_intervals_allowed,
            check_custom_messages_allowed
        )
        check_contact_limit(user_id, contact_count)

        # Check custom intervals if being updated (premium feature)
        if body.checkin_interval_min is not None:
            check_custom_intervals_allowed(user_id, body.checkin_interval_min)

        # Check custom messages if being updated (premium feature)
        if body.custom_start_message is not None or body.custom_overdue_message is not None:
            check_custom_messages_allowed(user_id)

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
            "custom_start_message": body.custom_start_message,
            "custom_overdue_message": body.custom_overdue_message,
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

            # Use current_friends already fetched earlier in function
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
                       t.custom_start_message, t.custom_overdue_message,
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
        if updated_trip is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve updated trip"
            )

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
            share_live_location=updated_trip.get("share_live_location", False),
            custom_start_message=updated_trip.get("custom_start_message"),
            custom_overdue_message=updated_trip.get("custom_overdue_message")
        )


@router.post("/{trip_id}/complete")
def complete_trip(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Mark a trip as completed"""
    with db.engine.begin() as connection:
        # Fetch trip details (without user filter to allow participant access)
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.status, t.title, t.location_text,
                       t.contact1, t.contact2, t.contact3, t.timezone, t.notify_self,
                       t.is_group_trip, t.user_id, a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Check authorization: user must be owner or accepted participant
        is_owner = trip.user_id == user_id
        if not is_owner:
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()
            if not participant:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to complete this trip"
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

        # Fetch all contact emails (owner + participants for group trips)
        contacts_for_email = _get_all_trip_email_contacts(connection, trip)

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

        # For group trips, also include participant friend contacts
        if trip.is_group_trip:
            participant_friend_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT DISTINCT friend_user_id FROM participant_trip_contacts
                    WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                    """
                ),
                {"trip_id": trip_id}
            ).fetchall()
            existing_friend_ids = set(friend_user_ids)
            for pfc in participant_friend_contacts:
                if pfc.friend_user_id not in existing_friend_ids:
                    friend_user_ids.append(pfc.friend_user_id)
                    existing_friend_ids.add(pfc.friend_user_id)
            log.info(f"[Trips] complete_trip: Added {len(participant_friend_contacts)} participant friend contacts")

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
                       t.contact1, t.contact2, t.contact3, t.timezone, t.is_group_trip,
                       t.custom_start_message,
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

        # Fetch all contact emails (owner + participants for group trips)
        contacts_for_email = _get_all_trip_email_contacts(connection, trip)

        # Update trip status to active and set start time to now (for early starts)
        # Also set notified_trip_started = true to prevent scheduler from sending duplicate emails
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET status = 'active',
                    start = now(),
                    notified_trip_started = true
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
        custom_start_msg = trip.custom_start_message

        # Schedule background task to send emails to contacts
        def send_emails_sync():
            asyncio.run(send_trip_starting_now_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name,
                user_timezone=user_timezone,
                start_location=trip_start_location,
                custom_message=custom_start_msg
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

        # For group trips, also include participant friend contacts
        if trip.is_group_trip:
            participant_friend_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT DISTINCT friend_user_id FROM participant_trip_contacts
                    WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                    """
                ),
                {"trip_id": trip_id}
            ).fetchall()
            existing_friend_ids = set(friend_user_ids)
            for pfc in participant_friend_contacts:
                if pfc.friend_user_id not in existing_friend_ids:
                    friend_user_ids.append(pfc.friend_user_id)
                    existing_friend_ids.add(pfc.friend_user_id)
            log.info(f"[Trips] start_trip: Added {len(participant_friend_contacts)} participant friend contacts")

        log.info(f"[Trips] start_trip: Friend user IDs to notify: {friend_user_ids}")

        if friend_user_ids:
            trip_title_for_push = trip.title
            user_name_for_push = user_name
            custom_start_msg_for_push = custom_start_msg
            def send_friend_starting_push_sync():
                for friend_id in friend_user_ids:
                    log.info(f"[Trips] Sending trip starting push to friend {friend_id}")
                    asyncio.run(send_friend_trip_starting_push(
                        friend_user_id=friend_id,
                        user_name=user_name_for_push,
                        trip_title=trip_title_for_push,
                        custom_message=custom_start_msg_for_push
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
        # Get trip details - check ownership or participant status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.status, t.eta, t.title, t.contact1, t.contact2, t.contact3,
                       t.timezone, t.notify_self, t.user_id, t.is_group_trip, a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Check if user is owner or accepted participant
        is_owner = trip.user_id == user_id
        if not is_owner:
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()

            if not participant:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to extend this trip"
                )

        # Allow extending active, overdue, or overdue_notified trips
        if trip.status not in ("active", "overdue", "overdue_notified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only extend active or overdue trips"
            )

        # Check if extension duration is allowed for user's subscription tier
        from src.services.subscription_check import check_extension_allowed
        check_extension_allowed(user_id, minutes)

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
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create check-in event"
            )
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

        # For group trips, update trip_participants with the extender's check-in info
        # Use upsert to handle case where owner's record doesn't exist yet
        if trip.is_group_trip:
            is_owner = trip.user_id == user_id
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, last_checkin_at, last_lat, last_lon, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, CASE WHEN :is_owner THEN 'owner' ELSE 'participant' END, 'accepted', :now, :lat, :lon, :now, :user_id)
                    ON CONFLICT (trip_id, user_id)
                    DO UPDATE SET last_checkin_at = :now, last_lat = :lat, last_lon = :lon
                    """
                ),
                {
                    "trip_id": trip_id,
                    "user_id": user_id,
                    "is_owner": is_owner,
                    "now": now.isoformat(),
                    "lat": lat,
                    "lon": lon
                }
            )
            log.info(f"[Trips] Updated trip_participants for user {user_id} on extend for trip {trip_id}")

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"
        owner_email = user.email if user and trip.notify_self else None

        # Fetch all contact emails (owner + participants for group trips)
        contacts_for_email = _get_all_trip_email_contacts(connection, trip)

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

        # For group trips, also include participant friend contacts
        if trip.is_group_trip:
            participant_friend_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT DISTINCT friend_user_id FROM participant_trip_contacts
                    WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                    """
                ),
                {"trip_id": trip_id}
            ).fetchall()
            existing_friend_ids = set(friend_user_ids)
            for pfc in participant_friend_contacts:
                if pfc.friend_user_id not in existing_friend_ids:
                    friend_user_ids.append(pfc.friend_user_id)
                    existing_friend_ids.add(pfc.friend_user_id)
            log.info(f"[Trips] extend_trip: Added {len(participant_friend_contacts)} participant friend contacts")

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

        # For group trips, send refresh pushes to owner (if not the extender) and all other participants
        if trip.is_group_trip:
            refresh_user_ids = []

            # Add owner if extender is not the owner
            if trip.user_id != user_id:
                refresh_user_ids.append(trip.user_id)

            # Add all other accepted participants
            other_participants = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id != :extender_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "extender_id": user_id}
            ).fetchall()
            refresh_user_ids.extend([p.user_id for p in other_participants])

            if refresh_user_ids:
                trip_id_for_refresh = trip_id

                def send_refresh_pushes():
                    for uid in refresh_user_ids:
                        asyncio.run(send_data_refresh_push(uid, "trip", trip_id_for_refresh))

                background_tasks.add_task(send_refresh_pushes)
                log.info(f"[Trips] Scheduled extend refresh pushes for {len(refresh_user_ids)} users")

        new_eta_iso = new_eta.isoformat()
        return {
            "ok": True,
            "message": f"Trip extended by {minutes} minutes",
            "new_eta": new_eta_iso
        }


@router.delete("/{trip_id}")
def delete_trip(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Delete a trip.

    For active group trips: Sets status to 'cancelled' (soft delete) and notifies participants.
    For other trips (solo, planned, completed): Performs hard delete.
    """
    with db.engine.begin() as connection:
        # Verify trip ownership and fetch details for decision making
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, is_group_trip, title
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

        # Determine if this should be a soft delete (cancelled) or hard delete
        is_active_group_trip = (
            trip.is_group_trip and
            trip.status in ('active', 'overdue', 'overdue_notified')
        )

        if is_active_group_trip:
            # SOFT DELETE: Mark as cancelled, notify participants

            # Get owner name for notifications
            owner = connection.execute(
                sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            owner_name = f"{owner.first_name} {owner.last_name}".strip() if owner else "The trip owner"
            if not owner_name:
                owner_name = "The trip owner"

            # Get all accepted participants (excluding owner)
            participants = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id AND status = 'accepted' AND user_id != :owner_id
                    """
                ),
                {"trip_id": trip_id, "owner_id": user_id}
            ).fetchall()

            # Update trip status to cancelled
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE trips
                    SET status = 'cancelled', completed_at = :cancelled_at
                    WHERE id = :trip_id
                    """
                ),
                {"trip_id": trip_id, "cancelled_at": datetime.now(UTC).isoformat()}
            )

            # Clear checkout votes (no longer relevant)
            connection.execute(
                sqlalchemy.text("DELETE FROM checkout_votes WHERE trip_id = :trip_id"),
                {"trip_id": trip_id}
            )

            # Send notifications to participants
            participant_ids = [p.user_id for p in participants]
            if participant_ids:
                trip_title = trip.title
                trip_id_for_notif = trip_id

                def send_cancelled_notifications():
                    for pid in participant_ids:
                        asyncio.run(send_trip_cancelled_push(
                            participant_user_id=pid,
                            owner_name=owner_name,
                            trip_title=trip_title,
                            trip_id=trip_id_for_notif
                        ))
                        # Also send data refresh push so their UI updates
                        asyncio.run(send_data_refresh_push(pid, "trip", trip_id_for_notif))

                background_tasks.add_task(send_cancelled_notifications)
                log.info(f"[Trips] Scheduled cancelled notifications for {len(participant_ids)} participants")

            return {"ok": True, "message": "Trip cancelled successfully"}

        else:
            # HARD DELETE: Remove trip completely

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

            # Now delete the trip (CASCADE handles other relations)
            connection.execute(
                sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
                {"trip_id": trip_id}
            )

            return {"ok": True, "message": "Trip deleted successfully"}


@router.get("/{trip_id}/timeline", response_model=list[TimelineEvent])
def get_trip_timeline(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get timeline events for a specific trip"""
    with db.engine.begin() as connection:
        # Verify trip ownership OR accepted participant status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id
                FROM trips t
                WHERE t.id = :trip_id
                AND (
                    t.user_id = :user_id
                    OR EXISTS (
                        SELECT 1 FROM trip_participants tp
                        WHERE tp.trip_id = t.id AND tp.user_id = :user_id AND tp.status = 'accepted'
                    )
                )
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Fetch timeline events with user info
        events = connection.execute(
            sqlalchemy.text(
                """
                SELECT e.id, e.what AS kind, e.timestamp AS at, e.lat, e.lon, e.extended_by,
                       e.user_id, u.first_name, u.last_name
                FROM events e
                LEFT JOIN users u ON e.user_id = u.id
                WHERE e.trip_id = :trip_id
                ORDER BY e.timestamp DESC
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
                extended_by=e.extended_by,
                user_id=e.user_id,
                user_name=f"{e.first_name} {e.last_name}".strip() if e.first_name else None
            )
            for e in events
        ]


# ==================== My Trip Contacts ====================

class TripContactResponse(BaseModel):
    """A safety contact for a trip (either email contact or friend)."""
    type: str  # "email" or "friend"
    # For email contacts
    contact_id: int | None = None
    name: str | None = None
    email: str | None = None
    # For friend contacts
    friend_user_id: int | None = None
    friend_name: str | None = None
    profile_photo_url: str | None = None


class MyTripContactsResponse(BaseModel):
    """Response containing the current user's safety contacts for a trip."""
    contacts: list[TripContactResponse]


@router.get("/{trip_id}/my-contacts", response_model=MyTripContactsResponse)
def get_my_trip_contacts(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get the current user's safety contacts for a trip.

    For group trips, each participant has their own safety contacts.
    This endpoint returns the contacts for the authenticated user:
    - If user is owner: returns owner's contacts (contact1/2/3, friend_contact1/2/3)
    - If user is participant: returns participant's contacts from participant_trip_contacts
    """
    with db.engine.begin() as connection:
        # Get trip and check if user has access
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.contact1, t.contact2, t.contact3, t.is_group_trip
                FROM trips t
                WHERE t.id = :trip_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        is_owner = trip.user_id == user_id
        contacts: list[TripContactResponse] = []
        log.info(f"[MyContacts] trip_id={trip_id}, user_id={user_id}, is_owner={is_owner}")

        if is_owner:
            # Owner: get contacts from trip table and trip_safety_contacts

            # Get email contacts (contact1, contact2, contact3)
            contact_ids = [trip.contact1, trip.contact2, trip.contact3]
            log.info(f"[MyContacts] Owner email contact_ids from trips table: {contact_ids}")
            contact_ids = [c for c in contact_ids if c is not None]
            log.info(f"[MyContacts] Owner email contact_ids (filtered): {contact_ids}")

            if contact_ids:
                email_contacts = connection.execute(
                    sqlalchemy.text(
                        "SELECT id, name, email FROM contacts WHERE id = ANY(:ids)"
                    ),
                    {"ids": contact_ids}
                ).fetchall()
                log.info(f"[MyContacts] Owner email_contacts query returned {len(email_contacts)} rows")

                for c in email_contacts:
                    contacts.append(TripContactResponse(
                        type="email",
                        contact_id=c.id,
                        name=c.name,
                        email=c.email
                    ))

            # Get friend contacts from trip_safety_contacts
            friend_rows = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT tsc.friend_user_id, u.first_name, u.last_name, u.profile_photo_url
                    FROM trip_safety_contacts tsc
                    JOIN users u ON tsc.friend_user_id = u.id
                    WHERE tsc.trip_id = :trip_id AND tsc.friend_user_id IS NOT NULL
                    ORDER BY tsc.position
                    """
                ),
                {"trip_id": trip_id}
            ).fetchall()
            log.info(f"[MyContacts] Owner friend_rows query returned {len(friend_rows)} rows")

            for f in friend_rows:
                contacts.append(TripContactResponse(
                    type="friend",
                    friend_user_id=f.friend_user_id,
                    friend_name=f"{f.first_name} {f.last_name}".strip() or None,
                    profile_photo_url=f.profile_photo_url
                ))

            log.info(f"[MyContacts] Owner total contacts: {len(contacts)}")

        else:
            # Participant: check they have accepted the trip
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id, status FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :user_id
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()

            if not participant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Trip not found or access denied"
                )

            # Debug: Get raw count from participant_trip_contacts
            ptc_count = connection.execute(
                sqlalchemy.text(
                    "SELECT COUNT(*) FROM participant_trip_contacts WHERE trip_id = :trip_id AND participant_user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).scalar() or 0
            log.info(f"[MyContacts] Participant has {ptc_count} rows in participant_trip_contacts")

            # Get participant's contacts from participant_trip_contacts
            # Email contacts
            email_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT c.id, c.name, c.email
                    FROM participant_trip_contacts ptc
                    JOIN contacts c ON ptc.contact_id = c.id
                    WHERE ptc.trip_id = :trip_id AND ptc.participant_user_id = :user_id
                    ORDER BY ptc.position
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchall()
            log.info(f"[MyContacts] Participant email_contacts query returned {len(email_contacts)} rows")

            for c in email_contacts:
                contacts.append(TripContactResponse(
                    type="email",
                    contact_id=c.id,
                    name=c.name,
                    email=c.email
                ))

            # Friend contacts
            friend_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT ptc.friend_user_id, u.first_name, u.last_name, u.profile_photo_url
                    FROM participant_trip_contacts ptc
                    JOIN users u ON ptc.friend_user_id = u.id
                    WHERE ptc.trip_id = :trip_id AND ptc.participant_user_id = :user_id
                        AND ptc.friend_user_id IS NOT NULL
                    ORDER BY ptc.position
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchall()
            log.info(f"[MyContacts] Participant friend_contacts query returned {len(friend_contacts)} rows")

            for f in friend_contacts:
                contacts.append(TripContactResponse(
                    type="friend",
                    friend_user_id=f.friend_user_id,
                    friend_name=f"{f.first_name} {f.last_name}".strip() or None,
                    profile_photo_url=f.profile_photo_url
                ))

            log.info(f"[MyContacts] Participant total contacts: {len(contacts)}")

        return MyTripContactsResponse(contacts=contacts)


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
