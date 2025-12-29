"""Friend management endpoints"""

import asyncio
import secrets
from datetime import datetime, timedelta

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.services.notifications import send_friend_request_accepted_push

router = APIRouter(
    prefix="/api/v1/friends",
    tags=["friends"],
)

# How long invite tokens are valid (7 days)
INVITE_EXPIRY_DAYS = 7


# Response models
class FriendResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    profile_photo_url: str | None
    member_since: str
    friendship_since: str
    # Mini profile stats
    age: int | None = None
    achievements_count: int | None = None
    total_trips: int | None = None
    total_adventure_hours: int | None = None
    favorite_activity_name: str | None = None
    favorite_activity_icon: str | None = None


class FriendInviteResponse(BaseModel):
    token: str
    invite_url: str
    expires_at: str


class FriendInvitePreview(BaseModel):
    inviter_first_name: str
    inviter_profile_photo_url: str | None
    inviter_member_since: str
    expires_at: str
    is_valid: bool


class PendingInviteResponse(BaseModel):
    id: int
    token: str
    created_at: str
    expires_at: str
    status: str  # "pending", "accepted", "expired"
    accepted_by_name: str | None


def _generate_invite_token() -> str:
    """Generate a URL-safe invite token."""
    return secrets.token_urlsafe(32)


def _get_friendship(connection, user_id: int, other_user_id: int):
    """Check if two users are friends. Returns the friendship row or None."""
    # Ensure user_id_1 < user_id_2 for the query
    id1, id2 = min(user_id, other_user_id), max(user_id, other_user_id)
    return connection.execute(
        sqlalchemy.text(
            """
            SELECT id, user_id_1, user_id_2, created_at
            FROM friendships
            WHERE user_id_1 = :id1 AND user_id_2 = :id2
            """
        ),
        {"id1": id1, "id2": id2}
    ).fetchone()


def _create_friendship(connection, user_id: int, other_user_id: int) -> None:
    """Create a friendship between two users."""
    # Ensure user_id_1 < user_id_2 for the constraint
    id1, id2 = min(user_id, other_user_id), max(user_id, other_user_id)
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO friendships (user_id_1, user_id_2)
            VALUES (:id1, :id2)
            """
        ),
        {"id1": id1, "id2": id2}
    )


def _compute_friend_stats(connection, friend_user_id: int) -> dict:
    """Compute stats for a friend's mini profile.

    Returns dict with: age, achievements_count, total_trips,
    total_adventure_hours, favorite_activity_name, favorite_activity_icon
    """
    # Get user age
    user = connection.execute(
        sqlalchemy.text("SELECT age FROM users WHERE id = :user_id"),
        {"user_id": friend_user_id}
    ).fetchone()
    age = user.age if user and user.age and user.age > 0 else None

    # Get total completed trips count
    trips_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(*) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": friend_user_id}
    ).fetchone()
    total_trips = trips_result.count if trips_result else 0

    # Get total adventure hours (sum of trip durations for completed trips)
    hours_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COALESCE(
                SUM(EXTRACT(EPOCH FROM (completed_at - start)) / 3600),
                0
            ) as total_hours
            FROM trips
            WHERE user_id = :user_id
            AND status = 'completed'
            AND completed_at IS NOT NULL
            """
        ),
        {"user_id": friend_user_id}
    ).fetchone()
    total_adventure_hours = int(hours_result.total_hours) if hours_result else 0

    # Calculate achievements count based on trip thresholds
    achievements_count = _calculate_achievements_count(
        total_trips, total_adventure_hours, connection, friend_user_id
    )

    # Get favorite activity (most common for completed trips)
    favorite_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT a.name, a.icon, COUNT(*) as trip_count
            FROM trips t
            JOIN activities a ON t.activity = a.id
            WHERE t.user_id = :user_id AND t.status = 'completed'
            GROUP BY a.id, a.name, a.icon
            ORDER BY trip_count DESC
            LIMIT 1
            """
        ),
        {"user_id": friend_user_id}
    ).fetchone()
    favorite_activity_name = favorite_result.name if favorite_result else None
    favorite_activity_icon = favorite_result.icon if favorite_result else None

    return {
        "age": age,
        "achievements_count": achievements_count,
        "total_trips": total_trips,
        "total_adventure_hours": total_adventure_hours,
        "favorite_activity_name": favorite_activity_name,
        "favorite_activity_icon": favorite_activity_icon,
    }


def _calculate_achievements_count(
    total_trips: int, total_hours: int, connection, user_id: int
) -> int:
    """Calculate achievements earned based on trip data (mirrors iOS logic)."""
    count = 0

    # Total Trips achievements
    for threshold in [1, 5, 10, 25, 50, 100, 150, 200, 250, 500, 1000]:
        if total_trips >= threshold:
            count += 1

    # Adventure Time achievements (hours)
    for threshold in [1, 10, 50, 100, 250, 500, 1000, 2500]:
        if total_hours >= threshold:
            count += 1

    # Activities tried achievements
    activities_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT activity) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_activities = activities_result.count if activities_result else 0
    for threshold in [1, 3, 5, 10, 15, 20]:
        if unique_activities >= threshold:
            count += 1

    # Locations achievements
    locations_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT location_text) as count
            FROM trips
            WHERE user_id = :user_id
            AND status = 'completed'
            AND location_text IS NOT NULL
            AND location_text != ''
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_locations = locations_result.count if locations_result else 0
    for threshold in [1, 5, 10, 25, 50, 100, 250]:
        if unique_locations >= threshold:
            count += 1

    return count


# ==================== Invite Endpoints ====================

@router.post("/invite", response_model=FriendInviteResponse)
def create_invite(user_id: int = Depends(auth.get_current_user_id)):
    """Generate a shareable friend invite link."""
    token = _generate_invite_token()
    expires_at = datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS)

    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at)
                VALUES (:inviter_id, :token, :expires_at)
                """
            ),
            {
                "inviter_id": user_id,
                "token": token,
                "expires_at": expires_at
            }
        )

    # Build the invite URL (will be used with universal links)
    invite_url = f"https://api.homeboundapp.com/f/{token}"

    return FriendInviteResponse(
        token=token,
        invite_url=invite_url,
        expires_at=expires_at.isoformat()
    )


@router.get("/invite/{token}", response_model=FriendInvitePreview)
def get_invite_preview(token: str):
    """Get invite details for preview before accepting (public endpoint)."""
    with db.engine.begin() as connection:
        invite = connection.execute(
            sqlalchemy.text(
                """
                SELECT fi.id, fi.inviter_id, fi.expires_at, fi.use_count, fi.max_uses,
                       u.first_name, u.profile_photo_url, u.created_at as member_since
                FROM friend_invites fi
                JOIN users u ON u.id = fi.inviter_id
                WHERE fi.token = :token
                """
            ),
            {"token": token}
        ).fetchone()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found"
            )

        now = datetime.utcnow()
        is_expired = invite.expires_at < now
        is_used_up = invite.use_count >= invite.max_uses
        is_valid = not is_expired and not is_used_up

        return FriendInvitePreview(
            inviter_first_name=invite.first_name or "A user",
            inviter_profile_photo_url=invite.profile_photo_url,
            inviter_member_since=invite.member_since.isoformat() if invite.member_since else "",
            expires_at=invite.expires_at.isoformat(),
            is_valid=is_valid
        )


@router.post("/invite/{token}/accept", response_model=FriendResponse)
def accept_invite(
    token: str,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Accept a friend invite and create the friendship."""
    with db.engine.begin() as connection:
        # Get the invite
        invite = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, inviter_id, expires_at, use_count, max_uses
                FROM friend_invites
                WHERE token = :token
                """
            ),
            {"token": token}
        ).fetchone()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found"
            )

        # Check if invite is still valid
        now = datetime.utcnow()
        if invite.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Invite has expired"
            )

        if invite.use_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Invite has already been used"
            )

        inviter_id = invite.inviter_id

        # Can't be friends with yourself
        if inviter_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot accept your own invite"
            )

        # Check if already friends
        existing = _get_friendship(connection, user_id, inviter_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already friends with this user"
            )

        # Create the friendship (handle race condition where friendship was created between check and insert)
        try:
            _create_friendship(connection, user_id, inviter_id)
        except sqlalchemy.exc.IntegrityError:
            # Friendship already exists (race condition)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already friends with this user"
            )

        # Update invite usage
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE friend_invites
                SET use_count = use_count + 1,
                    accepted_by = :accepted_by,
                    accepted_at = :accepted_at
                WHERE id = :invite_id
                """
            ),
            {
                "invite_id": invite.id,
                "accepted_by": user_id,
                "accepted_at": now
            }
        )

        # Get the inviter's profile to return
        inviter = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, first_name, last_name, profile_photo_url, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": inviter_id}
        ).fetchone()

        if not inviter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inviter not found"
            )

        # Get friendship created_at
        friendship = _get_friendship(connection, user_id, inviter_id)

        # Get the accepter's name for the notification
        accepter = connection.execute(
            sqlalchemy.text(
                """
                SELECT first_name, last_name
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        accepter_name = "Someone"
        if accepter:
            accepter_name = f"{accepter.first_name or ''} {accepter.last_name or ''}".strip() or "Someone"

        # Send push notification to inviter in background
        def send_push_sync():
            asyncio.run(send_friend_request_accepted_push(
                inviter_user_id=inviter_id,
                accepter_name=accepter_name
            ))

        background_tasks.add_task(send_push_sync)

        # Compute stats for the inviter
        stats = _compute_friend_stats(connection, inviter_id)

        return FriendResponse(
            user_id=inviter.id,
            first_name=inviter.first_name or "",
            last_name=inviter.last_name or "",
            profile_photo_url=inviter.profile_photo_url,
            member_since=inviter.created_at.isoformat() if inviter.created_at else "",
            friendship_since=friendship.created_at.isoformat() if friendship else "",
            age=stats["age"],
            achievements_count=stats["achievements_count"],
            total_trips=stats["total_trips"],
            total_adventure_hours=stats["total_adventure_hours"],
            favorite_activity_name=stats["favorite_activity_name"],
            favorite_activity_icon=stats["favorite_activity_icon"],
        )


@router.get("/invites/pending", response_model=list[PendingInviteResponse])
def get_pending_invites(user_id: int = Depends(auth.get_current_user_id)):
    """Get all invites sent by the current user with their status."""
    with db.engine.begin() as connection:
        invites = connection.execute(
            sqlalchemy.text(
                """
                SELECT fi.id, fi.token, fi.created_at, fi.expires_at,
                       fi.use_count, fi.max_uses, fi.accepted_by,
                       u.first_name as accepted_by_first_name,
                       u.last_name as accepted_by_last_name
                FROM friend_invites fi
                LEFT JOIN users u ON u.id = fi.accepted_by
                WHERE fi.inviter_id = :user_id
                ORDER BY fi.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        now = datetime.utcnow()
        result = []
        for inv in invites:
            # Determine status
            if inv.use_count >= inv.max_uses:
                invite_status = "accepted"
            elif inv.expires_at < now:
                invite_status = "expired"
            else:
                invite_status = "pending"

            # Build accepted_by name if available
            accepted_by_name = None
            if inv.accepted_by_first_name:
                accepted_by_name = f"{inv.accepted_by_first_name} {inv.accepted_by_last_name or ''}".strip()

            result.append(PendingInviteResponse(
                id=inv.id,
                token=inv.token,
                created_at=inv.created_at.isoformat(),
                expires_at=inv.expires_at.isoformat(),
                status=invite_status,
                accepted_by_name=accepted_by_name
            ))

        return result


# ==================== Friends List Endpoints ====================

@router.get("/", response_model=list[FriendResponse])
def get_friends(user_id: int = Depends(auth.get_current_user_id)):
    """Get all friends for the current user with their stats."""
    with db.engine.begin() as connection:
        # Query friendships where user is either user_id_1 or user_id_2
        friends = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    u.id as user_id,
                    u.first_name,
                    u.last_name,
                    u.profile_photo_url,
                    u.created_at as member_since,
                    f.created_at as friendship_since
                FROM friendships f
                JOIN users u ON (
                    (f.user_id_1 = :user_id AND u.id = f.user_id_2) OR
                    (f.user_id_2 = :user_id AND u.id = f.user_id_1)
                )
                ORDER BY f.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        result = []
        for f in friends:
            stats = _compute_friend_stats(connection, f.user_id)
            result.append(FriendResponse(
                user_id=f.user_id,
                first_name=f.first_name or "",
                last_name=f.last_name or "",
                profile_photo_url=f.profile_photo_url,
                member_since=f.member_since.isoformat() if f.member_since else "",
                friendship_since=f.friendship_since.isoformat() if f.friendship_since else "",
                age=stats["age"],
                achievements_count=stats["achievements_count"],
                total_trips=stats["total_trips"],
                total_adventure_hours=stats["total_adventure_hours"],
                favorite_activity_name=stats["favorite_activity_name"],
                favorite_activity_icon=stats["favorite_activity_icon"],
            ))
        return result


# ==================== Friend's Active Trips ====================
# NOTE: This must be defined BEFORE /{friend_user_id} to avoid route conflicts

class FriendActiveTripOwner(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    profile_photo_url: str | None


class CheckinLocation(BaseModel):
    """A check-in event with location data for friends to see on a map."""
    timestamp: str
    latitude: float | None
    longitude: float | None
    location_name: str | None


class LiveLocationData(BaseModel):
    """Real-time location data for friends to track during a trip."""
    latitude: float
    longitude: float
    timestamp: str
    speed: float | None


class FriendActiveTrip(BaseModel):
    id: int
    owner: FriendActiveTripOwner
    title: str
    activity_name: str
    activity_icon: str
    activity_colors: dict
    status: str
    start: str
    eta: str
    grace_min: int
    location_text: str | None
    start_location_text: str | None
    notes: str | None
    timezone: str | None
    last_checkin_at: str | None
    # Enhanced friend visibility fields
    checkin_locations: list[CheckinLocation] | None = None
    live_location: LiveLocationData | None = None
    destination_lat: float | None = None
    destination_lon: float | None = None
    start_lat: float | None = None
    start_lon: float | None = None
    has_pending_update_request: bool = False


@router.get("/active-trips", response_model=list[FriendActiveTrip])
def get_friend_active_trips(user_id: int = Depends(auth.get_current_user_id)):
    """Get all active/planned trips where the current user is a friend safety contact.

    This allows friends to see the status of trips they're monitoring.
    Friends get enhanced visibility compared to email contacts, including:
    - Check-in locations on a map
    - Live location (if owner has enabled it)
    - Trip coordinates for map display
    """
    import json
    import logging
    from src.services.geocoding import reverse_geocode_sync
    log = logging.getLogger(__name__)
    log.info(f"[Friends] get_friend_active_trips called for user_id={user_id}")

    with db.engine.begin() as connection:
        # Get trips with owner visibility settings and coordinates
        trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.start_location_text, t.notes, t.status, t.timezone,
                       t.gen_lat, t.gen_lon, t.start_lat, t.start_lon, t.share_live_location,
                       a.name as activity_name, a.icon as activity_icon, a.colors as activity_colors,
                       u.first_name, u.last_name, u.profile_photo_url,
                       u.friend_share_checkin_locations, u.friend_share_live_location,
                       u.friend_share_notes, u.friend_allow_update_requests,
                       e.timestamp as last_checkin_at
                FROM trips t
                JOIN trip_safety_contacts tsc ON tsc.trip_id = t.id
                JOIN activities a ON t.activity = a.id
                JOIN users u ON t.user_id = u.id
                LEFT JOIN events e ON t.last_checkin = e.id
                WHERE tsc.friend_user_id = :current_user_id
                AND t.status IN ('active', 'overdue', 'overdue_notified', 'planned')
                ORDER BY t.start ASC
                """
            ),
            {"current_user_id": user_id}
        ).mappings().fetchall()

        result = []
        for trip in trips:
            # Parse activity colors (may be JSON string or dict)
            colors = trip["activity_colors"]
            if isinstance(colors, str):
                colors = json.loads(colors)

            # Format datetime fields
            start_str = trip["start"]
            if hasattr(start_str, 'isoformat'):
                start_str = start_str.isoformat()
            eta_str = trip["eta"]
            if hasattr(eta_str, 'isoformat'):
                eta_str = eta_str.isoformat()
            last_checkin_str = trip["last_checkin_at"]
            if last_checkin_str is not None and hasattr(last_checkin_str, 'isoformat'):
                last_checkin_str = last_checkin_str.isoformat()

            # Get owner's visibility settings (with defaults for backwards compatibility)
            share_checkin_locations = trip.get("friend_share_checkin_locations", True)
            share_live_location = trip.get("friend_share_live_location", False)
            share_notes = trip.get("friend_share_notes", True)
            allow_update_requests = trip.get("friend_allow_update_requests", True)

            # Fetch check-in locations if owner allows it
            checkin_locations = None
            if share_checkin_locations:
                checkin_events = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT timestamp, lat, lon
                        FROM events
                        WHERE trip_id = :trip_id AND what = 'checkin' AND lat IS NOT NULL
                        ORDER BY timestamp DESC
                        LIMIT 10
                        """
                    ),
                    {"trip_id": trip["id"]}
                ).fetchall()

                if checkin_events:
                    checkin_locations = []
                    for event in checkin_events:
                        ts = event.timestamp
                        if hasattr(ts, 'isoformat'):
                            ts = ts.isoformat()
                        # Try to reverse geocode the location
                        location_name = None
                        if event.lat and event.lon:
                            try:
                                location_name = reverse_geocode_sync(event.lat, event.lon)
                            except Exception:
                                pass
                        checkin_locations.append(CheckinLocation(
                            timestamp=ts,
                            latitude=event.lat,
                            longitude=event.lon,
                            location_name=location_name
                        ))

            # Fetch live location if owner allows it AND trip has it enabled
            live_location = None
            trip_has_live_location = trip.get("share_live_location", False)
            if share_live_location and trip_has_live_location:
                live_loc = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT latitude, longitude, speed, timestamp
                        FROM live_locations
                        WHERE trip_id = :trip_id
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """
                    ),
                    {"trip_id": trip["id"]}
                ).fetchone()

                if live_loc:
                    ts = live_loc.timestamp
                    if hasattr(ts, 'isoformat'):
                        ts = ts.isoformat()
                    live_location = LiveLocationData(
                        latitude=live_loc.latitude,
                        longitude=live_loc.longitude,
                        speed=live_loc.speed,
                        timestamp=ts
                    )

            # Check for pending update requests from this friend
            has_pending_update = False
            if allow_update_requests:
                pending = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT 1 FROM update_requests
                        WHERE trip_id = :trip_id AND requester_user_id = :user_id
                        AND resolved_at IS NULL
                        AND requested_at > NOW() - INTERVAL '10 minutes'
                        LIMIT 1
                        """
                    ),
                    {"trip_id": trip["id"], "user_id": user_id}
                ).fetchone()
                has_pending_update = pending is not None

            result.append(FriendActiveTrip(
                id=trip["id"],
                owner=FriendActiveTripOwner(
                    user_id=trip["user_id"],
                    first_name=trip["first_name"] or "",
                    last_name=trip["last_name"] or "",
                    profile_photo_url=trip["profile_photo_url"]
                ),
                title=trip["title"],
                activity_name=trip["activity_name"],
                activity_icon=trip["activity_icon"],
                activity_colors=colors,
                status=trip["status"],
                start=start_str,
                eta=eta_str,
                grace_min=trip["grace_min"],
                location_text=trip["location_text"],
                start_location_text=trip["start_location_text"],
                notes=trip["notes"] if share_notes else None,
                timezone=trip["timezone"],
                last_checkin_at=last_checkin_str,
                # Enhanced friend visibility fields
                checkin_locations=checkin_locations,
                live_location=live_location,
                destination_lat=trip["gen_lat"],
                destination_lon=trip["gen_lon"],
                start_lat=trip.get("start_lat"),
                start_lon=trip.get("start_lon"),
                has_pending_update_request=has_pending_update
            ))

        return result


# ==================== Update Request Endpoint ====================

class UpdateRequestResponse(BaseModel):
    ok: bool
    message: str
    cooldown_remaining_seconds: int | None = None


@router.post("/trips/{trip_id}/request-update", response_model=UpdateRequestResponse)
def request_trip_update(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Request an update from the trip owner.

    Friends can use this to "ping" the trip owner when they're worried.
    Rate limited to 1 request per 10 minutes per trip per user.
    """
    from datetime import timezone
    from src.services.notifications import send_update_request_push
    import asyncio

    with db.engine.begin() as connection:
        # Verify user is a friend safety contact for this trip
        is_contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT 1 FROM trip_safety_contacts
                WHERE trip_id = :trip_id AND friend_user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not is_contact:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a safety contact for this trip"
            )

        # Get trip info and owner settings
        trip_info = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.title, t.user_id as owner_id, t.status,
                       u.first_name as owner_first_name, u.friend_allow_update_requests
                FROM trips t
                JOIN users u ON t.user_id = u.id
                WHERE t.id = :trip_id
                AND t.status IN ('active', 'overdue', 'overdue_notified', 'planned')
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found or not active"
            )

        # Check if owner allows update requests (default True for backwards compatibility)
        allow_requests = trip_info.friend_allow_update_requests
        if allow_requests is not None and not allow_requests:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trip owner has disabled update requests"
            )

        # Check for recent request from this user (rate limiting)
        now = datetime.now(timezone.utc)
        recent = connection.execute(
            sqlalchemy.text(
                """
                SELECT requested_at FROM update_requests
                WHERE trip_id = :trip_id AND requester_user_id = :user_id
                AND requested_at > :cutoff
                ORDER BY requested_at DESC LIMIT 1
                """
            ),
            {"trip_id": trip_id, "user_id": user_id, "cutoff": (now - timedelta(minutes=10)).isoformat()}
        ).fetchone()

        if recent:
            # Calculate remaining cooldown
            recent_at = recent.requested_at
            if hasattr(recent_at, 'replace'):
                recent_at = recent_at.replace(tzinfo=timezone.utc)
            cooldown_seconds = int(600 - (now - recent_at).total_seconds())
            return UpdateRequestResponse(
                ok=False,
                message="Please wait before requesting another update",
                cooldown_remaining_seconds=max(0, cooldown_seconds)
            )

        # Get requester's name for the notification
        requester = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        requester_name = f"{requester.first_name} {requester.last_name}".strip() if requester else "A friend"

        # Create the update request
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO update_requests (trip_id, requester_user_id, owner_user_id, requested_at)
                VALUES (:trip_id, :requester_id, :owner_id, :requested_at)
                """
            ),
            {
                "trip_id": trip_id,
                "requester_id": user_id,
                "owner_id": trip_info.owner_id,
                "requested_at": now.isoformat()
            }
        )

        # Send push notification to trip owner
        def send_push_sync():
            asyncio.run(send_update_request_push(
                owner_user_id=trip_info.owner_id,
                requester_name=requester_name,
                trip_title=trip_info.title,
                trip_id=trip_id
            ))

        background_tasks.add_task(send_push_sync)

        return UpdateRequestResponse(
            ok=True,
            message="Update request sent",
            cooldown_remaining_seconds=600  # 10 minute cooldown starts now
        )


# ==================== Individual Friend Endpoints ====================

@router.get("/{friend_user_id}", response_model=FriendResponse)
def get_friend(friend_user_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific friend's profile with stats."""
    with db.engine.begin() as connection:
        # Verify they are friends
        friendship = _get_friendship(connection, user_id, friend_user_id)
        if not friendship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Friend not found"
            )

        # Get friend's profile
        friend = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, first_name, last_name, profile_photo_url, created_at
                FROM users
                WHERE id = :friend_id
                """
            ),
            {"friend_id": friend_user_id}
        ).fetchone()

        if not friend:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        stats = _compute_friend_stats(connection, friend_user_id)

        return FriendResponse(
            user_id=friend.id,
            first_name=friend.first_name or "",
            last_name=friend.last_name or "",
            profile_photo_url=friend.profile_photo_url,
            member_since=friend.created_at.isoformat() if friend.created_at else "",
            friendship_since=friendship.created_at.isoformat() if friendship.created_at else "",
            age=stats["age"],
            achievements_count=stats["achievements_count"],
            total_trips=stats["total_trips"],
            total_adventure_hours=stats["total_adventure_hours"],
            favorite_activity_name=stats["favorite_activity_name"],
            favorite_activity_icon=stats["favorite_activity_icon"],
        )


@router.delete("/{friend_user_id}")
def remove_friend(friend_user_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Remove a friend."""
    with db.engine.begin() as connection:
        # Verify they are friends and get the friendship
        friendship = _get_friendship(connection, user_id, friend_user_id)
        if not friendship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Friend not found"
            )

        # Delete the friendship
        id1, id2 = min(user_id, friend_user_id), max(user_id, friend_user_id)
        connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM friendships
                WHERE user_id_1 = :id1 AND user_id_2 = :id2
                """
            ),
            {"id1": id1, "id2": id2}
        )

        return {"ok": True, "message": "Friend removed"}
